import logging
import os
import json
import contextvars
from datetime import datetime

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
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
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
