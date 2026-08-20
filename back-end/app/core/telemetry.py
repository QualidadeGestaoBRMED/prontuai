"""Telemetria OpenTelemetry do ProntuAI: traces e métricas via OTLP.

Substitui o prometheus-fastapi-instrumentator — o backend não expõe mais
/metrics. As métricas são empurradas por OTLP para o otel-collector
(ops/observability/otel-collector.yml), que as republica em :8889/metrics
para o Prometheus coletar.

Toda a configuração é feita pelas variáveis de ambiente padrão do OTel, não
por parâmetro: identidade (OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES),
destino (OTEL_EXPORTER_OTLP_ENDPOINT e cia), sampling (OTEL_TRACES_SAMPLER),
limites de atributo e o kill switch (OTEL_SDK_DISABLED). Ver
ops/observability/backend-env.example para o conjunto completo.

FORK: este módulo monta os providers no import, o que só é seguro porque o
gunicorn carrega `main:app` dentro de cada worker, depois do fork (é o padrão
quando `--preload` não é usado — ver entrypoint.sh). A thread do
BatchSpanProcessor não sobrevive a um fork: se algum dia `--preload` for
ligado, os workers ficam sem telemetria ou travam, e o setup precisa migrar
para um hook `post_fork` num gunicorn.conf.py.
"""
import os

# Precisa valer antes de qualquer import do OTel: o SDK e as instrumentações
# leem estas variáveis no momento do import/instrumentação. São todas
# variáveis padrão do OTel, então o .env sempre vence o default daqui.
_PADROES = {
    # Sem o opt-in, a instrumentação emite o semconv antigo e rotula as
    # métricas HTTP com http.target — o caminho cru (/v1/documents/<uuid>),
    # uma série nova por documento. Com ele o rótulo é http.route, o template.
    "OTEL_SEMCONV_STABILITY_OPT_IN": "http",
    # Vira o rótulo job= das séries no Prometheus, via resource OTel.
    "OTEL_SERVICE_NAME": "prontuai-backend",
    # O healthcheck do container bate /health a cada 30s: ruído puro nos
    # painéis de tráfego.
    "OTEL_PYTHON_EXCLUDED_URLS": "health,healthz,readyz,livez,metrics",
    # 15s para casar com o scrape_interval do Prometheus. O default do OTel
    # (60s) faria o Prometheus coletar o mesmo valor quatro vezes seguidas.
    "OTEL_METRIC_EXPORT_INTERVAL": "15000",
}
for _chave, _valor in _PADROES.items():
    os.environ.setdefault(_chave, _valor)

import logging
import socket

from app.core.metrics import VIEWS

logger = logging.getLogger(__name__)

_otel_initialized = False
_providers: list = []

