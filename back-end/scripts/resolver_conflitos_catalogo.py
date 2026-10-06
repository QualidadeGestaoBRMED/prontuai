#!/usr/bin/env python3
"""
Resolve os conflitos de importação do catálogo a partir de um CSV de decisões.

DE ONDE VÊM OS CONFLITOS
    `seed_exam_catalog.py` não escolhe: termo que o CSV de sinônimos pôs sob
    mais de um pai, ou que já era pai, vai para `exam_variation_conflicts` com
    os pais do CSV como candidatos. Medido no dev: dos 21 conflitos, a maioria
    não é sinônimo ambíguo — é o MESMO exame cadastrado duas vezes
    (`colpocitologia` × `colpocitologico`, `t 4 livre` × `t4 livre`). Atribuir
    o conflito trataria o sintoma e deixaria a duplicata.

AS TRÊS DECISÕES DO CSV (colunas: acao, termo, pai, observacao)
    juntar     `termo` é um exame pai duplicado de `pai`. As variações dele
               passam para `pai`, e o próprio nome vira variação de `pai`
               (continua sendo vocabulário do portão de extração). O pai
               duplicado deixa de existir.
    atribuir   `termo` é um conflito pendente; vira variação de `pai`.
    descartar  `termo` é um conflito pendente sem exame (ex.: "ap/perfil", que
               é incidência de raio-X); o conflito só é encerrado.

    Os nomes são comparados normalizados (`normalizar_termo`), então caixa,
    acento e pontuação não importam.

O QUE O SCRIPT FAZ SOZINHO
    Depois das decisões, cada conflito ainda pendente tem os candidatos
    reavaliados: se todos agora apontam para o mesmo pai — porque os
    duplicados foram juntados —, ele é atribuído a esse pai. É assim que
    `papanicolaou` (candidatos colpocitologia | colpocitologico) chega ao lugar
    certo sem linha própria no CSV. Conflito com candidatos que continuam
    distintos fica pendente para o painel.

    Conflito cujo termo já está sob o pai certo (ex.: o próprio nome do pai
    que foi juntado) é encerrado como atribuído sem criar nada.

SEGURANÇA
    Uma transação só. Sem `--aplicar`, tudo é executado e desfeito no fim: o
    dry-run passa pelas mesmas checagens de árvore estrita que a gravação.
    Linhas tocadas ficam com `created_by`/`updated_by` = `--ator`, e o
    relatório JSON (`--json`) guarda o pai removido em cada junção, para
    desfazer à mão se preciso. Faça dump das tabelas do catálogo antes de
    aplicar em staging/produção.

    Vetores das variações novas ficam nulos (pendência de vetorização, como no
    seed). O cache do motor é por processo: depois de aplicar, reinicie o
    backend.

USO
    python scripts/resolver_conflitos_catalogo.py --decisoes decisoes_conflitos_catalogo.csv
    python scripts/resolver_conflitos_catalogo.py --decisoes decisoes_conflitos_catalogo.csv --aplicar --ator seu.email@grupobrmed.com.br
"""
import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import user_db  # noqa: E402
from app.core.db.models import (  # noqa: E402
    ExamParentModel,
    ExamVariationConflictModel,
    ExamVariationModel,
)
from app.core.exam_normalize import normalizar_termo  # noqa: E402
from app.models.audit_log import AuditLogCreate  # noqa: E402
from app.services import exam_catalog_source  # noqa: E402
from app.services.exam_vector_service import derivar_vector_id  # noqa: E402

ACOES = {"juntar", "atribuir", "descartar"}


