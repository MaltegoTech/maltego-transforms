## Why

`MaltegoTransformServer` builds its `FastAPI` application with an
`openapi_url` read from the `API_OPENAPI_URL` environment variable (default
`/openapi.json`). FastAPI registers its built-in, unauthenticated OpenAPI
route at that path. `_configure_openapi()` strips only a route at the
hard-coded path `/openapi.json`, so when `API_OPENAPI_URL` names any other
path, the built-in route survives and serves the full OpenAPI document
without authentication, even with `swagger_enabled=False`.

## Scope and non-goals

In scope:

- `_configure_openapi()` removes FastAPI's built-in OpenAPI route at the
  application's configured `openapi_url`, whatever the path, in addition to
  `/openapi.json`.
- With `swagger_enabled=True`, the auth-protected `/openapi.json` route stays
  the only OpenAPI endpoint; with `swagger_enabled=False`, no OpenAPI endpoint
  is reachable.

Non-goals:

- No change to the OpenAPI document, the `/swagger` UI, or the
  `optional_auth` dependency.
- No new setting to serve the auth-protected document at a custom path.
- No change to other `API_*` variables.

## Artifacts

- Specs: required because the set of reachable HTTP endpoints changes when
  `API_OPENAPI_URL` is set.
- Design: required because this is a security contract change; it records
  why the custom path is not re-published behind authentication.

## Compatibility and verification

- Default configuration (`API_OPENAPI_URL` unset): no behavior change.
- `API_OPENAPI_URL=<other path>`: the unauthenticated document at that path
  now returns 404; with `swagger_enabled=True` the document is at the
  auth-protected `/openapi.json`, which the Swagger UI already uses.
- A security test sets `API_OPENAPI_URL=/custom-openapi.json` and asserts the
  route is absent and returns 404 for both `swagger_enabled` values; it fails
  before the fix. Full `poetry run pytest -q` and
  `openspec validate --all --strict` must pass. `CHANGELOG.md` records the fix
  under Security.
