# Runbook: Add a transform

Task-focused steps for writing a new SDK-native transform. If you are in a generated project with skills installed, load `maltego-transform-build` first.

## 1. Pick entities

- Import from `maltego.entities` (the `maltego-transforms-std-entities` package). Check standard entities before defining a custom one.
- Custom entity? Subclass `MaltegoEntity`, decorate with `@register_entity`, and set property metadata via `MaltegoEntityProperty` / `MEF`.

## 2. Write the function

```python
from maltego.server import register_transform, MaltegoContext
from maltego.entities import Domain, IPv4Address

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    return [IPv4Address("1.1.1.1")]
```

Rules:
- `async def` only (no sync transforms).
- Input type = the parameter annotation. Output type = the return annotation. Both are published to `/api/v3/transforms`; a bare `-> list` advertises no output type and breaks client routing.
- Return a single entity, a `list[...]`, `None`, an `AsyncGenerator[...]` (streaming), or a `MaltegoGraph` (multiple types / with links).

## 3. Optional features

- **Settings:** add a `settings: Dict[str, Any]` parameter and declare `settings=[TransformSetting(...)]` in the decorator. Define each setting name once as a module constant; reference it in the declaration and in `settings.get(NAME, default)`.
- **HTTP calls:** `IntegrationClient`, always `context=context`. It raises on non-2xx/network errors (catch `maltego.model.exception.MaltegoException` and subclasses).
- **Input constraints:** `input_constraint=PropertyValueMatchesRegex(regex=...)` from `maltego.model.input_constraints`.
- **Credentials:** `TransformSetting(auth=True, is_global=True)` — never hardcode.

## 4. Register it

Import the module in `project.py` so the server discovers it (`from transforms.my_module import *`).

## 5. Verify

```bash
python project.py
# in another shell: confirm it shows up with the right input/output types
curl http://127.0.0.1:3000/api/v3/transforms
```

If the transform is missing or has no output type, the input/return annotation is missing or untyped.
