import logging
import os
import json
import contextvars
from datetime import datetime
from logging.handlers import RotatingFileHandler

request_id_ctx = contextvars.ContextVar("request_id", default=None)
user_context_ctx = contextvars.ContextVar("user_context", default={})
audit_context_ctx = contextvars.ContextVar("audit_context", default={})
audit_logged_ctx = contextvars.ContextVar("audit_logged", default=False)


def set_request_context(request_id: str | None) -> None:
    request_id_ctx.set(request_id)


def set_user_context(user: object | None) -> None:
    if not user:
        user_context_ctx.set({})
        return
    user_context_ctx.set(
        {
            "user_id": getattr(user, "id", None),
            "user_email": getattr(user, "email", None),
            "user_role": getattr(user, "role", None).value if getattr(user, "role", None) else None,
            "clinic_id": getattr(user, "clinic_id", None),
        }
    )


def clear_context() -> None:
    request_id_ctx.set(None)
    user_context_ctx.set({})
    audit_context_ctx.set({})
    audit_logged_ctx.set(False)


def get_request_id() -> str | None:
    return request_id_ctx.get()


def get_user_context() -> dict:
    return user_context_ctx.get() or {}


def set_audit_context(data: dict | None) -> None:
    audit_context_ctx.set(data or {})


def get_audit_context() -> dict:
    return audit_context_ctx.get() or {}


def mark_audit_logged(value: bool = True) -> None:
    audit_logged_ctx.set(value)


def was_audit_logged() -> bool:
    return bool(audit_logged_ctx.get())


class ContextoDaRequisicaoFilter(logging.Filter):
    """Copia o contexto da requisição para dentro do LogRecord.

    O JsonFormatter lê os contextvars direto, mas o handler OTLP (que exporta os
    logs para o coletor) só enxerga o que está no record. Sem isto os logs
    chegariam ao Loki sem request_id e sem user_email — justamente os campos
    pelos quais o dashboard de exploração filtra.

    É um Filter, e não uma fábrica de LogRecord, de propósito. A fábrica roda na
    CRIAÇÃO do record, antes de `extra=` ser aplicado; quando alguém loga com
    extra={"request_id": ...} — como main.py fazia no audit — o logging levanta
    KeyError("Attempt to overwrite 'request_id' in LogRecord") e a linha se
    perde. O Filter roda depois, e o hasattr abaixo faz o `extra` explícito
    vencer em vez de colidir.
    """

    CAMPOS = ("user_id", "user_email", "user_role", "clinic_id")

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_ctx.get()
        if request_id and not hasattr(record, "request_id"):
            record.request_id = request_id
        contexto = user_context_ctx.get() or {}
        for chave in self.CAMPOS:
            valor = contexto.get(chave)
            if valor is not None and not hasattr(record, chave):
                setattr(record, chave, valor)
        return True


class JsonFormatter(logging.Formatter):
    RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }

    # Campos que o LoggingInstrumentor injeta em todo LogRecord. São tratados à
    # parte (renomeados para trace_id/span_id, e descartados quando não há span
    # ativo) em vez de caírem no loop genérico abaixo, que os copiaria crus:
    # otelTraceID="0" e otelTraceSampled=false em cada linha, mais um
    # otelServiceName que só repete o label job= do Loki.
    OTEL_CAMPOS = {
        "otelTraceID": "trace_id",
        "otelSpanID": "span_id",
        "otelTraceSampled": None,
        "otelServiceName": None,
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        user_context = user_context_ctx.get() or {}
        for key, value in user_context.items():
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key in self.RESERVED or key.startswith("_"):
                continue
            if key in self.OTEL_CAMPOS:
                destino = self.OTEL_CAMPOS[key]
                # "0" é o valor que o instrumentor usa quando não há span ativo
                # (log de startup, background job fora de requisição).
                if destino and value and value != "0":
                    payload[destino] = value
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

def setup_logging(log_file: str = "logs/app.log"):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "plain").lower()
    no_timestamp = os.getenv("LOG_NO_TIMESTAMP", "false").lower() == "true"
    quiet_loggers = [
        name.strip() for name in os.getenv("QUIET_LOGGERS", "").split(",") if name.strip()
    ]
    # Rotacao: o FileHandler puro cresce sem limite. Com os logs indo por OTLP
    # para o collector, nada mais le este arquivo, mas ele continua sendo a
    # fonte operacional local (e onde caem os logs de crash, que nao passam
    # pelo flush do exportador) — entao precisa de teto.
    max_bytes = int(os.getenv("LOG_FILE_MAX_BYTES", str(50 * 1024 * 1024)))
    backup_count = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))
    handlers = [
        RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ]
    # O filtro vai em cada handler, nao no logger: filtro de logger so vale para
    # records criados por aquele logger, e nao para os que sobem por propagacao.
    for handler in handlers:
        handler.addFilter(ContextoDaRequisicaoFilter())

    if log_format == "json":
        formatter = JsonFormatter()
        for handler in handlers:
            handler.setFormatter(formatter)
        logging.basicConfig(level=log_level, handlers=handlers)
    else:
        if log_format == "bare" or no_timestamp:
            fmt = "%(levelname)s %(name)s: %(message)s"
        else:
            fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        logging.basicConfig(
            level=log_level,
            format=fmt,
            handlers=handlers,
        )

    for logger_name in quiet_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

# Exemplo de uso:
# from app.core.logging import setup_logging
# setup_logging()
# logger = logging.getLogger(__name__)
# logger.info("Mensagem de log") 
