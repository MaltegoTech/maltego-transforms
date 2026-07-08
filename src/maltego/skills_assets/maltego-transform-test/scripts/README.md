# Test Scripts

## `sdk_project_check.py`

Ships with the `maltego-transform-test` skill in this `scripts/` directory.

It performs a structured check of an SDK project:
- Syntax and import validation for all `.py` files (via `py_compile`).
- Detection of stale TRX imports (`maltego_trx`, `maltego.server.v2`, `maltego.server.trx`).
- Detection of custom entity classes that duplicate standard entities.
- Detection of `@register_transform` usage without an import for it.
- Internal-only term scan of `.agents`/`skills`/`.skills` folders.
- Optional discovery-endpoint check against a running server, querying `/api/v3/transforms` and `/api/v3/assets/entities`.

### Usage

```bash
# Static project check
python scripts/sdk_project_check.py <project-path>

# Also check discovery endpoints on a running server
python scripts/sdk_project_check.py <project-path> --server-url http://127.0.0.1:8080
```

Flags:
- `--server-url URL` — optional running server to check discovery endpoints.
- `--terms TERM [TERM ...]` — additional internal-only terms to scan for.

The `maltego-transform-test` skill references this script directly.