class Catalogo:
    """Operações do catálogo dentro de uma única sessão (uma transação)."""

    def __init__(self, sessao, ator: str):
        self.s = sessao
        self.ator = ator
        self.agora = datetime.utcnow()

    def pai(self, nome: str) -> Optional[ExamParentModel]:
        return (
            self.s.query(ExamParentModel)
            .filter(
                ExamParentModel.name_normalized == normalizar_termo(nome),
                ExamParentModel.is_active.is_(True),
            )
            .first()
        )

    def pai_do_termo(self, normalizado: str) -> Optional[ExamParentModel]:
        """Pai ativo que é o termo, ou que tem o termo como variação."""
        pai = (
            self.s.query(ExamParentModel)
            .filter(
                ExamParentModel.name_normalized == normalizado,
                ExamParentModel.is_active.is_(True),
            )
            .first()
        )
        if pai:
            return pai
        variacao = (
            self.s.query(ExamVariationModel)
            .filter(ExamVariationModel.name_normalized == normalizado)
            .first()
        )
        if not variacao:
            return None
        return (
            self.s.query(ExamParentModel)
            .filter(
                ExamParentModel.id == variacao.parent_id,
                ExamParentModel.is_active.is_(True),
            )
            .first()
        )

    def termo_ocupado(self, normalizado: str) -> bool:
        return bool(
            self.s.query(ExamParentModel.id)
            .filter(ExamParentModel.name_normalized == normalizado)
            .first()
            or self.s.query(ExamVariationModel.id)
            .filter(ExamVariationModel.name_normalized == normalizado)
            .first()
        )

    def nova_variacao(self, pai_id: str, nome: str, normalizado: str, origem: str) -> None:
        variation_id = str(uuid.uuid4())
        self.s.add(
            ExamVariationModel(
                id=variation_id,
                parent_id=pai_id,
                name=nome,
                name_normalized=normalizado,
                vector_id=derivar_vector_id(variation_id),
                is_active=True,
                source=origem,
                created_at=self.agora,
                created_by=self.ator,
                updated_at=self.agora,
                updated_by=self.ator,
            )
        )

    def conflito_pendente(self, nome: str) -> Optional[ExamVariationConflictModel]:
        return (
            self.s.query(ExamVariationConflictModel)
            .filter(
                ExamVariationConflictModel.name_normalized == normalizar_termo(nome),
                ExamVariationConflictModel.resolution.is_(None),
            )
            .first()
        )

    def encerrar(self, conflito, resolucao: str, pai_id: Optional[str]) -> None:
        conflito.resolution = resolucao
        conflito.resolved_parent_id = pai_id
        conflito.resolved_at = self.agora
        conflito.resolved_by = self.ator

    # ------------------------------------------------------------------ ações

    def juntar(self, origem_nome: str, destino_nome: str) -> Dict[str, Any]:
        origem, destino = self.pai(origem_nome), self.pai(destino_nome)
        if not origem:
            raise ValueError(f"pai '{origem_nome}' não encontrado (ou inativo)")
        if not destino:
            raise ValueError(f"pai '{destino_nome}' não encontrado (ou inativo)")
        if origem.id == destino.id:
            raise ValueError("origem e destino são o mesmo exame")

        avisos = []
        if origem.status == "ativo" and destino.status != "ativo":
            avisos.append(
                f"'{origem.name}' é nome do BRNET e '{destino.name}' não: "
                "considere inverter a junção"
            )
        if origem.is_external and not destino.is_external:
            avisos.append(f"'{origem.name}' tinha flag externo; '{destino.name}' não tem")

        variacoes = (
            self.s.query(ExamVariationModel)
            .filter(ExamVariationModel.parent_id == origem.id)
            .all()
        )
        for variacao in variacoes:
            variacao.parent_id = destino.id
            variacao.updated_at = self.agora
            variacao.updated_by = self.ator

        removido = {
            "id": origem.id,
            "name": origem.name,
            "status": origem.status,
            "is_external": origem.is_external,
            "source": origem.source,
            "notes": origem.notes,
        }
        nome, normalizado = origem.name, origem.name_normalized
        # O pai sai antes de o nome voltar como variação: a árvore estrita não
        # admite o mesmo termo como pai e variação ao mesmo tempo.
        self.s.delete(origem)
        self.s.flush()
        self.nova_variacao(destino.id, nome, normalizado, "juncao_de_duplicata")
        self.s.flush()

        return {
            "variacoes_movidas": [v.name for v in variacoes],
            "pai_removido": removido,
            "destino": destino.name,
            "avisos": avisos,
        }

    def atribuir(self, termo: str, pai_nome: str) -> Dict[str, Any]:
        conflito = self.conflito_pendente(termo)
        if not conflito:
            raise ValueError(f"nenhum conflito pendente para '{termo}'")
        pai = self.pai(pai_nome)
        if not pai:
            raise ValueError(f"pai '{pai_nome}' não encontrado (ou inativo)")
        return self._atribuir(conflito, pai)

    def _atribuir(self, conflito, pai) -> Dict[str, Any]:
        atual = self.pai_do_termo(conflito.name_normalized)
        if atual and atual.id != pai.id:
            if atual.name_normalized == conflito.name_normalized:
                # O CSV de origem queria este pai como sinônimo de outro pai.
                raise ValueError(
                    f"'{conflito.name}' é ele próprio um exame pai; decida se é o mesmo "
                    f"exame que '{pai.name}' (juntar) ou descarte o conflito"
                )
            raise ValueError(f"'{conflito.name}' já está no catálogo sob '{atual.name}'")
        if atual is None:
            if self.termo_ocupado(conflito.name_normalized):
                raise ValueError(f"'{conflito.name}' ocupado por pai inativo")
            self.nova_variacao(pai.id, conflito.name, conflito.name_normalized, "conflito_resolvido")
        self.encerrar(conflito, "atribuida", pai.id)
        self.s.flush()
        return {"pai": pai.name, "variacao_criada": atual is None}

    def descartar(self, termo: str) -> Dict[str, Any]:
        conflito = self.conflito_pendente(termo)
        if not conflito:
            raise ValueError(f"nenhum conflito pendente para '{termo}'")
        self.encerrar(conflito, "descartada", None)
        self.s.flush()
        return {}

    def reavaliar_pendentes(self) -> List[Dict[str, Any]]:
        """Atribui o conflito cujos candidatos passaram a ser um exame só."""
        resultados = []
        pendentes = (
            self.s.query(ExamVariationConflictModel)
            .filter(ExamVariationConflictModel.resolution.is_(None))
            .order_by(ExamVariationConflictModel.name_normalized)
            .all()
        )
        for conflito in pendentes:
            pais = {}
            for candidato in conflito.candidate_parents or []:
                pai = self.pai_do_termo(normalizar_termo(candidato))
                pais[pai.id if pai else f"?{candidato}"] = pai
            if len(pais) == 1 and None not in pais.values():
                pai = next(iter(pais.values()))
                try:
                    detalhe = self._atribuir(conflito, pai)
                    resultados.append({"termo": conflito.name, "situacao": "atribuido_auto", **detalhe})
                except ValueError as erro:
                    resultados.append({"termo": conflito.name, "situacao": "pendente", "detalhe": str(erro)})
            else:
                nomes = sorted({p.name if p else k[1:] for k, p in pais.items()})
                resultados.append({"termo": conflito.name, "situacao": "pendente", "candidatos": nomes})
        return resultados