# Sem endpoint não há para onde exportar, e o default do SDK
# (http://localhost:4318) só geraria retry perpétuo. Estas são as variáveis
# que os exporters consultam, em ordem de precedência.
_ENDPOINT_VARS = (
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


# Instrumentações que não precisam de argumento. A lista saiu do
# `opentelemetry-bootstrap -a requirements` rodado sobre o requirements.txt
# deste projeto, filtrada para o que é de fato usado aqui.
_INSTRUMENTACOES = (
    # (nome, módulo, classe)
    ("requests", "opentelemetry.instrumentation.requests", "RequestsInstrumentor"),
    ("httpx", "opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
    ("botocore", "opentelemetry.instrumentation.botocore", "BotocoreInstrumentor"),
    ("redis", "opentelemetry.instrumentation.redis", "RedisInstrumentor"),
    ("threading", "opentelemetry.instrumentation.threading", "ThreadingInstrumentor"),
    ("asyncio", "opentelemetry.instrumentation.asyncio", "AsyncioInstrumentor"),
)


def _desligado(variavel: str, padrao: str = "false") -> bool:
    return os.getenv(variavel, padrao).strip().lower() == "true"


def _desabilitadas() -> set[str]:
    """Nomes listados em OTEL_PYTHON_DISABLED_INSTRUMENTATIONS.

    É a variável padrão do OTel para desligar uma instrumentação específica sem
    mexer em código — útil quando uma delas passa a brigar com uma dependência.
    Como as outras OTEL_PYTHON_*, só é honrada pela auto-instrumentação, então
    a leitura aqui é explícita. Vale para os nomes de _INSTRUMENTACOES e também
    para "fastapi", "sqlalchemy" e "logging".
    """
    bruto = os.getenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "")
    return {n.strip().lower() for n in bruto.split(",") if n.strip()}


def _instrumentar_simples(desabilitadas: set[str]) -> None:
    from importlib import import_module

    for nome, modulo, classe in _INSTRUMENTACOES:
        if nome in desabilitadas:
            logger.info(f"OTEL instrumentação {nome} desabilitada por variável de ambiente")
            continue
        try:
            getattr(import_module(modulo), classe)().instrument()
            logger.info(f"OTEL instrumentação {nome} habilitada")
        except Exception as e:
            # Falha isolada: uma instrumentação incompatível não pode derrubar
            # as outras nem a exportação das métricas de negócio.
            logger.warning(f"Falha na instrumentação {nome}: {e}")


def _exportador_ligado(sinal: str) -> bool:
    """Lê OTEL_{TRACES,METRICS}_EXPORTER: "otlp" (padrão) ou "none".

    O SDK só honra estas variáveis pelo caminho da auto-instrumentação
    (`opentelemetry-instrument`); com providers montados à mão, como aqui, a
    checagem tem que ser explícita.
    """
    return os.getenv(f"OTEL_{sinal}_EXPORTER", "otlp").strip().lower() not in ("none", "")


def _usa_grpc() -> bool:
    return os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").strip().lower().startswith("grpc")


def _span_exporter():
    if _usa_grpc():
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    # Endpoint, headers, compressão e timeout saem das variáveis padrão.
    return OTLPSpanExporter()


def _log_exporter():
    if _usa_grpc():
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    else:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    return OTLPLogExporter()


def _metric_exporter():
    if _usa_grpc():
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    return OTLPMetricExporter()


def _build_resource():
    from opentelemetry.sdk.resources import Resource

    # service.name, service.namespace, service.version e
    # deployment.environment.name vêm de OTEL_SERVICE_NAME e
    # OTEL_RESOURCE_ATTRIBUTES, que o próprio Resource.create() lê.
    #
    # service.instance.id fica no código porque precisa do PID: com WORKERS>1
    # cada worker do gunicorn exporta seus próprios contadores e, com o mesmo
    # instance, as séries colidiriam no collector. O default do SDK seria um
    # UUID aleatório — único, mas ilegível na hora de depurar.
    return Resource.create({"service.instance.id": f"{socket.gethostname()}-{os.getpid()}"})


def _setup_traces(resource, exportar: bool) -> None:
    """Registra o TracerProvider; só exporta se OTEL_TRACES_EXPORTER != none.

    O provider é criado mesmo sem exportador porque é dele que sai o trace_id
    que a correlação de logs injeta em cada linha: sem TracerProvider o span
    corrente é o INVALID_SPAN e o campo nunca apareceria.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # TracerProvider() sozinho lê OTEL_TRACES_SAMPLER, OTEL_TRACES_SAMPLER_ARG
    # e os OTEL_*_LIMIT; BatchSpanProcessor lê os OTEL_BSP_*.
    provider = TracerProvider(resource=resource)
    if exportar:
        provider.add_span_processor(BatchSpanProcessor(_span_exporter()))
    trace.set_tracer_provider(provider)
    _providers.append(provider)
    logger.info(
        "OTEL traces exportando via OTLP"
        if exportar
        else "OTEL traces não exportadas (OTEL_TRACES_EXPORTER=none); spans servem só para correlacionar logs"
    )


def _setup_metrics(resource) -> None:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import (
        DropAggregation,
        ExplicitBucketHistogramAggregation,
        View,
    )

    views = []
    for spec in VIEWS:
        spec = dict(spec)
        buckets = spec.pop("buckets", None)
        descartar = spec.pop("descartar", False)
        agregacao = (
            DropAggregation() if descartar else ExplicitBucketHistogramAggregation(buckets)
        )
        views.append(View(aggregation=agregacao, **spec))
    # O intervalo sai de OTEL_METRIC_EXPORT_INTERVAL, lido pelo próprio reader.
    reader = PeriodicExportingMetricReader(_metric_exporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader], views=views)
    metrics.set_meter_provider(provider)
    _providers.append(provider)
    logger.info("OTEL métricas exportando via OTLP")


def _setup_logs(resource) -> None:
    """Exporta os logs por OTLP, sem parar de escrever o arquivo local.

    Os dois caminhos coexistem de proposito: o arquivo é a fonte operacional
    (e pega log de crash, que nao sobrevive ao flush do exportador), e o OTLP é
    o caminho correlacionado, que chega ao Loki com trace_id. Ninguem le o
    arquivo — nao ha promtail/filelog — entao um app.log grande nao pesa mais
    na maquina, so ocupa disco (limitado por LOG_FILE_MAX_BYTES).

    O nivel deste handler é independente do arquivo: subir OTEL_LOG_LEVEL é o
    botao para cortar volume na rede sem perder detalhe no disco.
    """
    import logging as _logging

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(_log_exporter()))

    nivel = os.getenv("OTEL_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = LoggingHandler(
        level=getattr(_logging, nivel, _logging.INFO), logger_provider=provider
    )
    _logging.getLogger().addHandler(handler)
    _providers.append(provider)
    logger.info(f"OTEL logs exportando via OTLP (nivel {nivel})")


def setup_telemetry(app=None, engine=None) -> None:
    global _otel_initialized
    if _otel_initialized:
        return

    if os.getenv("OTEL_ENABLED"):
        logger.warning(
            "OTEL_ENABLED foi substituído pelo kill switch padrão do OTel: "
            "use OTEL_SDK_DISABLED=true para desligar. O valor atual está sendo ignorado."
        )

    # Kill switch padrão: desliga a telemetria inteira sem redeploy de código.
    # O SDK também o honra por dentro, mas o return aqui evita subir as threads
    # de exportação e abrir conexão para nada.
    if _desligado("OTEL_SDK_DISABLED"):
        logger.info("OTEL desligado por OTEL_SDK_DISABLED=true")
        return

    if not any(os.getenv(var) for var in _ENDPOINT_VARS):
        logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT não definido; traces e métricas não serão exportados")
        return

    try:
        resource = _build_resource()
        _setup_traces(resource, exportar=_exportador_ligado("TRACES"))
        if _exportador_ligado("METRICS"):
            _setup_metrics(resource)
        else:
            logger.info("OTEL métricas desligadas por OTEL_METRICS_EXPORTER=none")
        if _exportador_ligado("LOGS"):
            _setup_logs(resource)
        else:
            logger.info("OTEL logs desligados por OTEL_LOGS_EXPORTER=none")
        _otel_initialized = True
    except Exception as e:
        logger.warning(f"Falha ao inicializar OpenTelemetry: {e}")
        return

    # Cada instrumentação é opcional e falha isolada: sem isso, um pacote de
    # instrumentação ausente ou incompatível derrubaria também a exportação
    # das métricas de negócio, que não depende de nenhuma das duas.
    desabilitadas = _desabilitadas()
    _instrumentar_simples(desabilitadas)

    if app is not None and "fastapi" not in desabilitadas:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            # Emite http.server.request.duration (histograma em segundos,
            # rotulado por http.route/http.request.method/http.response.status_code),
            # que é o que substitui o http_requests_total do instrumentator.
            # As rotas excluídas vêm de OTEL_PYTHON_EXCLUDED_URLS.
            FastAPIInstrumentor.instrument_app(app)
            logger.info("OTEL instrumentação FastAPI habilitada")
        except Exception as e:
            logger.warning(f"Falha na instrumentação FastAPI: {e}")

    if "logging" not in desabilitadas and os.getenv("OTEL_PYTHON_LOG_CORRELATION", "true").strip().lower() == "true":
        try:
            from opentelemetry.instrumentation.logging import LoggingInstrumentor

            # set_logging_format=False é obrigatório: com True (que é o que a
            # variável OTEL_PYTHON_LOG_CORRELATION faz por conta própria na
            # auto-instrumentação) o instrumentor chama logging.basicConfig e
            # substitui os handlers JSON montados por setup_logging().
            #
            # inject_trace_context=True é o que de fato acrescenta
            # otelTraceID/otelSpanID ao LogRecord — sem ele o instrumentor não
            # injeta nada. O JsonFormatter renomeia esses campos para
            # trace_id/span_id e descarta os vazios (ver app/core/logging.py).
            LoggingInstrumentor().instrument(
                set_logging_format=False,
                inject_trace_context=True,
            )
            logger.info("OTEL correlação de logs habilitada (trace_id nas linhas de log)")
        except Exception as e:
            logger.warning(f"Falha na correlação de logs: {e}")

    if engine is not None and "sqlalchemy" not in desabilitadas:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.info("OTEL instrumentação SQLAlchemy habilitada")
        except Exception as e:
            logger.warning(f"Falha na instrumentação SQLAlchemy: {e}")


def shutdown_telemetry() -> None:
    """Descarrega spans e métricas pendentes antes do processo morrer.

    Sem isso, o último intervalo de exportação (até 15s de contadores) é
    perdido em todo restart/deploy.
    """
    for provider in _providers:
        try:
            provider.shutdown()
        except Exception as e:
            logger.warning(f"Falha ao encerrar provider OTEL: {e}")
