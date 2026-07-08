---
name: "maltego-transform-build"
description: "Load this skill when implementing SDK transforms: writing async @register_transform functions, typed entities, HTTP calls, settings, and input constraints."
metadata:
  version: "1.0.0"
---

# Maltego Transform Build Skill

## Purpose
Guide agents through implementing SDK-native transforms. Focus on async `@register_transform` patterns, typed entities, and clean SDK idioms.

## Step-by-Step: Build a Transform

### 1. Load Basics If Needed
Load `maltego-transform-basics` for surface-level mechanics such as function signatures, settings injection, `context.log`, entity returns, graph returns, and `IntegrationClient` calls. Skip it if you already have the pattern.

### 2. Set Up the Transform Function

```python
from maltego.server import register_transform
from maltego.model.context import MaltegoContext
from maltego.entities import Domain, IPv4Address  # always use standard entities first

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    ...
```

Rules:
- **Always `async`** — sync functions are not supported in the SDK.
- **Type-annotate** the first parameter with the correct entity class — do **not** pass `input_entity=` to the decorator.
- **Import entities** from `maltego.entities` — check standard entities first. (`maltego.entities` ships in the `maltego-transforms-std-entities` package; install it alongside the SDK.)

### 3. Access Input Entity Values
- Primary value: `input_entity.value`
- Typed properties: `input_entity.first_name`, `input_entity.domain`, etc.
- Do NOT use string-based property lookups — use typed attributes.

### 4. Make HTTP Calls via IntegrationClient

```python
from maltego.util import IntegrationClient

# Instantiate a shared client for your project
client = IntegrationClient()

@register_transform(...)
async def my_transform(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    # Pass context to every call
    response = await client.get("/api/endpoint", params={"q": input_entity.value}, context=context)
    data = response.json()
```

- Pass `context=context` to all client methods so limits and errors are tracked properly.
- The client **always raises on non-2xx responses and network errors** (there is no suppress flag). Catch the relevant exception from `maltego.model.exception`:

| Condition | Exception raised |
|-----------|------------------|
| 401 Unauthorized | `MaltegoHTTPDataProviderAPIKeyInvalid` |
| 403 Forbidden | `MaltegoHTTPUnauthorized` |
| 404 Not Found | `MaltegoHTTPDataProviderNotFound` |
| 5xx, timeouts, connection errors | `MaltegoHTTPDataProviderUnavailable` |
| Any other non-2xx (e.g. 429 Too Many Requests) | `MaltegoException` (base class) |

```python
from maltego.model.exception import MaltegoException, MaltegoHTTPDataProviderNotFound

@register_transform(...)
async def my_transform(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    try:
        response = await client.get("/api/endpoint", params={"q": input_entity.value}, context=context)
    except MaltegoHTTPDataProviderNotFound:
        context.log.inform("No results for this entity")
        return []                       # 404 → empty result, not a failure
    except MaltegoException as exc:
        # Catch-all for 429, 5xx, auth, and network errors. exc.message holds the upstream detail.
        context.log.fatal(f"API call failed: {exc.message}")
        return []
    return [IPv4Address(value=ip) for ip in response.json()["ips"]]
```

All the classes above subclass `MaltegoException`, so a single `except MaltegoException` is a safe catch-all; add specific handlers before it only when a status needs different handling. Every raised exception is also appended to `context.upstream_exceptions`.

### 5. Return Entities

```python
# Single entity type
return [IPv4Address(value=ip) for ip in data["ips"]]

# Multiple entity types → use MaltegoGraph
from maltego.model.graph import MaltegoGraph
graph = MaltegoGraph()
graph.add_entity(IPv4Address(value="1.2.3.4"))
graph.add_entity(Domain(value="related.example.com"))
return graph
```

**Type the return annotation with the entity class(es) you emit.** Just like the input
parameter, the return annotation is published to `/api/v3/transforms` as the transform's
declared output type(s), and the Maltego client uses it to decide which transforms to offer
on a result entity. Use `-> list[IPv4Address]` for one type, a union (`-> list[IPv4Address | Domain]`
or `-> IPv4Address | Domain`) for several, or `-> MaltegoGraph[Class]` for a typed graph.
A bare `-> list` (or no return annotation) advertises no output type and breaks that routing.

### 6. Use Settings

Settings are injected as a `settings: Dict[str, Any]` parameter — detected automatically by the `settings` name or a typed mapping annotation. A bare non-`settings` parameter annotated as `dict` is not enough.

