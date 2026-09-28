#!/usr/bin/env python3
"""
Reprocessa a etapa de comparação de exames dos documentos que falharam NELA.

Contexto: até o commit 9847611, `app/core/clients.py` mantinha um único
`AsyncOpenAI` criado no import, enquanto `v1_brmed._run_background_job_in_thread`
roda cada job em `asyncio.run()` numa thread nova — e `asyncio.run` fecha o loop
ao terminar. O job seguinte reaproveitava conexão TLS de um loop morto e a
comparação morria com `APIConnectionError`. Medido em staging (24/set/2026):
10 de 20 documentos.

O estrago em cada documento é sempre o mesmo, e é o que este script desfaz:
`validar_exames` cai no early-return de erro e devolve `exames_comparativo: []`,
então o documento fica **sem nenhum exame na tabela de comparação**, com
`status: "error"` e confiança baixa — como se a IA tivesse achado problema,
quando ela nem chegou a comparar.

POR QUE NÃO REPROCESSAR O DOCUMENTO INTEIRO
    Não é preciso, e sair pelo upload seria pior. A trava de duplicidade que
    devolve resultado pronto para arquivo idêntico vive só no handler HTTP
    (`app/api/v1_brmed.py`, os blocos de `get_document_by_hash` e da janela de
    dedup, ~linhas 466-547). Este script não sobe arquivo: lê o documento,
    re-executa a comparação e grava com `update_document` na MESMA linha. Nunca
    passa perto da dedup, não cria documento novo e não precisa fingir nada.

    E o OCR não precisa rodar de novo: ele usa o cliente `OpenAI` **síncrono**,
    que não depende de event loop e por isso nunca foi afetado. O markdown, os
    exames do OCR e os exames do BRNET já estão no banco. Reaproveitá-los evita
    Textract, evita nova consulta ao BRNET e — o que mais importa — garante que a
    comparação nova rode sobre exatamente a mesma entrada da que falhou.

O QUE O SCRIPT NÃO TOCA
    A decisão humana. Se alguém já aprovou ou rejeitou o documento na checagem,
    `validation_status`, `reviewed_by` e as justificativas ficam como estão: o
    script preenche a comparação que faltava e nada mais. Documento revisado só
    entra com `--incluir-revisados`, e mesmo então a decisão é preservada.

SELETOR (estreito de propósito)
    Só entra documento cujo erro é o da comparação E que tem `exams_ocr` e
    `exams_brnet` preenchidos. A checagem dos dois arrays não é redundante: no
    banco de dev, 598 documentos têm comparativo vazio e só 2 falharam na
    comparação — os outros 596 falharam ANTES (paciente não encontrado, CNPJ
    inválido, expedição em aberto inexistente) e nunca chegaram a ter exame
    obrigatório para comparar. Reprocessar a comparação deles não faz nada, e
    varrer por "comparativo vazio" arrastaria os 596 junto.

    O texto do erro varia entre "Event loop is closed" e "Connection error."
    conforme a exceção que chega ao `except` — as duas são a mesma falha, então o
    filtro é pelo prefixo `Erro ao comparar exames (fallback):`.

REQUISITOS DE EXECUÇÃO
    Rode de dentro do container do back-end (ou de um ambiente equivalente):
    a comparação usa o índice FAISS assinado, logo precisa dos artefatos
    `exam_similarity_*` E de `ARTIFACT_SIGNING_KEY` batendo, além de
    `OPENAI_API_KEY` e `DATABASE_URL`.

    `validar_exames` chama `salvar_auditoria`, que grava
    `auditoria_validacao/validacao_<cpf>_<ts>.json` relativo ao cwd — CPF no nome
    do arquivo. É o mesmo comportamento do processamento normal, não uma exposição
    nova, mas rode do mesmo cwd da aplicação para os arquivos caírem onde já caem.

USO
    # ver o que seria feito, sem gravar (padrão)
    python scripts/reprocessar_comparacao.py --todos

    # os documentos de um paciente específico
    python scripts/reprocessar_comparacao.py --doc <uuid> --doc <uuid>

    # gravar
    python scripts/reprocessar_comparacao.py --todos --aplicar
"""
import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.core.database import user_db  # noqa: E402
from app.core.pii import mask_identifier  # noqa: E402
from app.models.audit_log import AuditLogCreate  # noqa: E402
from app.services import validacao_service, workflow_service  # noqa: E402

PREFIXO_ERRO = "Erro ao comparar exames (fallback):"

# Mesma consulta do seletor descrito no topo. Fica em SQL porque não há método de
# repositório que busque por conteúdo do payload, e um `SELECT *` em Python
# traria os 4861 documentos para a memória para descartar quase todos.
SQL_CANDIDATOS = """
SELECT d.id
FROM documents d
WHERE d.result_payload IS NOT NULL
  AND (d.result_payload::jsonb) ->> 'erro' LIKE :prefixo
  AND coalesce(array_length(d.exams_ocr, 1), 0) > 0
  AND coalesce(array_length(d.exams_brnet, 1), 0) > 0
  AND d.archived_at IS NULL
ORDER BY d.uploaded_at DESC
LIMIT :limite
"""


