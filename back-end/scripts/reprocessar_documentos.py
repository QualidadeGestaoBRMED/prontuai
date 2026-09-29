"""
Reprocessa documentos que falharam por erro do sistema, retomando o pipeline na
etapa em que a falha ocorreu.

Ferramenta de plantão: sempre que uma falha nossa deixar documentos com resultado
inútil, é por aqui que eles voltam — sem reenvio pela clínica e sem passar pela
trava de duplicidade.

POR QUE ETAPAS, E NÃO UM "REPROCESSAR TUDO"
    Cada etapa do pipeline precisa de uma entrada diferente, e o que sobrevive no
    banco decide o que é possível:

      etapa      precisa de                        disponível?
      ---------  --------------------------------  -------------------------
      ocr        o PDF original                    NÃO (ver abaixo)
      brnet      identificador + ocr_markdown      sim, 100% dos documentos
      comparacao exams_ocr + exams_brnet           sim, 4265 de 4861

    `--etapa ocr` não existe de propósito: `file_path` está preenchido em 100%
    das linhas, mas o arquivo não está mais lá. Medido no banco de dev: 12 PDFs
    em `data/uploads/` para 4861 documentos — a coluna mente. Falha de OCR só se
    resolve com reenvio do documento, e o script diz isso em vez de tentar.

    `--etapa brnet` reconsulta a fonte externa e segue até o fim (filtra os exames
    do OCR e compara). Serve para a família de erros que é transitória por
    natureza: paciente que ainda não estava cadastrado, expedição que ainda não
    tinha sido aberta, indisponibilidade da API.

    `--etapa comparacao` refaz só a comparação, a partir do que já está no banco.
    O OCR não precisa rodar: ele usa o cliente `OpenAI` **síncrono** e por isso
    nunca sofreu do bug de event loop que motivou este script.

O QUE NUNCA É TOCADO
    - A decisão humana. Documento já aprovado/rejeitado na checagem só entra com
      `--incluir-revisados`, e mesmo então `validation_status` e `reviewed_by`
      ficam fora do update: o comparativo é preenchido, a decisão fica.
    - Quem enviou. `uploaded_by_user_id`, `uploaded_by_user_email`, `clinic_id`,
      `filename`, `uploaded_at` e `content_hash` não vão no update em nenhum
      caminho.
    - O documento original. Nada é recriado: o update cai na MESMA linha, então a
      dedup do handler de upload (`app/api/v1_brmed.py`, blocos de
      `get_document_by_hash` e da janela de dedup) nunca entra em cena.

SELEÇÃO POR ERRO
    Cada etapa tem os padrões de erro que ela sabe consertar, e `--erro` permite
    informar outro (LIKE do Postgres, repetível). O casamento é revalidado em
    Python documento por documento, não só no SQL — `--doc` não passa pela
    consulta, e é justamente o caminho de quem cola um id às pressas.

    `--listar-erros` mostra a distribuição dos erros no banco com a etapa capaz de
    tratar cada um. É por aí que se começa quando o erro é novo.

    Erro que o script se recusa a tratar não é limitação, é a proteção principal:
    no dev, 596 de 598 documentos com comparativo vazio falharam ANTES da
    comparação. Reprocessar a comparação deles não faria nada e sobrescreveria o
    erro que explica cada caso.

REQUISITOS DE EXECUÇÃO
    Rode de dentro do container do back-end. A comparação usa o índice FAISS
    assinado, logo precisa dos artefatos `exam_similarity_*` com assinatura
    batendo com `ARTIFACT_SIGNING_KEY`, além de `OPENAI_API_KEY` e `DATABASE_URL`.
    `--etapa brnet` precisa também das credenciais da API externa.

    `validar_exames` chama `salvar_auditoria`, que grava
    `auditoria_validacao/validacao_<cpf>_<ts>.json` relativo ao cwd — CPF no nome
    do arquivo. É o mesmo comportamento do processamento normal, mas rode do
    mesmo cwd da aplicação para os arquivos caírem onde já caem.

USO
    python scripts/reprocessar_documentos.py --listar-erros
    python scripts/reprocessar_documentos.py --todos                      # dry-run
    python scripts/reprocessar_documentos.py --todos --etapa brnet
    python scripts/reprocessar_documentos.py --todos --aplicar
    python scripts/reprocessar_documentos.py --doc <uuid> --erro 'Timeout%'
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
from app.services import (  # noqa: E402
    brmed_service,
    validacao_service,
    workflow_service,
)

# ── catálogo de etapas ──────────────────────────────────────────────────────
#
# Cada etapa declara os erros que sabe consertar. Os padrões são LIKE do Postgres
# e foram tirados do que existe no banco, não imaginados: rodar `--listar-erros`
# mostra a distribuição real e qual etapa cobre cada linha.
#
# ETAPA_OCR não existe: o PDF não sobrevive (12 arquivos em disco para 4861
# documentos no dev). Os erros dessa família estão em ERROS_SEM_CONSERTO, para o
# script explicar por que não os trata em vez de ficar calado.

ETAPA_COMPARACAO = "comparacao"
ETAPA_BRNET = "brnet"

PADROES_COMPARACAO = [
    # O mesmo bug aparece com dois textos, conforme a exceção que chega ao
    # `except` de `comparar_exames_com_rag`: "Event loop is closed" e
    # "Connection error.". Filtrar pelo prefixo pega os dois.
    "Erro ao comparar exames (fallback):%",
    # Segundo early-return de `validar_exames`: o LLM devolveu formato inesperado.
    # Estrago idêntico (comparativo vazio), conserto idêntico.
    "formato_de_resposta_invalido",
    "Erro ao validar exames:%",
]

PADROES_BRNET = [
    # Família transitória: o paciente é cadastrado depois, a expedição é aberta
    # depois, a API volta. Reconsultar resolve; nada disso é culpa do documento.
    "Paciente não encontrado%",
    "Expedição em aberto não encontrada%",
    "Integração com ProntuAI API não configurada%",
    "Não foi possível consultar exames obrigatórios%",
    "cnpj é obrigatório%",
    "cpf ou passaporte é obrigatório%",
    "cpf deve conter%",
]

# Erros cujo conserto NÃO é reprocessar, e que o script recusa explicitamente.
# Ficam aqui para `--listar-erros` dizer o que fazer com eles.
ERROS_SEM_CONSERTO = {
    "Não foi possível extrair": (
        "identificador não sai do markdown; a extração é regex determinística, "
        "então reprocessar devolve o mesmo resultado — precisa de reenvio ou de "
        "correção manual do CPF"
    ),
    "Erro no OCR": "falha de leitura do PDF, e o PDF não sobrevive — precisa de reenvio",
    "Erro no processamento": "falha genérica de OCR/processamento — precisa de reenvio",
}

ETAPAS = {
    ETAPA_COMPARACAO: {
        "descricao": "refaz só a comparação, a partir de exams_ocr + exams_brnet",
        "padroes": PADROES_COMPARACAO,
    },
    ETAPA_BRNET: {
        "descricao": "reconsulta a fonte externa e segue até a comparação",
        "padroes": PADROES_BRNET,
    },
}

# Fica em SQL porque não há método de repositório que busque por conteúdo do
# payload, e um `SELECT *` em Python traria os 4861 documentos para a memória
# para descartar quase todos. A elegibilidade por etapa é revalidada depois, em
# `_elegivel`, para `--doc` receber a mesma checagem.
SQL_CANDIDATOS = """
SELECT d.id
FROM documents d
WHERE d.result_payload IS NOT NULL
  AND d.archived_at IS NULL
  AND EXISTS (
    SELECT 1 FROM unnest(CAST(:padroes AS text[])) AS padrao
    WHERE (d.result_payload::jsonb) ->> 'erro' LIKE padrao
  )
