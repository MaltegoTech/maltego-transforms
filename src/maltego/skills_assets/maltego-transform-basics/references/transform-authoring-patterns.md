# Transform Authoring Basics

Surface-level reference for writing transforms using the `maltego-transforms` current SDK. This is not a complete SDK reference; use docs or local source/tests for areas not covered here.

---

## 1. Basic Async Transform

```python
from typing import Any, Dict
from maltego.server import register_transform
from maltego.model.context import MaltegoContext
from maltego.entities import Domain, IPv4Address

from maltego.util import IntegrationClient

client = IntegrationClient()

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    results = []
    response = await client.get(f"/resolve?domain={input_entity.value}", context=context)
    data = response.json()
    for ip in data.get("ips", []):
        entity = IPv4Address(value=ip)
        results.append(entity)
    return results
```

### Key Points
- Function must be `async`.
- Decorated with `@register_transform`.
- The **first function parameter's type annotation** determines the accepted entity type — do **not** pass `input_entity=` to the decorator.
- Return a list of entities or a `MaltegoGraph`.

---

## 2. Typed Input Entity

```python
from maltego.entities import Person

@register_transform(display_name="Person Info")
async def person_info(input_entity: Person, context: MaltegoContext) -> list[Person]:
    name = input_entity.value          # the entity's display value
    first = input_entity.first_name    # typed property
    last = input_entity.last_name
    ...
```

- Use typed properties directly from the entity object (not string lookups).
- `input_entity.value` is always the primary entity value.

---

## 3. Returning a Graph (Multiple Entity Types)

```python
from maltego.model.graph import MaltegoGraph
from maltego.entities import Domain, EmailAddress, Person

@register_transform(display_name="Domain Profile")
async def domain_profile(input_entity: Domain, context: MaltegoContext) -> MaltegoGraph:
    graph = MaltegoGraph()
    graph.add_entity(EmailAddress(value="admin@" + input_entity.value))
    graph.add_entity(Person(value="Domain Admin"))
    return graph
```

### Type annotations propagate to discovery — type the return too

Both the **input parameter annotation** and the **return annotation** are read at
registration and published to `GET /api/v3/transforms`. The return type becomes the
transform's declared **output** entity type(s), which the Maltego client uses to decide
which transforms to offer on a given result entity. Annotate the return with the actual
entity class(es) you emit — not a bare `list`:

- `-> list[IPv4Address]` → declares `maltego.IPv4Address` as the output type.
- `-> IPv4Address | Domain` or `-> list[IPv4Address | Domain]` → **multiple output types are
  supported** and all are declared in discovery.
- `-> MaltegoGraph[Person]` → typed graph output. Bare `-> MaltegoGraph` declares `maltego.Unknown`.
- Bare `-> list` or an unannotated return → **no output types are advertised** (empty list),
  so the client cannot route the transform onto its result entities.

The first-parameter (input) annotation is read the same way; a missing or untyped input
annotation breaks discovery for that transform.

---

## 4. Transform Function Parameters

The SDK inspects the function signature at registration time and injects arguments automatically per these rules:

1. **Input** — always the **first positional parameter** (any name). Its **type annotation** drives what is injected:
   - `EntityClass` → single entity instance
   - `List[EntityClass]` → list of entity instances
   - `MaltegoGraph` / `MaltegoGraph[EntityClass]` → full input graph
2. **Remaining parameters** are resolved in two passes: name-based first, then annotation-based for unclaimed params.

| Parameter | Name recognized | Annotation recognized | Injected value |
|-----------|----------------|----------------------|----------------|
| Input (first param) | Any name — position only | Entity class, `List[...]`, or `MaltegoGraph` | Entity/list/graph per annotation |
| Settings | `settings` | `Dict[str, ...]` or `dict[str, ...]` | `Dict[str, Any]` of transform settings |
| Slider/limit | `slider` or `limit` | `int` | Maltego slider value (`int`) |
| Context | `context` | `MaltegoContext` | `MaltegoContext` instance |

A bare `dict` annotation is not enough for annotation-based matching unless the parameter is named `settings`; use `settings` or a typed mapping such as `Dict[str, Any]`.

Parameters with default values and `**kwargs` are silently accepted. Any other unresolvable parameter raises `ValueError` at registration.

```python
# All four parameter types together
@register_transform(display_name="Full Example")
async def full_example(
    input_entity: Domain,       # position → single entity
    settings: Dict[str, Any],   # name "settings" → settings dict
    slider: int,                # name "slider" → Maltego slider value
    context: MaltegoContext,    # name "context" → context object
) -> list[IPv4Address]:         # return annotation → declared output type in discovery
    limit = slider
    api_key = settings.get("API_KEY", "")
    context.log.inform(f"Processing {input_entity.value}, limit={limit}")
    ...
```

You may also receive multiple entities or a whole graph as input:

