# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Security

- FastAPI's built-in OpenAPI route is now removed at whatever path
  `API_OPENAPI_URL` configures. Previously only a route at `/openapi.json`
  was removed, so a custom `API_OPENAPI_URL` served the full OpenAPI document
  without authentication, even with `swagger_enabled=False`. With
  `swagger_enabled=True` the document is served only at the auth-protected
  `/openapi.json`.

### Fixed

- The server now finishes application startup under uvicorn. With
  `fastapi-restful` 0.6.0, the expired-execution cleanup loop ran inside the
  lifespan startup and never returned, so the server never started listening.
  Cleanup now runs as a background task every `scheduled_cleanup_seconds`,
  logs and survives failures, and is cancelled on shutdown before the runner
  shuts down.

### Removed

- The `fastapi-restful` dependency, and with it the transitive `psutil<6`
  dependency. Protocol models now use the SDK's own
  `maltego.protocol.api_model.APIModel`, which generates the same camelCase
  aliases, so wire payloads and the OpenAPI schema are unchanged. The
  `API_DEBUG`, `API_TITLE`, `API_VERSION`, `API_OPENAPI_URL`,
  `API_OPENAPI_PREFIX` and `API_DISABLE_DOCS` environment variables still
  configure the FastAPI application. Projects that import `fastapi_restful`
  themselves must now declare it as their own dependency.

## 1.1.2 - 2026-09-29

### Fixed

- `DATE_TIME` and `DATE` property values sent as Unix epoch timestamps
  (milliseconds such as `"1696175006000"`, or seconds) now parse to UTC
  datetimes instead of failing with `OverflowError` and reaching the transform
  as raw strings. Strings dateutil already parses are unchanged.
- v3 run requests rejected with 400 `Invalid input.` now log the reason at
  WARNING instead of DEBUG, so rejected runs can be diagnosed.
- v3 prompt responses rejected with 400 `Invalid input.` or 404 `Resource not
  found.` now log the reason at WARNING instead of DEBUG.
- `boolean` and `boolean_list` transform settings now parse `"true"`/`"false"`
  (case-insensitive) and `"1"`/`"0"` strings correctly; previously any
  non-empty string, including `"false"` and `"0"`, became `True`. Other strings
  (e.g. `"yes"`) are treated as invalid: `None`, or dropped from a list.
- `datetime` link property values that are naive, non-UTC, or use
  `dateutil.tz.tzutc()` are now normalized to UTC (as entity properties already
  are) instead of failing with an `AssertionError`.
- `IntegrationClient` now maps upstream HTTP 402 (payment required / credits
  exhausted) to `MaltegoHTTPDataProviderUnavailable` instead of an "unexpected
  response", and the 403 message no longer implies an invalid API key.
- Upstream 4xx responses are logged at WARNING instead of ERROR, since
  connectors often treat them as expected outcomes (e.g. 404 = no results);
  5xx, unknown statuses and network errors keep their levels.
- The runner logs transforms raising `MaltegoHTTPClientError` subclasses (e.g.
  `MaltegoHTTPInputEntityMalformed`) at WARNING instead of ERROR; other
  `MaltegoException`s remain ERROR.
- `daterange.fromstring_v3` and `date`/`datetime`/`daterange` transform
  settings now accept epoch-timestamp values, and out-of-range values are
  treated as unparseable instead of raising `OverflowError` (HTTP 500).
- `daterange` no longer raises `TypeError` when one bound is timezone-naive and
  the other aware; bounds are normalized before being compared.
- Empty items in `DATE_TIME`/`DATE`/`DATE_RANGE` list property values are
  dropped instead of producing mixed lists such as `[datetime, '']`.
- Unparseable input property values now log a WARNING with the property name,
  type and exception type instead of an ERROR traceback containing the raw
  value; the raw value is still passed through to the transform.

## 1.1.1 - 2026-09-25

### Fixed

- Multiplexed transform execution now preserves late result events across
  pages and attributes logs, prompts, and upstream errors to the correct input.

## 1.1.0 - 2026-09-25

### Added

- Entity definitions can declare optional `variant_property` and `variant_icon_property` references. Protocol 3.3 discovery returns them as `variantProperty` and `variantIconProperty` when configured; earlier protocol versions omit them.

## 1.0.1 - 2026-08-07

### Fixed
- `IntegrationClient._call_httpx_method` no longer raises a bare, untyped
  `MaltegoException` for unhandled 4xx upstream responses. HTTP 429 (rate
  limit) now maps to `MaltegoHTTPDataProviderUnavailable`; all other
  unhandled non-2xx codes map to `MaltegoHTTPDataProviderInvalidResponse`
  instead of the previous untyped exception, so connectors relying on typed
  exception handling can distinguish and react to these cases correctly.
- Threaded transform runners now await cancellation cleanup before closing
  their event loop, preventing intermittent pending-task warnings during
  shutdown.
- The generated discovery helper validates its host argument as a hostname or
  IP literal before constructing request URLs, rejecting URL authority/path
  injection while preserving local and remote SDK discovery.

## 1.0.0 - 2026-07-07

Initial public release of the `maltego-transforms` Python SDK.
