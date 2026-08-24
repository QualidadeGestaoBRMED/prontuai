"""Métricas de negócio do ProntuAI (OpenTelemetry).

Os instrumentos são criados no import, via meter *proxy* da API do OTel:
enquanto `setup_telemetry()` não roda o proxy é no-op e nada é exportado;
depois ele religa nos instrumentos reais do SDK, já com as Views de buckets
declaradas em VIEWS.

Nomenclatura: os nomes aqui são os nomes *finais* no Prometheus menos os
sufixos que o otel-collector acrescenta sozinho (`_total` nos contadores,
`_bucket`/`_sum`/`_count` nos histogramas). É por isso que os contadores não
levam `_total` aqui e que os histogramas de tempo carregam `_segundos` no
próprio nome e ficam sem unidade OTel — declarar unit="s" faria o collector
acrescentar mais um `_seconds` e quebraria os painéis existentes.

clinica_id/clinica_nome: cardinalidade limitada ao número de clínicas
credenciadas (dezenas, não milhares) — diferente de request_id/user_email,
que são por requisição e nunca devem virar atributo (ver promtail-config.yml).
"""
import logging

logger = logging.getLogger(__name__)

# Buckets de latência HTTP recomendados pelo semconv, usados no lado servidor
# e no cliente.
LAT = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10)

# Views aplicadas ao MeterProvider (montadas em telemetry.py). "buckets" vira
# ExplicitBucketHistogramAggregation; "descartar" vira DropAggregation.
# "meter_name" restringe a View a um escopo de instrumentação — e quando duas
# Views casam com o mesmo instrumento, AMBAS se aplicam, então restringir uma
# exige restringir a outra também.
VIEWS: tuple[dict, ...] = (
    {"instrument_name": "prontuai_workflow_duracao_segundos",
     "buckets": (5, 15, 30, 60, 120, 300, 600, 1200)},
    {"instrument_name": "prontuai_ocr_duracao_segundos",
     "buckets": (5, 15, 30, 60, 120, 300, 600, 1200)},
    {"instrument_name": "prontuai_confianca_score",
     "buckets": (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)},

    # Latência HTTP da instrumentação do FastAPI. Os buckets vêm do "advice" do
    # semconv, mas SDKs mais antigos ignoram o advice e caem nos buckets default
    # (0..10000) — que, para um histograma em segundos, jogam todo o tráfego no
    # primeiro bucket e zeram a utilidade do painel de p95. Declarar aqui deixa
    # o resultado igual em qualquer versão suportada.
    {"instrument_name": "http.server.request.duration", "buckets": LAT},

    # Latência das chamadas HTTP de saída. Restrita ao escopo do httpx porque é
    # o único cliente que o código usa (brmed_service.py, API ProntuAI).
    {"instrument_name": "http.client.request.duration",
     "meter_name": "opentelemetry.instrumentation.httpx", "buckets": LAT},

    # A instrumentação do requests emite ESTA MESMA métrica, com os mesmos
    # atributos. Dois escopos convivem bem no SDK, mas o exporter Prometheus do
    # collector achata o escopo: as duas séries ficam idênticas e uma sobrescreve
    # a outra, perdendo ~50% das amostras sem erro nenhum. Descartar a métrica do
    # escopo requests custa zero hoje (nenhuma chamada no código usa requests) e
    # não afeta os spans dele, que continuam sendo gerados.
    {"instrument_name": "http.client.request.duration",
     "meter_name": "opentelemetry.instrumentation.requests", "descartar": True},

    # Duração de corrotinas e de asyncio.to_thread. Precisa de faixa muito mais
    # larga que a de HTTP: o to_thread do OCR roda por minutos, enquanto a
    # maioria das corrotinas termina em milissegundos.
    {"instrument_name": "asyncio.process.duration",
     "buckets": (0.005, 0.05, 0.5, 1, 5, 15, 60, 300, 1200)},
)

