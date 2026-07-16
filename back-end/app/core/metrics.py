"""Métricas Prometheus de negócio do ProntuAI.

Expostas em /metrics quando METRICS_ENABLED=true (ver main.py).
Se prometheus_client não estiver instalado, todos os instrumentos viram no-op
para não quebrar ambientes sem a dependência.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram

    # clinica_id/clinica_nome: cardinalidade limitada ao número de clínicas
    # credenciadas (dezenas, não milhares) — diferente de request_id/user_email,
    # que são por requisição e nunca devem virar label (ver promtail-config.yml).
    DOCUMENTOS_PROCESSADOS = Counter(
        "prontuai_documentos_processados_total",
        "Documentos processados pelo workflow completo",
        ["status", "clinica_id", "clinica_nome"],
    )

    WORKFLOW_DURACAO = Histogram(
        "prontuai_workflow_duracao_segundos",
        "Duração do processamento completo do documento",
        buckets=(5, 15, 30, 60, 120, 300, 600, 1200),
    )

    OCR_DURACAO = Histogram(
        "prontuai_ocr_duracao_segundos",
        "Duração do pipeline de OCR",
        ["motor"],
        buckets=(5, 15, 30, 60, 120, 300, 600, 1200),
    )

    TEXTRACT_TIMEOUT = Counter(
        "prontuai_textract_timeout_total",
        "Timeouts do AWS Textract",
    )

    OCR_FALLBACK_DOCLING = Counter(
        "prontuai_ocr_fallback_docling_total",
        "Fallbacks do Textract para OCR local (Docling)",
    )

    PRONTUAI_API_CONSULTAS = Counter(
        "prontuai_api_consultas_total",
        "Consultas à API externa ProntuAI",
        ["resultado"],
    )

    CONFIANCA_SCORE = Histogram(
        "prontuai_confianca_score",
        "Score de confiança do documento (0-100): qualidade do OCR + cobertura dos exames obrigatórios",
        ["clinica_id", "clinica_nome"],
        buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
    )

    VALIDACAO_DOCUMENTOS = Counter(
        "prontuai_validacao_documentos_total",
        "Resultado da validação automática pela IA (aprovado | rejeitado por exames faltantes)",
        ["resultado", "clinica_id", "clinica_nome"],
    )

    REVISAO_HUMANA = Counter(
        "prontuai_revisao_humana_total",
        "Decisões do revisor humano sobre documentos (aprovado | rejeitado)",
        ["decisao", "clinica_id", "clinica_nome"],
    )

    DOCUMENTOS_ENVIADOS = Counter(
        "prontuai_documentos_enviados_total",
        "Documentos recebidos no upload, antes do processamento (workflow pode falhar depois)",
        ["clinica_id", "clinica_nome"],
    )

    CLINICAS_CRIADAS = Counter(
        "prontuai_clinicas_criadas_total",
        "Clínicas cadastradas no sistema",
    )

    # role: bounded a ADMIN/MANAGER/CHECKER/SENDER — não é PII, é papel do usuário.
    # clinica_id/clinica_nome: "sem_clinica" para ADMIN/MANAGER/CHECKER (não têm clínica).
    USUARIOS_CRIADOS = Counter(
        "prontuai_usuarios_criados_total",
        "Usuários cadastrados no sistema",
        ["role", "clinica_id", "clinica_nome"],
    )

except ImportError:  # pragma: no cover - ambiente sem prometheus_client
    logger.warning("prometheus_client não instalado; métricas de negócio desabilitadas")

    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    DOCUMENTOS_PROCESSADOS = _NoopMetric()
    WORKFLOW_DURACAO = _NoopMetric()
    OCR_DURACAO = _NoopMetric()
    TEXTRACT_TIMEOUT = _NoopMetric()
    OCR_FALLBACK_DOCLING = _NoopMetric()
    PRONTUAI_API_CONSULTAS = _NoopMetric()
    CONFIANCA_SCORE = _NoopMetric()
    VALIDACAO_DOCUMENTOS = _NoopMetric()
    REVISAO_HUMANA = _NoopMetric()
    DOCUMENTOS_ENVIADOS = _NoopMetric()
    CLINICAS_CRIADAS = _NoopMetric()
    USUARIOS_CRIADOS = _NoopMetric()
