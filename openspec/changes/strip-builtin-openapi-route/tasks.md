## 1. Establish evidence

- [x] 1.1 Confirm `_configure_openapi()` strips only `/openapi.json` and that `API_OPENAPI_URL` moves FastAPI's built-in route (served with 200 and no auth on `main`).
- [x] 1.2 Add a parametrized security test for `API_OPENAPI_URL=/custom-openapi.json` with both `swagger_enabled` values; confirm it fails before the fix.

## 2. Implement

- [x] 2.1 Strip routes at `/openapi.json` and at `self.app.openapi_url` in `_configure_openapi()`.

## 3. Verify and complete

- [x] 3.1 Run the security test file, then `poetry run pytest -q`.
- [x] 3.2 Update `CHANGELOG.md` (Unreleased, Security) and run `openspec validate --all --strict`.