def _payload(document) -> Dict[str, Any]:
    """`result_payload` volta do repositório como dict ou como texto JSON."""
    bruto = document.result_payload
    if isinstance(bruto, dict):
        return bruto
    if isinstance(bruto, str) and bruto.strip():
        try:
            carregado = json.loads(bruto)
            return carregado if isinstance(carregado, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _revisado(document, payload: Dict[str, Any]) -> bool:
    """Mesma regra do `_revisado_por_humano` do feedback: a coluna não basta.

    Em parte da base o revisor está só no `result_payload`, de antes de a coluna
    `reviewed_by` passar a ser preenchida.
    """
    if document.reviewed_by:
        return True
    return bool(payload.get("reviewed_by") or payload.get("reviewedBy"))


def _elegivel(document, payload: Dict[str, Any]) -> Optional[str]:
    """Devolve o motivo da recusa, ou None se o documento pode ser reprocessado.

    Revalida em Python o que o SQL já filtrou, porque `--doc` entra sem passar
    pela consulta: é o caminho que alguém usa às pressas, com um id colado do
    e-mail, e é justamente onde um documento errado apareceria.
    """
    erro = payload.get("erro")
    if not (isinstance(erro, str) and erro.startswith(PREFIXO_ERRO)):
        return f"erro não é o da comparação (erro={erro!r})"
    if not (document.exams_ocr or payload.get("exames_ocr")):
        return "sem exames do OCR para comparar"
    if not (document.exams_brnet or payload.get("exames_brnet")):
        return "sem exames do BRNET — a falha foi antes da comparação"
    return None


def _recalcular_confianca(
    payload: Dict[str, Any],
    resultado: Dict[str, Any],
    exames_ocr: List[str],
    markdown: str,
) -> Dict[str, Any]:
    """Refaz confiança e `analysis_details` com as funções do próprio pipeline.

    Reaproveita as fórmulas de `_processar_documento_completo_impl` em vez de
    copiá-las: se a ponderação mudar lá, o reprocessamento acompanha.

    `quality` e `field_checks` saem do markdown, que a falha não afetou, então
    são recalculados e batem com o que já estava salvo. Só `match_confidence`
    dependia da comparação — foi calculado sobre lista vazia e por isso saiu
    vazio.
    """
    linhas = workflow_service._extrair_linhas_markdown(markdown or "")
    comparativo = resultado.get("exames_comparativo", [])

    analysis_details = dict(payload.get("analysis_details") or {})
    analysis_details["quality"] = workflow_service._avaliar_qualidade(markdown or "", linhas)
    analysis_details["field_checks"] = workflow_service._avaliar_campos(
        markdown or "", linhas, payload.get("patient_name")
    )
    analysis_details["match_confidence"] = workflow_service._avaliar_confianca_exames(
        comparativo, exames_ocr, linhas
    )

    obrigatorios_total = len([e for e in comparativo if e.get("status") != "extra_no_ocr"])
    obrigatorios_encontrados = len([e for e in comparativo if e.get("status") == "encontrado"])
    cobertura = obrigatorios_encontrados / obrigatorios_total if obrigatorios_total else 0.0
    quality_score = analysis_details["quality"]["score"]
    score = round((quality_score * 0.4) + (cobertura * 100 * 0.6))

    return {
        "analysis_details": analysis_details,
        "confidence_score": score,
        "confidence_details": {
            "score": score,
            "quality_score": quality_score,
            "mandatory_coverage": round(cobertura, 4),
            "mandatory_found": obrigatorios_encontrados,
            "mandatory_total": obrigatorios_total,
        },
    }


def _montar_payload(
    payload: Dict[str, Any], resultado: Dict[str, Any], confianca: Dict[str, Any]
) -> Dict[str, Any]:
    """Payload novo = o antigo com os campos da comparação preenchidos.

    Parte do payload existente de propósito: ele carrega CPF, nome, dados do
    BRNET e `reviewed_by` que não têm nada a ver com a falha. Reconstruir do zero
    perderia isso — e `update_document` relê `reviewed_by` do payload, então
    apagá-lo de lá desfaria a decisão humana.
    """
    comparativo = resultado["exames_comparativo"]
    novo = dict(payload)
    novo.update(
        {
            "tabela_comparacao": comparativo,
            "decisao_final": resultado["mensagem"],
            "analise_comparacao": resultado.get("analise_ia") or resultado.get("mensagem"),
            "validation_result": {
                "exames_faltantes": [e["exame"] for e in comparativo if e["status"] == "faltante"],
                "exames_extras": [e["exame"] for e in comparativo if e["status"] == "extra_no_ocr"],
                "analysis": resultado["mensagem"],
            },
            "erro": None,
            "status": "success",
            **confianca,
        }
    )
    # Marca a origem do dado: sem isso, um comparativo preenchido hoje é
    # indistinguível de um que sempre esteve certo, e a medição de acurácia do
    # período contaminado fica sem como excluir estes documentos.
    novo["reprocessado_por"] = "scripts/reprocessar_comparacao.py"
    novo["reprocessado_motivo"] = payload.get("erro")
    return novo


async def _reprocessar(document_id: str, aplicar: bool, incluir_revisados: bool) -> Dict[str, Any]:
    document = user_db.get_document_by_id(document_id)
    if not document:
        return {"id": document_id, "situacao": "nao_encontrado"}

    payload = _payload(document)
    recusa = _elegivel(document, payload)
    if recusa:
        return {"id": document_id, "situacao": "inelegivel", "detalhe": recusa}

    revisado = _revisado(document, payload)
    if revisado and not incluir_revisados:
        return {
            "id": document_id,
            "situacao": "revisado_ignorado",
            "detalhe": "já tem decisão humana; use --incluir-revisados",
        }

    exames_ocr = list(document.exams_ocr or payload.get("exames_ocr") or [])
    exames_brnet = list(document.exams_brnet or payload.get("exames_brnet") or [])
    identificador = (
        document.cpf
        or payload.get("identificador_consulta")
        or payload.get("passaporte_processado")
        or "NAO_ENCONTRADO"
    )

    base = {
        "id": document_id,
        "paciente": mask_identifier(identificador),
        "n_ocr": len(exames_ocr),
        "n_brnet": len(exames_brnet),
        "revisado": revisado,
    }

    # `exames_ocr` já vem filtrado por `_filtrar_exames_ocr` de quando o
    # documento foi processado — é exatamente a lista que a comparação recebeu.
    # Refiltrar aqui mudaria a entrada e o reprocessamento deixaria de ser
    # comparável com a execução original.
    resultado = await validacao_service.validar_exames(
        cpf=identificador,
        exames_obrigatorios=exames_brnet,
        exames_enviados=exames_ocr,
        exames_brnet=exames_brnet,
    )

    if resultado.get("erro"):
        # Falhou de novo. Não grava nada: sobrescrever o payload com um erro novo
        # só apagaria o rastro do erro original sem melhorar o documento.
        return {**base, "situacao": "falhou_de_novo", "detalhe": resultado["erro"]}

    confianca = _recalcular_confianca(payload, resultado, exames_ocr, document.ocr_markdown or "")
    comparativo = resultado["exames_comparativo"]
    resumo = {
        **base,
        "situacao": "ok" if aplicar else "ok_dry_run",
        "encontrados": len([e for e in comparativo if e["status"] == "encontrado"]),
        "faltantes": len([e for e in comparativo if e["status"] == "faltante"]),
        "extras": len([e for e in comparativo if e["status"] == "extra_no_ocr"]),
        "liberado": resultado["status_liberado"],
        "confianca_antes": payload.get("confidence_score"),
        "confianca_depois": confianca["confidence_score"],
    }
    if not aplicar:
        return resumo

    novo_payload = _montar_payload(payload, resultado, confianca)
    detalhes = confianca["confidence_details"]

    # `validation_status` fica de fora quando há decisão humana: o comparativo
    # entra, a decisão não se mexe.
    campos = {
        "result_payload": novo_payload,
        "exams_found": resultado.get("exames_presentes") or [],
        "confidence_score": confianca["confidence_score"],
        "quality_score": detalhes["quality_score"],
        "mandatory_coverage": detalhes["mandatory_coverage"],
    }
    if not revisado:
        campos["validation_status"] = "pending"

    user_db.update_document(document_id=document_id, **campos)

    try:
        user_db.create_audit_log(
            AuditLogCreate(
                action="documents.comparacao_reprocessada",
                resource="documents",
                resource_id=document_id,
                user_email="script:reprocessar_comparacao",
                status_code=200,
                metadata={
                    # Nome de exame não é PII; CPF e nome do paciente não entram.
                    "erro_original": payload.get("erro"),
                    "exames_encontrados": resumo["encontrados"],
                    "exames_faltantes": resumo["faltantes"],
                    "status_liberado": resultado["status_liberado"],
                    "confianca_antes": payload.get("confidence_score"),
                    "confianca_depois": confianca["confidence_score"],
                    "decisao_humana_preservada": revisado,
                },
            )
        )
    except Exception as erro_auditoria:  # auditoria não derruba o reprocessamento
        resumo["aviso_auditoria"] = str(erro_auditoria)

    return resumo


def _candidatos(limite: int) -> List[str]:
    with user_db.engine.connect() as conexao:
        linhas = conexao.execute(
            text(SQL_CANDIDATOS), {"prefixo": f"{PREFIXO_ERRO}%", "limite": limite}
        ).fetchall()
    return [linha[0] for linha in linhas]


def _preflight_indice(permitir_sem_indice: bool) -> Optional[str]:
    """Recusa reprocessar sem o índice de similaridade carregado.

    `validacao_service` valida a assinatura HMAC dos artefatos no import e, se ela
    não bater, deixa `exam_similarity_index = None` e segue — a comparação passa a
    rodar SEM o contexto RAG, com qualidade pior, e nada no resultado denuncia
    isso. Num reprocessamento é o pior desfecho possível: grava comparativo
    degradado sobre o documento e ainda apaga o erro que sinalizava o problema.
    Medido no container de dev, onde `ARTIFACT_SIGNING_KEY` não bate com os
    artefatos: a comparação "funciona" e ninguém percebe.
    """
    if validacao_service.exam_similarity_index is not None:
        return None
    recado = (
        "índice de similaridade de exames NÃO carregado (assinatura HMAC inválida "
        "ou artefato ausente) — a comparação rodaria sem contexto RAG"
    )
    if permitir_sem_indice:
        print(f"AVISO: {recado}. Prosseguindo por --sem-indice.\n")
        return None
    return recado


async def _executar(args: argparse.Namespace) -> int:
    impedimento = _preflight_indice(args.sem_indice)
    if impedimento:
        print(f"ABORTADO: {impedimento}.")
        print("Rode de onde os artefatos validam, ou assuma o risco com --sem-indice.")
        return 2

    ids = list(args.doc or [])
    if args.todos:
        ids.extend(i for i in _candidatos(args.limite) if i not in ids)

    if not ids:
        print("Nenhum documento a reprocessar.")
        return 0

    print(f"{len(ids)} documento(s) | {'GRAVANDO' if args.aplicar else 'DRY-RUN (use --aplicar)'}\n")

    resultados = []
    for indice, document_id in enumerate(ids, start=1):
        # Sequencial de propósito: a comparação é uma chamada à OpenAI por
        # documento, e um lote concorrente grande só troca este bug por rate
        # limit. O volume real é de dezenas, não de milhares.
        resultado = await _reprocessar(document_id, args.aplicar, args.incluir_revisados)
        resultados.append(resultado)
        situacao = resultado["situacao"]
        if situacao.startswith("ok"):
            print(
                f"[{indice}/{len(ids)}] {document_id} {resultado['paciente']} "
                f"encontrados={resultado['encontrados']} faltantes={resultado['faltantes']} "
                f"extras={resultado['extras']} liberado={resultado['liberado']} "
                f"confianca={resultado['confianca_antes']}->{resultado['confianca_depois']}"
                + ("  [decisão humana preservada]" if resultado["revisado"] else "")
            )
        else:
            print(f"[{indice}/{len(ids)}] {document_id} {situacao}: {resultado.get('detalhe', '')}")

    print()
    contagem: Dict[str, int] = {}
    for resultado in resultados:
        contagem[resultado["situacao"]] = contagem.get(resultado["situacao"], 0) + 1
    for situacao, quantos in sorted(contagem.items()):
        print(f"  {situacao}: {quantos}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as saida:
            json.dump(resultados, saida, ensure_ascii=False, indent=2)
        print(f"\nRelatório em {args.json}")

    # Falha só quando o reprocessamento não deu conta; documento inelegível ou
    # revisado-ignorado é decisão do script, não erro.
    return 1 if contagem.get("falhou_de_novo") or contagem.get("nao_encontrado") else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reprocessa a comparação de exames dos documentos que falharam nessa etapa.",
        epilog="Sem --aplicar não grava nada.",
    )
    parser.add_argument("--doc", action="append", metavar="ID", help="documento (repetível)")
    parser.add_argument("--todos", action="store_true", help="varre pelo erro da comparação")
    parser.add_argument("--limite", type=int, default=50, help="máximo em --todos (padrão: 50)")
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão é dry-run)")
    parser.add_argument(
        "--incluir-revisados",
        dest="incluir_revisados",
        action="store_true",
        help="inclui documentos já revisados; a decisão humana é preservada",
    )
    parser.add_argument(
        "--sem-indice",
        dest="sem_indice",
        action="store_true",
        help="prossegue mesmo sem o índice de similaridade (comparação degradada)",
    )
    parser.add_argument("--json", metavar="ARQUIVO", help="salva o relatório em JSON")
    args = parser.parse_args()

    if not args.doc and not args.todos:
        parser.error("informe --doc ou --todos")

    return asyncio.run(_executar(args))


if __name__ == "__main__":
    sys.exit(main())