```python
# List input
async def sum_numbers(entities: List[Number], context: MaltegoContext) -> Number: ...

# Graph input
async def analyze_graph(graph: MaltegoGraph, context: MaltegoContext) -> Phrase: ...
```

---

## 5. MaltegoContext

`MaltegoContext` is injected when your transform accepts a `context` parameter or annotates a parameter as `MaltegoContext`. Key attributes:

| Attribute / Method | Description |
|---|---|
| `context.log` | User-visible transform messages via `.inform()`, `.debug()`, `.partial()`, and `.fatal()`. These are emitted as `result.events[].data.statusMessage`, not `status.uiMessages`. |
| `context.request` | FastAPI `Request` object — advanced use only (e.g. reading the raw request body in middleware); not needed in typical transforms |
| `context.response_headers` | Headers merged into the HTTP response — advanced use only (custom middleware headers); not needed in typical transforms |
| `context.upstream_exceptions` | Exceptions recorded by `IntegrationClient` calls |

Settings are passed as a separate `settings: Dict[str, Any]` function parameter — **not** via `context`. See section 7.

---

## 6. IntegrationClient (HTTP Calls)

The SDK provides an `IntegrationClient` for HTTP calls. It is typically instantiated once globally (e.g. in your module or project initialization) and reused across transforms. It is **not** accessed via `context`.

```python
from maltego.util import IntegrationClient

client = IntegrationClient()

@register_transform(...)
async def my_transform(input_entity: Domain, context: MaltegoContext) -> list:
    # You MUST pass the context to the client methods
    response = await client.get("/endpoint", params={"q": input_entity.value}, context=context)
    data = response.json()
```

- Always pass `context=context` to client calls (`get`, `post`, etc.).
- Raises on non-2xx by default; handle exceptions explicitly if needed.

---

## 7. Settings

Settings are injected as a `settings: Dict[str, Any]` function parameter — detected by parameter name `settings` or `Dict[str, ...]` annotation.

### Declaring Settings in `@register_transform`

```python
from typing import Any, Dict
from maltego.server import register_transform, TransformSetting
from maltego.model.context import MaltegoContext
from maltego.entities import Domain

@register_transform(
    display_name="Search",
    settings=[
        TransformSetting(name="API_KEY", display_name="API Key", auth=True, is_global=True),
        TransformSetting(name="MAX_RESULTS", display_name="Max Results", type="int", default_value=10),
    ],
)
async def search(input_entity: Domain, settings: Dict[str, Any], context: MaltegoContext) -> list:
    api_key = settings.get("API_KEY", "")
    max_results = int(settings.get("MAX_RESULTS", 10))
    ...
```

- The decorator kwarg is `settings=` (not `transform_settings=`).
- Access values via `settings.get("KEY", default)` — same dict for both auth/global and per-transform settings.
- `is_global=True` is the current SDK flag for sharing one stored value across transforms in the same namespace.
- `is_global_setting=True` is a compatibility flag for integrations that already rely on the older global-setting naming shape.
- **For new transforms, use `is_global=True`.** Reserve `is_global_setting=True` only for backward compatibility with integrations built against the older global-setting naming.
- Runtime access remains `settings.get("<name>")` for both flags because the SDK deserializes settings back to the original `name`.

---

## 8. Input Constraints

```python
from maltego.model.input_constraints import PropertyValueMatchesRegex

@register_transform(
    display_name="Domain Lookup",
    input_constraint=PropertyValueMatchesRegex(
        regex=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    ),
)
async def domain_lookup(input_entity: Domain, context: MaltegoContext) -> list:
    ...
```

---

## 9. Pagination

```python
from typing import Any, Dict

@register_transform(
    display_name="Large Search",
    settings=[TransformSetting(name="page", display_name="Page", type="int", default_value=1)],
)
async def large_search(input_entity: Domain, settings: Dict[str, Any], context: MaltegoContext) -> list[IPv4Address]:
    page = int(settings.get("page", 1))
    results = await fetch_page(input_entity.value, page)
    return [IPv4Address(value=r["ip"]) for r in results]
```

- Use transform settings to pass page tokens/numbers.
- For offset/page-number APIs, increment the `page` (or `offset`) setting value each run.
- For cursor/token-based APIs, the cursor returned by the API cannot be incremented numerically. Return it as a property on a result entity (so the next run can pass it back in) or store it in a dedicated transform setting — do not fabricate the next cursor.
- Keep each response within practical Maltego graph size limits.

---

## 10. Transform Registration and Server Startup

```bash
# Run the generated project's server entry point (project.py calls run_server()).
python project.py
```

The FastAPI app exposes:
- `GET /api/v3/transforms` — discovery endpoint listing all SDK transforms
- `GET /api/v3/assets/entities` — entity discovery
- `POST /api/v3/transforms/<transform_id>/run` — execute a transform and receive a run ID
