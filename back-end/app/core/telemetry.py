import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_otel_initialized = False


def _parse_headers(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    headers: dict[str, str] = {}
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def setup_telemetry(app=None, engine=None) -> None:
    global _otel_initialized
    if _otel_initialized:
        return

    enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.info("OTEL desabilitado (OTEL_ENABLED=false)")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "prontuai-backend")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    otlp_headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))
    sampler = os.getenv("OTEL_TRACES_SAMPLER", "parentbased_traceidratio")
    sampler_arg = os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1")

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except Exception as e:
        logger.warning(f"Falha ao importar OpenTelemetry: {e}")
        return

    try:
        if sampler.lower() == "traceidratio":
            sampler_obj = TraceIdRatioBased(float(sampler_arg))
        else:
            sampler_obj = ParentBased(TraceIdRatioBased(float(sampler_arg)))

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource, sampler=sampler_obj)
        trace.set_tracer_provider(provider)

        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=otlp_headers)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTEL exportador OTLP configurado")
        else:
            logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT não definido. Traces não serão exportadas.")

        if app is not None:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("OTEL instrumentação FastAPI habilitada")

        if engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.info("OTEL instrumentação SQLAlchemy habilitada")

        _otel_initialized = True
    except Exception as e:
        logger.warning(f"Falha ao inicializar OpenTelemetry: {e}")
