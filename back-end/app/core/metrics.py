"""Métricas Prometheus de negócio do ProntuAI.

Expostas em /metrics quando METRICS_ENABLED=true (ver main.py).
Se prometheus_client não estiver instalado, todos os instrumentos viram no-op
para não quebrar ambientes sem a dependência.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram

    DOCUMENTOS_PROCESSADOS = Counter(
        "prontuai_documentos_processados_total",
        "Documentos processados pelo workflow completo",
        ["status"],
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
        buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
    )

    VALIDACAO_DOCUMENTOS = Counter(
        "prontuai_validacao_documentos_total",
        "Resultado da validação automática (completo | exames_faltantes)",
        ["resultado"],
    )

    REVISAO_HUMANA = Counter(
        "prontuai_revisao_humana_total",
        "Decisões do revisor humano sobre documentos (aprovado | rejeitado)",
        ["decisao"],
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
