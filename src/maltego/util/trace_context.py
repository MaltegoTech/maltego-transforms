import contextvars

TRACEPARENT_VAR = contextvars.ContextVar("traceparent", default="N/A")