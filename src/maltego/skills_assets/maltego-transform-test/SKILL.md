---
name: "maltego-transform-test"
description: "Load this skill when testing a local SDK transform server: syntax checks, discovery endpoint validation, and transform request/response assertions."
compatibility: "Requires Python 3.10+ and a running maltego-transforms SDK server (default http://127.0.0.1:8080); the check script makes live HTTP calls and the pytest fixture examples need pytest and httpx."
metadata:
  version: "1.0.0"
---

# Maltego Transform Test Skill

## Purpose
Test a local `maltego-transforms` SDK server without the Maltego Desktop client, pTDS, iTDS, or any internal infrastructure. All testing is done via direct HTTP calls and Python import checks.

## Prerequisites

- The SDK server must be running locally (start it with `python project.py`).
- No external secrets or proprietary services are required for basic testing.

## Step-by-Step: Test a Transform Server

### 1. Syntax and Import Check

Before running the server, verify the project is importable:

```bash
# Compile-check all Python files
python -m py_compile src/transforms/*.py

# Check the project entry point imports without starting the server
# (project.py only calls run_server() under __main__, so importing is safe)
python -c "import project; print('OK')"
```

If these fail, fix the syntax/import errors before proceeding.

### 2. Start the Server (if not already running)

```bash
# project.py calls run_server() under __main__
python project.py
```

Verify it started:

```bash
curl -s http://127.0.0.1:8080/health | python -m json.tool
# or just check for a 200 response
curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/api/v3/transforms
```

### 3. Check the Discovery Endpoint

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms | python -m json.tool
```

Assert:
- Response is a JSON array/object.
- Each registered transform appears by name/ID.
- Each transform has the expected `input.type_ids`.

### 4. Check the Entity Discovery Endpoint

```bash
curl -s http://127.0.0.1:8080/api/v3/assets/entities | python -m json.tool
```

Assert:
- Response lists expected entity types.

### 5. Run a Transform via HTTP

```bash
curl -s -X POST http://127.0.0.1:8080/api/v3/transforms/<transform_id>/run \
  -H "Content-Type: application/json" \
  -d '{"input": {"metadata": {"entitiesTypesStat": {"maltego.Domain": 1}, "entitiesTotalCount": 1, "linksTotalCount": 0, "rootEntitiesCount": 1}, "graph": {"entities": [{"id": "0", "valueRef": "fqdn", "type": "maltego.Domain", "properties": [{"name": "fqdn", "type": "STRING", "value": "example.com"}], "displayInformation": []}], "links": []}}, "transformSettings": [], "limit": 12}' \
  | python -m json.tool
```

Assert:
- HTTP 201 response.
- Response body contains `result.runId` (string) and `result.state` (initially `"RUNNING"`).

The run POST returns immediately — results arrive asynchronously. Poll the results endpoint until `result.state` is terminal: **`COMPLETED`**, **`FAILED`**, or **`CANCELED`**. Any non-terminal startup or progress state means keep polling; a timed-out run is reported as `FAILED`. Both `/results` and `/status` hit the same handler and return HTTP 201 with the same envelope.

```bash
RUN_ID=$(curl -s -X POST http://127.0.0.1:8080/api/v3/transforms/<transform_id>/run \
  -H "Content-Type: application/json" -d '<request body as above>' \
  | python -c "import sys,json; print(json.load(sys.stdin)['result']['runId'])")