ORDER BY d.uploaded_at DESC
LIMIT :limite
"""

SQL_DISTRIBUICAO_ERROS = """
SELECT (result_payload::jsonb) ->> 'erro' AS erro,
       count(*) AS quantos,
       count(*) FILTER (WHERE coalesce(array_length(exams_brnet, 1), 0) > 0) AS com_brnet,
       count(*) FILTER (WHERE reviewed_by IS NOT NULL) AS revisados
FROM documents
WHERE result_payload IS NOT NULL
  AND archived_at IS NULL
  AND (result_payload::jsonb) ->> 'erro' IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
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


def _like(padrao: str, valor: str) -> bool:
    """LIKE do Postgres em Python, para revalidar o mesmo padrão fora do SQL."""
    import re as _re

    regex = "".join(
        ".*" if ch == "%" else "." if ch == "_" else _re.escape(ch) for ch in padrao
    )
    return _re.fullmatch(regex, valor, flags=_re.DOTALL) is not None


def _casa_algum(padroes: List[str], erro: Optional[str]) -> bool:
    return isinstance(erro, str) and any(_like(p, erro) for p in padroes)


def _motivo_sem_conserto(erro: Optional[str]) -> Optional[str]:
    if not isinstance(erro, str):
        return None
    for marcador, explicacao in ERROS_SEM_CONSERTO.items():
        if marcador in erro:
            return explicacao
    return None


