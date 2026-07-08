# Testing and Parity Reference

How to test a local `maltego-transforms` current SDK server without external tooling. All checks use direct HTTP calls and Python imports.

---

## TRX Migration Notes

Use the TRX migration implementer skill as the canonical completion-gate
checklist. This reference covers the direct HTTP checks and artifact checks
needed to prove those gates.

Do not rely on CSV/discovery metadata alone when choosing representative runs.
Generated TRX projects may keep the true behavior in wrapper classes or shared
dispatch calls, including wrapper output arguments that do not appear in every
discovery artifact.

---

## Running the Transform Server Locally

### Running the project

```bash
# From the project root; replace run.py with the documented project entrypoint.
python run.py
```

### Expected startup output

```
INFO:     Uvicorn running on http://127.0.0.1:8080
INFO:     Application startup complete.
```

---

## Discovery Endpoint

### GET /api/v3/transforms

Returns all registered transforms.

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms | python -m json.tool
```

**Expected response shape:**

```json
{
  "transforms": [
    {
      "name": "domain_to_ip",
      "display_name": "Domain to IP",
      "input": {"type": "ENTITY", "type_ids": ["maltego.Domain"]},
      "description": "..."
    }
  ],
  "oauth": []
}
```

**Assertions:**
- Status 200.
- `transforms` array is non-empty if transforms are registered.
- Each item in `transforms` has `name`, `display_name`, and `input.type_ids`.

---

### GET /api/v3/assets/entities

Returns all entity types the server knows about.

```bash
curl -s http://127.0.0.1:8080/api/v3/assets/entities | python -m json.tool
```

**Expected response shape:**

```json
[
  {
    "id": "maltego.Domain",
    "display_name": "Domain",
    "properties": [...]
  }
]
```

---

## Sending a Transform Request

### POST /api/v3/transforms/<transform_id>/run

```bash
curl -s -X POST http://127.0.0.1:8080/api/v3/transforms/domain_to_ip/run \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "metadata": {
        "entitiesTypesStat": {"maltego.Domain": 1},
        "entitiesTotalCount": 1,
        "linksTotalCount": 0,
        "rootEntitiesCount": 1
      },
      "graph": {
        "entities": [{
          "id": "0",
          "valueRef": "fqdn",
          "type": "maltego.Domain",
          "properties": [{"name": "fqdn", "type": "STRING", "value": "example.com"}],
          "displayInformation": []
        }],
        "links": []
      }
    },
    "transformSettings": [],
    "limit": 12
  }' | python -m json.tool
```

**Expected response shape:**

```json
{
  "result": {
    "runId": "...",
    "state": "RUNNING"
  },
  "status": {
    "uiMessages": [],
    "code": 200
  }
}
```

**Assertions:**
- Status 201.
- `result.runId` is present (`result.state` carries the run state; `status` is an object, not a string).
- Poll `/api/v3/transforms/<transform_id>/run/<runId>/results` and assert returned events.

---

## Response Schema Assertions

When writing automated assertions:

```python
def assert_transform_response(response):
    assert response.status_code == 201
    data = response.json()
    run_id = data["result"]["runId"]
    assert run_id
    # Result events (entities/links) are not in this response body — retrieve them by polling:
    #   GET /api/v3/transforms/<transform_id>/run/<run_id>/results

def assert_entity_type(entity, expected_type):
    assert entity["type"] == expected_type, f"Expected {expected_type}, got {entity['type']}"


TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}

def poll_transform_run(client, transform_id, run_id, poll_interval=1.0):
    """Poll GET /results until result.state is terminal; return the final response dict.

    Each poll returns HTTP 201 with (camelCase on the wire):
      {"result": {"runId": ..., "state": "COMPLETED"|"FAILED"|"CANCELED"|"RUNNING",
                  "eventCount": <int>,
                  "events": [{"timestamp": ...,
                              "data": {"inputType": "ENTITY"|"LINK"|"STATUS_MESSAGE",
                                       "eventType": "ADD", "entity": {...}}}]},
       "status": {"uiMessages": [], "code": 200}}
    A timed-out run is reported as "FAILED".
    """
    import time
    while True:
        resp = client.get(f"/api/v3/transforms/{transform_id}/run/{run_id}/results")
        assert resp.status_code == 201, resp.text
        data = resp.json()
        if data["result"]["state"] in TERMINAL_STATES:
            return data
        time.sleep(poll_interval)
```

---

## Pytest Fixture Patterns

```python
import pytest
import httpx

BASE_URL = "http://127.0.0.1:8080"

@pytest.fixture(scope="session")
def http_client():
    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        yield client

@pytest.fixture
def run_transform(http_client):
    def _run(transform_id, entity_type, entity_value, settings=None):
        return http_client.post(
            f"/api/v3/transforms/{transform_id}/run",
            json={
                "input": {
                    "metadata": {
                        "entitiesTypesStat": {entity_type: 1},
                        "entitiesTotalCount": 1,
                        "linksTotalCount": 0,
                        "rootEntitiesCount": 1,
                    },
                    "graph": {
                        "entities": [{
                            "id": "0",
                            "valueRef": "value",
                            "type": entity_type,
                            "properties": [{"name": "value", "type": "STRING", "value": entity_value}],
                            "displayInformation": [],
                        }],
                        "links": [],
                    },
                },
                "transformSettings": [
                    {"name": key, "value": value}
                    for key, value in (settings or {}).items()
                ],
                "limit": 12,
            }
        )
    return _run
```

### Example Test

```python
def test_domain_to_ip_returns_ip_entities(http_client, run_transform):
    resp = run_transform("domain_to_ip", "maltego.Domain", "example.com")
    assert resp.status_code == 201
    run_id = resp.json()["result"]["runId"]
    assert run_id

    final = poll_transform_run(http_client, "domain_to_ip", run_id)
    assert final["result"]["state"] == "COMPLETED"
    entities = [e for e in final["result"]["events"] if e["data"]["inputType"] == "ENTITY"]
    assert entities and entities[0]["data"]["entity"]["type"] == "maltego.IPv4Address"
```

---

## Syntax and Import Checks

Before running the server:

```bash
# Compile-check all transforms
python -m py_compile src/transforms/my_transform.py

# Import check
python -c "import src.transforms.my_transform; print('Import OK')"

# Full project import check (project.py only starts the server under __main__)
python -c "import project; print('App OK')"
```

---

## Edge Cases to Test

| Case | Input | Expected |
|------|-------|----------|
| Empty value | `""` | 400 or empty entities array |
| Very long value | 2000-char string | No 500 error |
| Wrong entity type | `maltego.NonExistent` | 422 or structured error |
| Missing required setting | omit setting key | 400 or descriptive error |
| Pagination edge | page beyond last | Empty entities array |

---

## Server Config Check

Verify environment variables/settings are loaded:

```bash
curl -s http://127.0.0.1:8080/health | python -m json.tool
```

If the server supports a `/health` or `/config` endpoint, check that settings are non-null (without exposing secrets in logs).

---

## No External Dependencies Required

All tests above:
- Run against `localhost` only.
- Use public test values (`example.com`, `8.8.8.8`, etc.).
- Do not require the Maltego Desktop client, pTDS, iTDS, or external registries.
- Do not require internal credentials or secrets in test fixtures.
