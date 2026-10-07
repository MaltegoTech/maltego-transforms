## Purpose

The transform server starts, serves, and cleans up expired executions without
depending on `fastapi-restful`, while its protocol serialization and
`FastAPI` application configuration stay unchanged.

## ADDED Requirements

### Requirement: Application startup completes and cleanup runs periodically

Entering the `MaltegoTransformServer` application lifespan MUST complete
startup without waiting for the expired-execution cleanup loop. While the
application runs, the server MUST call `runner.cleanup()` once every
`scheduled_cleanup_seconds`, with the first call after one full interval. An
exception raised by one cleanup call MUST be logged and MUST NOT stop later
calls. On shutdown, the server MUST stop the cleanup loop before calling
`runner.shutdown()` and closing the authentication validator, and MUST run
that shutdown sequence even when the application exits with an error.

#### Scenario: Startup completes under a real ASGI server
- **WHEN** a server is started with uvicorn
- **THEN** startup completes, the server listens, and `GET /health` returns
  200.

#### Scenario: Cleanup runs after each interval
- **WHEN** a server with `scheduled_cleanup_seconds=1` has been running for
  more than one second
- **THEN** `runner.cleanup()` has been called at least once.

#### Scenario: A failing cleanup does not stop the loop
- **WHEN** one `runner.cleanup()` call raises an exception
- **THEN** the exception is logged and the next interval calls
  `runner.cleanup()` again.

#### Scenario: Shutdown stops the loop
- **WHEN** the application lifespan exits
- **THEN** the cleanup loop is cancelled and awaited, then
  `runner.shutdown()` runs and the authentication validator is closed.

### Requirement: Protocol models keep their camelCase aliases

Every v3 protocol model MUST serialize and publish its OpenAPI schema with the
same aliases as before this change. A field alias MUST be produced by
title-casing the snake_case field name, removing each underscore that follows
an ASCII letter or digit and precedes an uppercase letter or digit, then
lowercasing the first uppercase letter after any leading underscores. Protocol
models MUST accept input by alias or by field name, and MUST support
validation from object attributes.

#### Scenario: Snake_case fields use camelCase aliases
- **WHEN** a model with `display_name` and `type_ids` fields is serialized by
  alias
- **THEN** the keys are `displayName` and `typeIds`.

#### Scenario: Digits and existing capitals follow the title-case rule
- **WHEN** aliases are generated for `maltego_v3_transform_discovery_message`
  and `transformSettings`
- **THEN** the aliases are `maltegoV3TransformDiscoveryMessage` and
  `transformsettings`.

#### Scenario: Input by field name is accepted
- **WHEN** a protocol model is validated from a mapping keyed by snake_case
  field names
- **THEN** validation succeeds with the same values as the camelCase input.

### Requirement: FastAPI application settings keep their environment behavior

The server MUST construct its `FastAPI` application from the `API_DEBUG`,
`API_TITLE`, `API_VERSION`, `API_OPENAPI_URL`, `API_OPENAPI_PREFIX`, and
`API_DISABLE_DOCS` environment variables, matched case-insensitively, with
defaults `False`, `"FastAPI"`, `"0.1.0"`, `"/openapi.json"`, `""`, and
`False`. `API_OPENAPI_PREFIX` MUST set the application root path.
`API_DISABLE_DOCS` MUST disable the OpenAPI URL. The server MUST always
disable the FastAPI docs and ReDoc URLs. The environment MUST be read each
time a server is constructed, and an invalid value MUST fail construction with
a validation error.

#### Scenario: Defaults without environment variables
- **WHEN** a server is constructed without `API_*` variables
- **THEN** the application has `debug=False`, `title="FastAPI"`,
  `version="0.1.0"`, `openapi_url="/openapi.json"`, `root_path=""`, and no
  docs or ReDoc URL.

#### Scenario: Environment overrides
- **WHEN** `API_DEBUG=true` and `API_OPENAPI_PREFIX=/pfx` are set before a
  server is constructed
- **THEN** the application has `debug=True` and `root_path="/pfx"`.

#### Scenario: Invalid value
- **WHEN** `API_DEBUG=notabool` is set
- **THEN** constructing the server raises a validation error.
