---
name: "maltego-transform-discover"
description: "Load this skill when discovering what transforms and entities a running SDK server exposes, using direct server endpoints."
compatibility: "Requires Python 3.10+ and a running maltego-transforms SDK server (default http://127.0.0.1:8080); the discovery script and curl examples make live HTTP calls to it."
metadata:
  version: "1.0.0"
---

# Maltego Transform Discover Skill

## Purpose
Discover the transforms and entities exposed by a running `maltego-transforms` SDK server using its built-in discovery endpoints. This is the current, modern discovery path for SDK servers.

## Step-by-Step: Discover a Server

### 1. Confirm the Server Is Running

```bash
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/v3/transforms
# Expect: 200
```

If not running, start it with `python project.py`.

### 2. List All Transforms

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms | python -m json.tool
```

Each transform entry includes:
- `name` — the transform identifier used in `/api/v3/transforms/<id>/run` calls
- `display_name` — human-readable name
- `input` — accepted graph/entity input definition and type IDs
- `description` — optional description
- `transform_settings` — per-transform settings declarations

### 3. List All Entities

```bash
curl -s http://127.0.0.1:8080/api/v3/assets/entities | python -m json.tool
```

Each entity entry includes:
- `id` — entity type identifier (e.g., `maltego.Domain`)
- `display_name` — human-readable name
- `properties` — list of property definitions

### 4. Get Details for a Specific Transform

```bash
curl -s http://127.0.0.1:8080/api/v3/transforms/<transform_id> | python -m json.tool
```

Use this to inspect input constraints, settings, and accepted entity types for a single transform.

### 5. Check Server Configuration

```bash
curl -s http://127.0.0.1:8080/health | python -m json.tool
```

Reports server health and may expose non-sensitive config (e.g., which transforms are loaded).

## Load Reference If Needed

Load `references/direct-server-discovery.md` for:
- Full endpoint reference with example responses.
- How to parse transform and entity lists.
- curl command examples for scripted discovery.
- Notes on legacy pTDS/iTDS formats (for recognizing TRX-era projects only).

Use `scripts/discover_server.py` to programmatically query a running server:

```bash
python scripts/discover_server.py --host 127.0.0.1 --port 8080
python scripts/discover_server.py --transforms-only
python scripts/discover_server.py --entities-only
```

## Routing

- **Testing transforms**: load `maltego-transform-test`.
- **Understanding what a TRX project exposes**: load `maltego-trx-migration-planner`.
- **Writing new transforms**: load `maltego-transform-build`.

## What NOT to Do

- Do NOT use pTDS or iTDS as the primary discovery mechanism for current SDK servers.
- Do NOT require the Maltego Desktop client for discovery.
- Do NOT assume internal infrastructure for server access.
