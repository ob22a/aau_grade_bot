from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Attach a request-scoped correlation ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        correlation_id = _correlation_id.get()
        record.correlation_id = correlation_id or "-"
        return True


def set_correlation_id(value: str | None = None) -> str:
    if value is None:
        value = str(uuid.uuid4())
    _correlation_id.set(value)
    return value


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def configure_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [cid=%(correlation_id)s] %(message)s"
    )

    handler_exists = any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
    if not handler_exists:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(CorrelationIdFilter())
        root_logger.addHandler(handler)
