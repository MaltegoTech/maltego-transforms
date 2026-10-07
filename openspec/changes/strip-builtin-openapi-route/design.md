## Decision

In `MaltegoTransformServer._configure_openapi()` (`src/maltego/server/__init__.py`),
strip routes whose path is `/openapi.json` or the application's
`openapi_url` before the existing swagger branch. `self.app.openapi_url` is
the exact path FastAPI used in `FastAPI.setup()` for its built-in route, so
matching on it removes that route and nothing else. When `openapi_url` is
`None` (`API_DISABLE_DOCS`), FastAPI registered no route and only
`/openapi.json` is stripped, as before.

Alternatives considered:

- Build `FastAPI(openapi_url=None)` unconditionally. This also prevents the
  route but changes `app.openapi_url`, which `API_OPENAPI_URL` and
  `API_DISABLE_DOCS` users can observe, and it touches the `FastAPI(...)`
  construction that the `fastapi-restful` removal also edits.
- Re-register the auth-protected document at the custom path. Rejected:
  `API_OPENAPI_URL` is undocumented, the Swagger UI is hard-coded to
  `/openapi.json`, and publishing a second spec path widens the surface this
  fix closes.

## Compatibility

| Consumer | Current behavior | Target behavior | Gate or fallback | Verification |
| --- | --- | --- | --- | --- |
| Default deployment (`API_OPENAPI_URL` unset) | `/openapi.json` only via the auth route, when swagger is enabled | unchanged | none | existing F25/F70 tests |
| `API_OPENAPI_URL=/x`, swagger disabled | `/x` serves the full spec without auth | `/x` returns 404 | none; fail-closed | new security test |
| `API_OPENAPI_URL=/x`, swagger enabled | `/x` without auth, `/openapi.json` with auth | only `/openapi.json` with auth | fetch the spec from `/openapi.json` | new security test |

## Risks and focused verification

- A deployment that fetched the spec from a custom `API_OPENAPI_URL` path
  loses that endpoint. This is the intended fail-closed outcome; the
  changelog names the replacement path.
- Verification: the new parametrized test in
  `src/tests/security/test_prp6_failclosed.py` fails on `main` (the built-in
  `Route` named `openapi` is present at the custom path and returns 200) and
  passes after the change; `poetry run pytest -q`; `openspec validate --all
  --strict`.