def _elegivel(
    document, payload: Dict[str, Any], etapa: str, padroes: List[str]
) -> Optional[str]:
    """Devolve o motivo da recusa, ou None se o documento pode ser reprocessado.

    Revalida em Python o que o SQL já filtrou, porque `--doc` entra sem passar
    pela consulta: é o caminho que alguém usa às pressas, com um id colado do
    e-mail, e é justamente onde um documento errado apareceria.

    A recusa é a função principal daqui, não um detalhe: no dev, 596 de 598
    documentos com comparativo vazio falharam antes da comparação.
    """
    erro = payload.get("erro")

    sem_conserto = _motivo_sem_conserto(erro)
    if sem_conserto:
        return f"não se resolve reprocessando: {sem_conserto}"

    if not _casa_algum(padroes, erro):
        return f"erro fora dos padrões da etapa {etapa} (erro={erro!r})"

    if not document.ocr_markdown:
        # Sem o markdown não há como refiltrar nem reavaliar qualidade, e o PDF
        # não volta. Vale para as duas etapas.
        return "sem ocr_markdown — só reenvio resolve"

    if etapa == ETAPA_COMPARACAO:
        if not (document.exams_ocr or payload.get("exames_ocr")):
            return "sem exames do OCR para comparar"
        if not (document.exams_brnet or payload.get("exames_brnet")):
            return "sem exames do BRNET — a falha foi antes da comparação; tente --etapa brnet"
        return None

    if etapa == ETAPA_BRNET:
        if not _identificadores(document, payload):
            return "sem CPF, passaporte ou CNPJ para consultar a fonte externa"
        return None

    return f"etapa desconhecida: {etapa}"


