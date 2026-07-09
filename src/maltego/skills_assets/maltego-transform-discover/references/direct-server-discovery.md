# Direct Server Discovery Reference

How to discover transforms and entities from a running `maltego-transforms` SDK server using its built-in endpoints.

---

## Modern SDK Discovery Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v3/transforms` | GET | List all registered SDK transforms |
| `/api/v3/transforms/<id>` | GET | Get details for a single SDK transform |
| `/api/v3/assets/entities` | GET | List all entity types the server knows about |
| `/health` | GET | Server liveness check |

The JSON protocol endpoints return JSON. If `MaltegoServerSettings.api_prefix` is configured, prepend that prefix before `/api/v3/...`, for example `/custom/api/v3/transforms`. Authentication requirements depend on server configuration.

---

## GET /api/v3/transforms — Full Transform List

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms | python -m json.tool
```

### Example Response

```json
{
  "transforms": [
    {
      "name": "domain_to_ip",
      "display_name": "Domain to IP",
      "input": {
        "type": "ENTITY",
        "type_ids": ["maltego.Domain"]
      },
      "description": "Resolves a domain to its IP addresses.",
      "transform_settings": [
        {
          "name": "MAX_RESULTS",
          "display_name": "Max Results",
          "type": "string",
          "default_value": "10",
          "optional": true
        }
      ]
    }
  ],
  "oauth": []
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `name` | Used in `POST /api/v3/transforms/<id>/run` to execute the transform |
| `display_name` | Human-readable name |
| `input.type_ids` | Maltego entity type strings accepted as input |
| `transform_settings` | Per-transform settings declarations |

---

## GET /api/v3/transforms/<id> — Single Transform Detail

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms/domain_to_ip | python -m json.tool
```

Returns the same shape as a single item from the transforms list. Useful for inspecting a specific transform's settings and constraints.

---

## GET /api/v3/assets/entities — Entity List

```bash
curl -s http://127.0.0.1:8080/api/v3/assets/entities | python -m json.tool
```

### Example Response

```json
[
  {
    "id": "maltego.Domain",
    "display_name": "Domain",
    "properties": [
      {
        "name": "fqdn",
        "display_name": "FQDN",
        "type": "string"
      }
    ]
  },
  {
    "id": "maltego.IPv4Address",
    "display_name": "IP Address",
    "properties": [
      {
        "name": "ip.internal",
        "display_name": "Internal",
        "type": "boolean"
      }
    ]
  }
]
```

---

## GET /health — Server Health

```bash
curl -s http://127.0.0.1:8080/health | python -m json.tool
```

Typical response:

```json
{
  "status": "ok",
  "version": "3.7.0",
  "transforms_loaded": 5,
  "entities_loaded": 12
}
```

---

## Scripted Discovery (Bash)

```bash
#!/bin/bash
BASE_URL="${SERVER_URL:-http://127.0.0.1:8080}"

echo "=== Transform List ==="
curl -s "$BASE_URL/api/v3/transforms" | python -m json.tool

echo ""
echo "=== Entity List ==="
curl -s "$BASE_URL/api/v3/assets/entities" | python -m json.tool

echo ""
echo "=== Health ==="
curl -s "$BASE_URL/health" | python -m json.tool
```

---

## Reading the Transform List — Extracting IDs

```bash
# Extract all transform IDs
curl -s http://127.0.0.1:8080/api/v3/transforms | python -c "
import json, sys
payload = json.load(sys.stdin)
for t in payload['transforms']:
    print(t['name'], '->', t['input']['type_ids'])
"
```

---

## Legacy Format Recognition (pTDS / iTDS)

> **Note**: pTDS and iTDS are legacy discovery mechanisms used by TRX-era projects. They are NOT the recommended path for SDK servers. This section exists only to help recognize legacy projects during migration.

### pTDS (personal Transform Distribution Server)
- XML-based discovery, typically served from a local Maltego plugin or bundled server.
- Exposes transforms via an XML manifest at `/TRX/TRXSettings` or similar.
- Used by classic Python TRX projects.

### iTDS (internet Transform Distribution Server)
- Hosted XML-based discovery for production classic transforms.
- Agents encountering XML transform manifests should treat the project as a TRX migration candidate.

### Recognition Signal

If you see URLs of the form `http://host/TRX/...` or XML responses from a discovery endpoint, the project is using the legacy protocol. Route to `maltego-trx-migration-planner` for migration planning.

---

## No External Dependencies

All discovery above:
- Uses `curl` (or `httpx`/`requests` in Python).
- Works against `localhost` or any reachable host:port.
- Does not require the Maltego Desktop client or any internal registry.