```python
from typing import Any, Dict
from maltego.server import register_transform, TransformSetting

# Define each setting name once, then reference the constant on both sides.
API_KEY = "API_KEY"
MAX_RESULTS = "MAX_RESULTS"

@register_transform(
    display_name="Search",
    settings=[
        TransformSetting(name=API_KEY, display_name="API Key", auth=True, is_global=True),
        TransformSetting(name=MAX_RESULTS, display_name="Max Results", type="int", default_value=10),
    ],
)
async def search(input_entity: Domain, settings: Dict[str, Any], context: MaltegoContext) -> list[IPv4Address]:
    api_key = settings.get(API_KEY, "")
    max_results = int(settings.get(MAX_RESULTS, 10))
```

Decorator kwarg is `settings=` (not `transform_settings=`). Access values via `settings.get("KEY", default)`.

Define each setting name once as a module-level constant and reference it in both the `TransformSetting(name=...)` declaration and the `settings.get(...)` call. The name is the SDK's two-sided contract between declaration and lookup — a literal typed twice (and mistyped on one side) silently reads back as the default, with no error. Apply the same single-source rule to other reused literals such as the shared `transform_set` value and the API base URL.

### 7. Add Input Constraints (if needed)

```python
from maltego.model.input_constraints import PropertyValueMatchesRegex

@register_transform(
    display_name="Domain Lookup",
    input_constraint=PropertyValueMatchesRegex(regex=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
)
```

Available constraint classes live in `maltego.model.input_constraints` (e.g. `PropertyValueMatchesRegex`, `PropertyDisplayNameMatchesRegex`, `PropertyNameMatchesRegex`, `PropertyEquals`). `InputConstraint` itself is an abstract base — do not instantiate it directly.

### 8. Verify API Behavior
If uncertain about an API endpoint, parameter, or entity schema:
- Route to `maltego-transform-docs` to choose the relevant Freshdesk SDK article.
- Start from the SDK overview at `https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview` and follow the linked Freshdesk article by title. If a direct public link is not known, cite the article title plus local SDK source or tests instead of inventing a URL.

## Security

- **Do not log entity values that may contain PII.** `context.log.inform()` / `.debug()` / `.partial()` / `.fatal()` messages are surfaced to the user in the Maltego client (as `result.events[].data.statusMessage`). Log operation metadata, not raw entity values.
- **Keep API keys in `TransformSetting(auth=True, is_global=True)`, never hardcoded.** `auth=True` marks the setting as a credential in the client UI; read it at runtime via `settings.get(API_KEY, "")`.
- **Validate entity values before forwarding them.** `input_entity.value` and typed properties are user-controlled. Apply allowlist regex or schema validation before interpolating them into URLs, API query parameters, or any subprocess call.

## Troubleshooting

- **Transform registered but missing from `GET /api/v3/transforms`** — the input parameter's type annotation is missing/not an entity class, or the return annotation is bare (`-> list` with no type argument). Both annotations are read at registration and published to discovery; an absent or untyped one drops the transform (or its output type) from the listing.
- **`422 Unprocessable Entity` on `/run`** — the request body is missing the v3 `metadata` wrapper. Confirm the caller sends the full v3 shape (`input.metadata` + `input.graph`).
- **Entity not appearing in Maltego after a successful run** — the return annotation declares a different type than the function actually returns. The client routes and renders using the declared output type from discovery; a mismatch silently discards the entity.
- **`ValueError` at server startup** — a transform parameter cannot be resolved by name or annotation (not the input entity, `settings`, `slider`/`limit`, or `context`). Remove it or give it a default value.

> These skills cover local development. For production hosting, TLS, environment configuration, and reverse-proxy setup, see `https://docs.maltego.com/en/support/solutions/articles/15000062366-https-certificates-and-browser-trust`, `https://docs.maltego.com/en/support/solutions/articles/15000062356-server-configuration`, and `https://docs.maltego.com/en/support/solutions/articles/15000062365-deploying-behind-a-reverse-proxy`, plus your deployment target's own docs.

## What NOT to Do

- Do NOT write sync transform functions.
- Do NOT use TRX-style class bodies (`class MyTransform(DiscoverableTransform)`).
- Do NOT use `request.Value`, `response.addEntity()` — these are TRX idioms.
- Do NOT hardcode credentials or base URLs in transform code.
- Do NOT assume proprietary internal infrastructure.