try:
    from opentelemetry import metrics as _otel_metrics
    from opentelemetry.metrics import Observation

    _meter = _otel_metrics.get_meter("prontuai.negocio")

    # Heartbeat: substitui o `up{job="prontuai-backend"}` do modelo de scrape.
    # Como o backend agora empurra métricas, a ausência da série no Prometheus
    # (após o metric_expiration do collector) é o sinal de "fora do ar" — e um
    # gauge sempre-1 garante que a série exista mesmo sem tráfego algum.
    BACKEND_UP = _meter.create_observable_gauge(
        "prontuai_backend_up",
        callbacks=[lambda options: [Observation(1)]],
        description="1 enquanto o processo do backend está exportando métricas",
    )

    DOCUMENTOS_PROCESSADOS = _meter.create_counter(
        "prontuai_documentos_processados",
        description="Documentos processados pelo workflow completo",
    )

    WORKFLOW_DURACAO = _meter.create_histogram(
        "prontuai_workflow_duracao_segundos",
        description="Duração do processamento completo do documento",
    )

    OCR_DURACAO = _meter.create_histogram(
        "prontuai_ocr_duracao_segundos",
        description="Duração do pipeline de OCR",
    )

    TEXTRACT_TIMEOUT = _meter.create_counter(
        "prontuai_textract_timeout",
        description="Timeouts do AWS Textract",
    )

    OCR_FALLBACK_DOCLING = _meter.create_counter(
        "prontuai_ocr_fallback_docling",
        description="Fallbacks do Textract para OCR local (Docling)",
    )

    PRONTUAI_API_CONSULTAS = _meter.create_counter(
        "prontuai_api_consultas",
        description="Consultas à API externa ProntuAI",
    )

    CONFIANCA_SCORE = _meter.create_histogram(
        "prontuai_confianca_score",
        description="Score de confiança do documento (0-100): qualidade do OCR + cobertura dos exames obrigatórios",
    )

    VALIDACAO_DOCUMENTOS = _meter.create_counter(
        "prontuai_validacao_documentos",
        description="Resultado da validação automática pela IA (aprovado | rejeitado por exames faltantes)",
    )

    REVISAO_HUMANA = _meter.create_counter(
        "prontuai_revisao_humana",
        description="Decisões do revisor humano sobre documentos (aprovado | rejeitado)",
    )

    DOCUMENTOS_ENVIADOS = _meter.create_counter(
        "prontuai_documentos_enviados",
        description="Documentos recebidos no upload, antes do processamento (workflow pode falhar depois)",
    )

    CLINICAS_CRIADAS = _meter.create_counter(
        "prontuai_clinicas_criadas",
        description="Clínicas cadastradas no sistema",
    )

    # role: bounded a ADMIN/MANAGER/CHECKER/SENDER — não é PII, é papel do usuário.
    # clinica_id/clinica_nome: "sem_clinica" para ADMIN/MANAGER/CHECKER (não têm clínica).
    USUARIOS_CRIADOS = _meter.create_counter(
        "prontuai_usuarios_criados",
        description="Usuários cadastrados no sistema",
    )

except ImportError:  # pragma: no cover - ambiente sem opentelemetry-api
    logger.warning("opentelemetry-api não instalado; métricas de negócio desabilitadas")

    class _NoopInstrument:
        def add(self, *args, **kwargs):
            pass

        def record(self, *args, **kwargs):
            pass

    BACKEND_UP = _NoopInstrument()
    DOCUMENTOS_PROCESSADOS = _NoopInstrument()
    WORKFLOW_DURACAO = _NoopInstrument()
    OCR_DURACAO = _NoopInstrument()
    TEXTRACT_TIMEOUT = _NoopInstrument()
    OCR_FALLBACK_DOCLING = _NoopInstrument()
    PRONTUAI_API_CONSULTAS = _NoopInstrument()
    CONFIANCA_SCORE = _NoopInstrument()
    VALIDACAO_DOCUMENTOS = _NoopInstrument()
    REVISAO_HUMANA = _NoopInstrument()
    DOCUMENTOS_ENVIADOS = _NoopInstrument()
    CLINICAS_CRIADAS = _NoopInstrument()
    USUARIOS_CRIADOS = _NoopInstrument()