def _identificadores(document, payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """CPF, passaporte e CNPJ para reconsultar a fonte externa.

    Saem do payload, que é onde o pipeline guarda o que ELE usou na consulta que
    falhou — reextrair do markdown daria o mesmo resultado (a extração é regex
    determinística) e ainda arriscaria divergir.
    """
    def limpo(valor: Any) -> Optional[str]:
        if not isinstance(valor, str):
            return None
        valor = valor.strip()
        # O pipeline grava esta string literal quando não achou identificador.
        if not valor or valor in {"Não encontrado", "NAO_ENCONTRADO"}:
            return None
        return valor

    identificadores = {
        "cpf": limpo(payload.get("cpf_processado")) or limpo(document.cpf),
        "passaporte": limpo(payload.get("passaporte_processado")),
        "cnpj": limpo(payload.get("cnpj_processado")),
    }
    return {k: v for k, v in identificadores.items() if v}


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
    payload: Dict[str, Any],
    resultado: Dict[str, Any],
    confianca: Dict[str, Any],
    brnet: Optional[Dict[str, Any]] = None,
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
    novo["reprocessado_por"] = "scripts/reprocessar_documentos.py"
    novo["reprocessado_motivo"] = payload.get("erro")

    # Na etapa `brnet` a consulta trouxe exigência, nome e dados da expedição
    # novos — são justamente o que faltava, então substituem o que estava lá.
    if brnet:
        novo["exames_brnet"] = brnet.get("exames") or []
        novo["fonte_exames_obrigatorios"] = brnet.get("source") or "prontuai_api"
        novo["tipo_identificador_consulta"] = brnet.get("tipo_identificador_consulta")
        novo["identificador_consulta"] = brnet.get("identificador_consulta")
        if brnet.get("cpf_processado"):
            novo["cpf_processado"] = brnet["cpf_processado"]
            novo["cpf"] = brnet["cpf_processado"]
        if brnet.get("passaporte_processado"):
            novo["passaporte_processado"] = brnet["passaporte_processado"]
        if brnet.get("nome"):
            novo["patient_name"] = brnet["nome"]
        novo["brmed_result"] = {
            "exames_obrigatorios": brnet.get("exames") or [],
            "source": brnet.get("source") or "prontuai_api",
            "pedido_exame_id": brnet.get("pedido_exame_id"),
            "tipo_pedido_exame": brnet.get("tipo_pedido_exame"),
            "data_previsao_liberacao": brnet.get("data_previsao_liberacao"),
            "atendimento_realizado_em": brnet.get("atendimento_realizado_em"),
        }
        novo["exames_ocr"] = resultado["_exames_ocr_usados"]
        novo["ocr_result"] = {
            **(payload.get("ocr_result") or {}),
            "exames_extraidos": resultado["_exames_ocr_usados"],
        }

    # Campo interno do script, não faz parte do contrato do payload.
    novo.pop("_exames_ocr_usados", None)
    return novo


async def _obter_exames_brnet(
    document, payload: Dict[str, Any], etapa: str
) -> tuple[Optional[List[str]], Optional[Dict[str, Any]], Optional[str]]:
    """Devolve (exames_brnet, resposta_da_consulta, erro).

    Na etapa `comparacao` reaproveita o que está no banco. Na `brnet` reconsulta a
    fonte externa — é o ponto de toda a etapa, já que o erro dela foi exatamente
    essa consulta ter falhado.
    """
    if etapa == ETAPA_COMPARACAO:
        guardados = list(document.exams_brnet or payload.get("exames_brnet") or [])
        return guardados, None, None

    identificadores = _identificadores(document, payload)
    resposta = await brmed_service.consultar_exames_prontuai(
        cpf=identificadores.get("cpf"),
        passaporte=identificadores.get("passaporte"),
        cnpj=identificadores.get("cnpj"),
    )
    if "erro" in resposta:
        return None, None, f"fonte externa: {resposta['erro']}"
    exames = resposta.get("exames") or []
    if not exames:
        # Consulta respondeu sem exigência nenhuma. Gravar isso zeraria o
        # comparativo e o documento ficaria "liberado" por ausência de regra —
        # pior que o erro atual.
        return None, None, "fonte externa respondeu sem exames obrigatórios"
    return exames, resposta, None


async def _reprocessar(
    document_id: str,
    aplicar: bool,
    incluir_revisados: bool,
    etapa: str,
    padroes: List[str],
) -> Dict[str, Any]:
    document = user_db.get_document_by_id(document_id)
    if not document:
        return {"id": document_id, "situacao": "nao_encontrado"}

    payload = _payload(document)
    recusa = _elegivel(document, payload, etapa, padroes)
    if recusa:
        return {"id": document_id, "situacao": "inelegivel", "detalhe": recusa}

    revisado = _revisado(document, payload)
    if revisado and not incluir_revisados:
        return {
            "id": document_id,
            "situacao": "revisado_ignorado",
            "detalhe": "já tem decisão humana; use --incluir-revisados",
        }

    markdown = document.ocr_markdown or ""
    identificador = (
        document.cpf
        or payload.get("identificador_consulta")
        or payload.get("passaporte_processado")
        or "NAO_ENCONTRADO"
    )
    base = {
        "id": document_id,
        "etapa": etapa,
        "paciente": mask_identifier(identificador),
        "revisado": revisado,
    }

    exames_brnet, brnet, erro_brnet = await _obter_exames_brnet(document, payload, etapa)
    if erro_brnet:
        return {**base, "situacao": "falhou_de_novo", "detalhe": erro_brnet}

    if etapa == ETAPA_COMPARACAO:
        # `exames_ocr` já vem filtrado por `_filtrar_exames_ocr` de quando o
        # documento foi processado — é exatamente a lista que a comparação
        # recebeu. Refiltrar aqui mudaria a entrada e o reprocessamento deixaria
        # de ser comparável com a execução original.
        exames_ocr = list(document.exams_ocr or payload.get("exames_ocr") or [])
    else:
        # Na etapa `brnet` a exigência mudou, e o filtro do OCR depende dela: o
        # portão de extração é o catálogo mais os nomes que o BRNET pede. Refiltrar
        # é obrigatório, e roda sobre o markdown CRU — `varrer_markdown` recupera
        # do markdown exame que o filtro anterior havia descartado por não estar
        # na exigência antiga.
        exames_ocr = workflow_service._filtrar_exames_ocr(
            list(document.exams_ocr or payload.get("exames_ocr") or []),
            exames_brnet,
            markdown,
        )

    base.update({"n_ocr": len(exames_ocr), "n_brnet": len(exames_brnet or [])})

    if not exames_ocr:
        return {**base, "situacao": "inelegivel", "detalhe": "nenhum exame do OCR após o filtro"}

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

    confianca = _recalcular_confianca(payload, resultado, exames_ocr, markdown)
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

    resultado["_exames_ocr_usados"] = exames_ocr
    novo_payload = _montar_payload(payload, resultado, confianca, brnet)
    detalhes = confianca["confidence_details"]

    # `validation_status` fica de fora quando há decisão humana: o comparativo
    # entra, a decisão não se mexe. `uploaded_by_*`, `clinic_id`, `filename`,
    # `uploaded_at` e `content_hash` não vão em nenhum caminho.
    campos = {
        "result_payload": novo_payload,
        "exams_found": resultado.get("exames_presentes") or [],
        "confidence_score": confianca["confidence_score"],
        "quality_score": detalhes["quality_score"],
        "mandatory_coverage": detalhes["mandatory_coverage"],
    }
    if etapa == ETAPA_BRNET:
        # A exigência mudou; as colunas que a espelham precisam acompanhar, senão
        # a tela e o payload divergem.
        campos["exams_brnet"] = exames_brnet
        campos["exams_ocr"] = exames_ocr
    if not revisado:
        campos["validation_status"] = "pending"

    user_db.update_document(document_id=document_id, **campos)

    try:
        user_db.create_audit_log(
            AuditLogCreate(
                action="documents.reprocessado",
                resource="documents",
                resource_id=document_id,
                user_email="script:reprocessar_documentos",
                status_code=200,
                metadata={
                    # Nome de exame não é PII; CPF e nome do paciente não entram.
                    "etapa": etapa,
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


def _candidatos(padroes: List[str], limite: int) -> List[str]:
    with user_db.engine.connect() as conexao:
        linhas = conexao.execute(
            text(SQL_CANDIDATOS), {"padroes": list(padroes), "limite": limite}
        ).fetchall()
    return [linha[0] for linha in linhas]


def _listar_erros() -> int:
    """Distribuição dos erros no banco, com a etapa capaz de tratar cada um.

    É o ponto de partida quando o erro é novo: em vez de adivinhar um padrão, olha
    o que existe, quantos documentos são, quantos já têm decisão humana e qual
    etapa resolve. Só leitura.
    """
    with user_db.engine.connect() as conexao:
        linhas = conexao.execute(text(SQL_DISTRIBUICAO_ERROS)).fetchall()

    if not linhas:
        print("Nenhum documento com erro registrado.")
        return 0

    print(f"{'erro':<62} {'docs':>5} {'brnet':>6} {'rev':>4}  tratável por")
    print("-" * 104)
    for erro, quantos, com_brnet, revisados in linhas:
        texto = (erro or "")[:60]
        sem_conserto = _motivo_sem_conserto(erro)
        if sem_conserto:
            tratavel = f"— ({sem_conserto[:44]})"
        else:
            etapas = [
                nome for nome, cfg in ETAPAS.items() if _casa_algum(cfg["padroes"], erro)
            ]
            tratavel = " ou ".join(f"--etapa {e}" for e in etapas) if etapas else "— (padrão não mapeado; use --erro)"
        print(f"{texto:<62} {quantos:>5} {com_brnet:>6} {revisados:>4}  {tratavel}")

    print()
    print("docs = documentos com esse erro | brnet = quantos têm exigência do BRNET")
    print("rev  = quantos já têm decisão humana (ficam de fora sem --incluir-revisados)")
    return 0


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
    if args.listar_erros:
        return _listar_erros()

    etapa = args.etapa
    # `--erro` substitui os padrões da etapa em vez de somar: quem informa um erro
    # específico quer aquele, e somar traria a varredura inteira de carona.
    padroes = list(args.erro) if args.erro else list(ETAPAS[etapa]["padroes"])

    impedimento = _preflight_indice(args.sem_indice)
    if impedimento:
        print(f"ABORTADO: {impedimento}.")
        print("Rode de onde os artefatos validam, ou assuma o risco com --sem-indice.")
        return 2

    ids = list(args.doc or [])
    if args.todos:
        ids.extend(i for i in _candidatos(padroes, args.limite) if i not in ids)

    if not ids:
        print(f"Nenhum documento a reprocessar na etapa {etapa}.")
        print("Use --listar-erros para ver o que existe no banco.")
        return 0

    print(f"etapa: {etapa} — {ETAPAS[etapa]['descricao']}")
    print(f"padrões: {', '.join(padroes)}")
    print(f"{len(ids)} documento(s) | {'GRAVANDO' if args.aplicar else 'DRY-RUN (use --aplicar)'}\n")

    resultados = []
    for indice, document_id in enumerate(ids, start=1):
        # Sequencial de propósito: cada documento é pelo menos uma chamada à
        # OpenAI (e na etapa brnet também uma à API externa). Um lote concorrente
        # grande só troca este problema por rate limit. O volume real é de dezenas.
        resultado = await _reprocessar(
            document_id, args.aplicar, args.incluir_revisados, etapa, padroes
        )
        resultados.append(resultado)
        situacao = resultado["situacao"]
        if situacao.startswith("ok"):
            print(
                f"[{indice}/{len(ids)}] {document_id} {resultado['paciente']} "
                f"ocr={resultado['n_ocr']} brnet={resultado['n_brnet']} "
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
        description=(
            "Reprocessa documentos que falharam por erro do sistema, retomando o "
            "pipeline na etapa em que a falha ocorreu."
        ),
        epilog=(
            "Sem --aplicar não grava nada. Comece por --listar-erros. "
            "Não há --etapa ocr: o PDF original não sobrevive, então falha de "
            "leitura só se resolve com reenvio do documento."
        ),
    )
    parser.add_argument(
        "--etapa",
        choices=sorted(ETAPAS),
        default=ETAPA_COMPARACAO,
        help="; ".join(f"{nome}: {cfg['descricao']}" for nome, cfg in ETAPAS.items()),
    )
    parser.add_argument(
        "--erro",
        action="append",
        metavar="PADRÃO",
        help="padrão LIKE do erro (repetível); substitui os padrões da etapa",
    )
    parser.add_argument(
        "--listar-erros",
        dest="listar_erros",
        action="store_true",
        help="mostra os erros do banco e a etapa que trata cada um; não grava nada",
    )
    parser.add_argument("--doc", action="append", metavar="ID", help="documento (repetível)")
    parser.add_argument("--todos", action="store_true", help="varre pelos padrões da etapa")
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

    if not args.listar_erros and not args.doc and not args.todos:
        parser.error("informe --doc, --todos ou --listar-erros")

    return asyncio.run(_executar(args))


if __name__ == "__main__":
    sys.exit(main())
