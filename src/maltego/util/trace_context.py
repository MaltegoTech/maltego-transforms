import contextvars

TRACEPARENT_VAR = contextvars.ContextVar("traceparent", default="N/A")
# Qualified name (`<prefix>.<ns>.<name>`) of the running transform, for log lines
TRANSFORM_VAR = contextvars.ContextVar("transform", default="N/A")