def ler_decisoes(caminho: str) -> List[Dict[str, str]]:
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        linhas = []
        for numero, linha in enumerate(csv.DictReader(arquivo), start=2):
            acao = (linha.get("acao") or "").strip().lower()
            if not acao or acao.startswith("#"):
                continue
            if acao not in ACOES:
                raise SystemExit(f"linha {numero}: ação '{acao}' inválida (use {sorted(ACOES)})")
            termo, pai = (linha.get("termo") or "").strip(), (linha.get("pai") or "").strip()
            if not termo or (acao != "descartar" and not pai):
                raise SystemExit(f"linha {numero}: '{acao}' exige termo{' e pai' if acao != 'descartar' else ''}")
            linhas.append({"linha": numero, "acao": acao, "termo": termo, "pai": pai})
    # Junções primeiro: são elas que fazem os conflitos convergirem.
    return sorted(linhas, key=lambda d: d["acao"] != "juntar")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve conflitos de importação do catálogo a partir de um CSV de decisões.",
        epilog="Sem --aplicar, executa tudo numa transação e desfaz no fim.",
    )
    parser.add_argument("--decisoes", required=True, help="CSV com acao,termo,pai,observacao")
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão é dry-run)")
    parser.add_argument("--ator", default="script:resolver_conflitos_catalogo")
    parser.add_argument("--json", metavar="ARQUIVO", help="salva o relatório em JSON")
    args = parser.parse_args()

    decisoes = ler_decisoes(args.decisoes)
    print(f"{len(decisoes)} decisão(ões) | {'GRAVANDO' if args.aplicar else 'DRY-RUN (use --aplicar)'}\n")

    sessao = user_db._get_session()
    catalogo = Catalogo(sessao, args.ator)
    relatorio: Dict[str, Any] = {"decisoes": [], "reavaliacao": []}
    falhas = 0
    try:
        for decisao in decisoes:
            acao, termo, pai = decisao["acao"], decisao["termo"], decisao["pai"]
            # Savepoint por decisão: uma linha errada não derruba as outras.
            ponto = sessao.begin_nested()
            try:
                if acao == "juntar":
                    detalhe = catalogo.juntar(termo, pai)
                elif acao == "atribuir":
                    detalhe = catalogo.atribuir(termo, pai)
                else:
                    detalhe = catalogo.descartar(termo)
                ponto.commit()
                situacao = "ok"
            except ValueError as erro:
                ponto.rollback()
                detalhe, situacao = {"detalhe": str(erro)}, "falhou"
                falhas += 1
            relatorio["decisoes"].append({**decisao, "situacao": situacao, **detalhe})

            marca = "+" if situacao == "ok" else "!"
            alvo = f" -> {pai}" if pai else ""
            print(f"  {marca} {acao:<9} {termo}{alvo}")
            if situacao == "falhou":
                print(f"      {detalhe['detalhe']}")
            for aviso in detalhe.get("avisos", []):
                print(f"      aviso: {aviso}")
            if detalhe.get("variacoes_movidas"):
                print(f"      {len(detalhe['variacoes_movidas'])} variação(ões) movida(s)")

        relatorio["reavaliacao"] = catalogo.reavaliar_pendentes()
        print("\nconflitos restantes, reavaliados:")
        for item in relatorio["reavaliacao"]:
            if item["situacao"] == "atribuido_auto":
                print(f"  + {item['termo']} -> {item['pai']}")
            else:
                extra = item.get("detalhe") or " | ".join(item.get("candidatos", []))
                print(f"  ? {item['termo']}  (continua pendente: {extra})")

        auto = sum(1 for i in relatorio["reavaliacao"] if i["situacao"] == "atribuido_auto")
        pendentes = len(relatorio["reavaliacao"]) - auto
        print(
            f"\ndecisões aplicadas: {len(decisoes) - falhas} | falhas: {falhas} | "
            f"atribuídos automaticamente: {auto} | ainda pendentes: {pendentes}"
        )

        if args.aplicar:
            sessao.commit()
        else:
            sessao.rollback()
            print("\n[dry-run] nada foi gravado.")
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()

    if args.aplicar:
        exam_catalog_source.invalidar()
        print("\ngravado. Reinicie o backend para o motor carregar o catálogo novo.")
        try:
            user_db.create_audit_log(
                AuditLogCreate(
                    action="exams.conflitos_resolvidos_em_lote",
                    resource="exam_variation_conflicts",
                    user_email=args.ator,
                    status_code=200,
                    metadata={
                        # Nome de exame não é PII.
                        "decisoes": [
                            {k: d.get(k) for k in ("acao", "termo", "pai", "situacao")}
                            for d in relatorio["decisoes"]
                        ],
                        "atribuidos_automaticamente": [
                            i["termo"] for i in relatorio["reavaliacao"] if i["situacao"] == "atribuido_auto"
                        ],
                    },
                )
            )
        except Exception as erro_auditoria:
            print(f"AVISO: falha ao registrar auditoria: {erro_auditoria}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as saida:
            json.dump(relatorio, saida, ensure_ascii=False, indent=2, default=str)
        print(f"Relatório em {args.json}")

    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
