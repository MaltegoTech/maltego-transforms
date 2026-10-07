## 1. Establish evidence

- [x] 1.1 Confirm every `fastapi_restful` usage in `src/`, tests, templates, skills, docs, and requirements files, and read the installed 0.6.0 source of `api_model`, `camelcase`, `api_settings`, and `tasks`.
- [x] 1.2 Capture `/openapi.json` (`swagger_enabled=True`), v3 discovery responses, a v3 transform run, protocol model schemas, and `FastAPI` attributes under `API_*` variables from `origin/main`.
- [x] 1.3 Add a unit test pinning `APIModel` alias generation for protocol field names with digits, existing capitals, and plain snake_case, plus input by field name.
- [x] 1.4 Add a lifespan regression test that enters `server.app.router.lifespan_context(server.app)` under `asyncio.wait_for(..., 10)` with `scheduled_cleanup_seconds=1` and asserts cleanup ran.

## 2. Implement

- [x] 2.1 Add `src/maltego/protocol/api_model.py` and switch every v3 protocol module to it.
- [x] 2.2 Add `src/maltego/server/fastapi_settings.py` and construct `FastAPI` from it in `MaltegoTransformServer.__init__`.
- [x] 2.3 Replace `repeat_every` in the lifespan with a cancellable `asyncio` cleanup task and `try/finally` shutdown.
- [x] 2.4 Remove `fastapi-restful` from `pyproject.toml`, run `poetry lock`, and confirm the lock diff removes only `fastapi-restful` and `psutil`.

## 3. Verify and complete

- [x] 3.1 Run the focused tests, then `poetry run pytest -q` with snapshots unchanged.
- [x] 3.2 Confirm `grep -rn fastapi_restful src/` is empty, and compare the captured responses after the change with the `origin/main` capture.
- [x] 3.3 Start a server with uvicorn, confirm `GET /health` returns 200, and stop it cleanly.
- [x] 3.4 Update `CHANGELOG.md` (Unreleased) and run `openspec validate --all --strict`.
