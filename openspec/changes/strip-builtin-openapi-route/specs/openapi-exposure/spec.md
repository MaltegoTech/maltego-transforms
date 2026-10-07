## Purpose

The transform server publishes its OpenAPI document only through the
authentication-aware route controlled by `swagger_enabled`.

## ADDED Requirements

### Requirement: The built-in FastAPI OpenAPI route is never reachable

The server MUST remove FastAPI's built-in OpenAPI route at the application's
configured `openapi_url`, including a path set through `API_OPENAPI_URL`.
When `swagger_enabled` is `False`, no OpenAPI document route MUST be
reachable. When `swagger_enabled` is `True`, the only OpenAPI document route
MUST be `/openapi.json` with the `optional_auth` dependency.

#### Scenario: Custom API_OPENAPI_URL with swagger disabled
- **WHEN** `API_OPENAPI_URL=/custom-openapi.json` is set and the server is
  set up with `swagger_enabled=False`
- **THEN** `GET /custom-openapi.json` returns 404 and no `/openapi.json`
  route exists.

#### Scenario: Custom API_OPENAPI_URL with swagger enabled
- **WHEN** `API_OPENAPI_URL=/custom-openapi.json` is set and the server is
  set up with `swagger_enabled=True`
- **THEN** `GET /custom-openapi.json` returns 404 and `/openapi.json` is served
  by the route that depends on `optional_auth`.

#### Scenario: Default configuration is unchanged
- **WHEN** `API_OPENAPI_URL` is not set
- **THEN** `/openapi.json` is absent with `swagger_enabled=False` and served by
  the `optional_auth` route with `swagger_enabled=True`.
