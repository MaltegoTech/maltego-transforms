# Copyright (c) Maltego Technologies GmbH.
import logging
from logging.config import dictConfig
from typing import Any, Dict

from pydantic import BaseModel
from uvicorn.logging import DefaultFormatter

from maltego.util.trace_context import TRACEPARENT_VAR


def get_current_traceparent():
    value = TRACEPARENT_VAR.get()
    if not value or value == "N/A":
        return ""
    parts = value.split("-")
    return f"TraceId: {parts[1]}" if len(parts) >= 2 else ""


class TraceparentFilter(logging.Filter):
    def filter(self, record):
        is_access = record.name.startswith("uvicorn.access")
        if is_access or record.levelno >= logging.ERROR:
            record.traceparent = get_current_traceparent()
        else:
            record.traceparent = ""
        return True


class ConditionalTraceFormatter(DefaultFormatter):
    """
    Drop traceparent column if empty
    """

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.full_fmt = fmt
        self.no_tp_fmt = fmt.replace(" | %(traceparent)s", "")

    def format(self, record):
        self._style._fmt = self.full_fmt if record.traceparent else self.no_tp_fmt
        return super().format(record)


class LogConfig(BaseModel):
    """Logging configuration to be set for the server"""

    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(name)20s | %(traceparent)s | %(message)s"
    ACCESS_LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(name)20s | %(traceparent)s | %(message)s"
    LOG_LEVEL: str = "INFO"

    # Logging config
    version: int = 1
    disable_existing_loggers: bool = False
    formatters: Dict[str, Dict[str, str]] = {
        "default": {
            "()": "maltego.config.ConditionalTraceFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            "()": "maltego.config.ConditionalTraceFormatter",
            "fmt": ACCESS_LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    filters: Dict[str, Dict[str, str]] = {
        "traceparent_filter": {
            "()": "maltego.config.TraceparentFilter"
        }
    }
    handlers: Dict[str, Dict[str, Any]] = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "filters": ["traceparent_filter"]
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "filters": ["traceparent_filter"]
        },
    }
    loggers: Dict[str, Dict[str, Any]] = {
        "root": {"handlers": ["default"], "level": LOG_LEVEL},
        "uvicorn.access": {
            "handlers": ["access"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    }


def get_logging_config(level: str) -> LogConfig:
    log_config = LogConfig()
    if hasattr(log_config, "LOG_LEVEL"):
        setattr(log_config, "LOG_LEVEL", level)
    log_config.loggers["root"]["level"] = level
    dictConfig(log_config.model_dump())
    return log_config