while true; do
  RESULT=$(curl -s http://127.0.0.1:8080/api/v3/transforms/<transform_id>/run/$RUN_ID/results)
  STATE=$(echo "$RESULT" | python -c "import sys,json; print(json.load(sys.stdin)['result']['state'])")
  [[ "$STATE" =~ ^(COMPLETED|FAILED|CANCELED)$ ]] && { echo "$RESULT" | python -m json.tool; break; }
  sleep 1
done
```

The results envelope (field names are camelCase on the wire):

```json
{
  "result": {
    "runId": "...", "state": "COMPLETED", "eventCount": 2,
    "events": [
      {"timestamp": "...", "data": {"inputType": "ENTITY", "eventType": "ADD", "entity": {"type": "maltego.IPv4Address"}}},
      {"timestamp": "...", "data": {"inputType": "STATUS_MESSAGE", "eventType": "ADD", "statusMessage": {"type": "INFO", "text": "...", "progress": 1.0}}}
    ]
  },
  "status": {"uiMessages": [], "code": 200}
}
```

`data.inputType` discriminates each event: `ENTITY` and `LINK` events carry the emitted graph objects; `STATUS_MESSAGE` events carry `context.log` output. Large result sets are paginated — pass `?eventPointer=N&eventLimit=M` to page through `events`.

### 6. Negative / Edge Case Testing

```bash
# Empty value (same request schema as the happy path, with an empty value)
curl -s -X POST http://127.0.0.1:8080/api/v3/transforms/<transform_id>/run \
  -H "Content-Type: application/json" \
  -d '{"input": {"metadata": {"entitiesTypesStat": {"maltego.Domain": 1}, "entitiesTotalCount": 1, "linksTotalCount": 0, "rootEntitiesCount": 1}, "graph": {"entities": [{"id": "0", "valueRef": "fqdn", "type": "maltego.Domain", "properties": [{"name": "fqdn", "type": "STRING", "value": ""}], "displayInformation": []}], "links": []}}, "transformSettings": [], "limit": 12}' \
  | python -m json.tool

# Invalid entity type
curl -s -X POST http://127.0.0.1:8080/api/v3/transforms/<transform_id>/run \
  -H "Content-Type: application/json" \
  -d '{"input": {"metadata": {"entitiesTypesStat": {"maltego.NonExistent": 1}, "entitiesTotalCount": 1, "linksTotalCount": 0, "rootEntitiesCount": 1}, "graph": {"entities": [{"id": "0", "valueRef": "value", "type": "maltego.NonExistent", "properties": [{"name": "value", "type": "STRING", "value": "test"}], "displayInformation": []}], "links": []}}, "transformSettings": [], "limit": 12}' \
  | python -m json.tool
```

Assert:
- Returns a structured error, not an unhandled exception.
- HTTP status reflects the error type (400 for bad input, 422 for validation errors).

### 7. Use `sdk_project_check.py` (If Available)

Run the bundled `sdk_project_check.py` for a structured project check:

```bash
python scripts/sdk_project_check.py --server-url http://127.0.0.1:8080
```

See `scripts/README.md` for details.

## TRX Migration Parity Checks

For migrated TRX projects, discovery and smoke tests are not enough. Load
`references/testing-and-parity.md` for direct HTTP discovery, run-and-poll
mechanics, and artifact checks. Use the TRX migration implementer skill as the
canonical completion-gate checklist.

## Provider-Agnostic Fixtures

When writing automated tests (e.g., with `pytest`):

```python
import pytest
import httpx

BASE_URL = "http://127.0.0.1:8080"

@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=10)

def test_transforms_discovery(client):
    resp = client.get("/api/v3/transforms")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))

def test_run_domain_to_ip(client):
    resp = client.post("/api/v3/transforms/domain_to_ip/run", json={
        "input": {
            "metadata": {
                "entitiesTypesStat": {"maltego.Domain": 1},
                "entitiesTotalCount": 1,
                "linksTotalCount": 0,
                "rootEntitiesCount": 1,
            },
            "graph": {
                "entities": [{
                    "id": "0",
                    "valueRef": "fqdn",
                    "type": "maltego.Domain",
                    "properties": [{"name": "fqdn", "type": "STRING", "value": "example.com"}],
                    "displayInformation": [],
                }],
                "links": [],
            },
        },
        "transformSettings": [],
        "limit": 12,
    })
    assert resp.status_code == 201
    result = resp.json()
    assert "runId" in result["result"]
```

- No internal secrets in fixtures.
- Use public test data (e.g., `example.com`, `8.8.8.8`).

## What NOT to Do

- Do NOT require the Maltego Desktop client to run tests.
- Do NOT require pTDS, iTDS, or any external registry.
- Do NOT hardcode internal API keys or secrets in test fixtures.
- Do NOT skip the syntax/import check step.

## Routing

- **Discovery questions**: load `maltego-transform-discover`.
- **Build/implementation questions**: load `maltego-transform-build`.
