# TRX to SDK Mapping Reference

Comprehensive mapping from TRX-era patterns to `maltego-transforms` SDK equivalents. Load this during migration planning and implementation.

**Absence from this table is not evidence of absence in the SDK.** Before
declaring any TRX pattern unsupported, a no-op, or without an SDK equivalent,
verify it against the SDK source (`src/maltego/`) or the docs. If a pattern
genuinely has no equivalent, flag it as a manual decision point (planner) or
preserve it as a `TODO` with the evidence you checked (implementer) — never
silently drop it or assume a no-op.

---

## Class to Function Migration

### TRX Pattern (old)

```python
from maltego_trx.transform import DiscoverableTransform
from maltego_trx.entities import Domain, IPv4Address

class DomainToIP(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        domain = request.Value
        for ip in resolve(domain):
            response.addEntity("maltego.IPv4Address", ip)
```

### SDK Equivalent (new)

```python
from typing import Any, Dict
from maltego.server import register_transform
from maltego.model.context import MaltegoContext
from maltego.entities import Domain, IPv4Address

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    domain = input_entity.value
    return [IPv4Address(value=ip) for ip in await resolve_async(domain)]
```

---

## Pattern-by-Pattern Mapping Table

| TRX pattern | SDK equivalent | Notes |
|-------------|--------------|-------|
| `class MyTransform(DiscoverableTransform)` | `@register_transform` async function | Class body → async function body |
| `def create_entities(cls, request, response)` | `async def my_transform(input_entity, context)` | classmethod → async function |
| `request.Value` | `input_entity.value` | Primary entity value |
| `request.getSourceEntity().getProperty("prop")` | `input_entity.<typed_attr>` | Use typed property attribute |
| `response.addEntity(entity_type_str, value)` | `EntityClass(value=value)` + return list | Return entity objects. Annotate the return with the emitted class(es) — `-> list[EntityClass]`, a union `-> list[A | B]` when `addEntity` produces several types, or `-> MaltegoGraph[Class]`. The return annotation is published as the transform's output type in discovery; a bare `-> list` advertises none |
| `response.addUIMessage("msg")` | `context.log.inform("msg")` | Also `.debug()`, `.partial()`, `.fatal()`; emitted as `result.events[].data.statusMessage`, not `status.uiMessages` |
| `request.getTransformSetting("KEY")` | `settings.get("KEY")` | Via `settings: Dict[str, Any]` parameter |
| `request.getTransformSetting("KEY", "default")` | `settings.get("KEY", "default")` | With default |
| `request.Slider` | `slider: int` (or `limit: int`) function parameter | SDK injects the Maltego slider value; matched by name `slider`/`limit` or by `int` annotation |
| `entity.addProperty(name, display, matching, value)` | `entity.<typed_attr> = value` or `entity.add_property(name, ...)` | Typed or dynamic |
| `entity.setLinkLabel("label")` | `entity.link_label = "label"` on returned entity, or `graph.add_link(..., label="label")` | Set on entity (auto-link) or explicit graph link |
| `entity.setLinkColor(color)` / `entity.setLinkStyle(style)` / `entity.setLinkThickness(thick)` | `entity.link_color = LinkColor.RED` / `entity.link_style = LinkStyle.DOTTED` / `entity.link_thickness = LinkThickness.THICKNESS_2` | Use `LinkColor`, `LinkStyle`, `LinkThickness` enums |
| `entity.reverseLink()` | `entity.reverse_link = True` | Arrow points from result toward input |
| `entity.setBookmark(-1)` | `entity.bookmark = Bookmark.NONE` (or other `Bookmark` enum value) | Use `Bookmark` enum from `maltego.model.entity` |
| `registry.add_transform(TransformSet, Transform)` | Auto-registered via `@register_transform` | No manual registry needed |
| `registry.write_local_mtz()` | Not needed in the SDK | Remove |
| `registry.write_config(...)` | Not needed in the SDK | Remove |
| `entity.addOverlay(prop, position, type)` / `setOverlayRow()` | `entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.NORTH, "prop_name")` | Use `OverlayTypes` and `OverlayPositions` enums |
| `entity.setIconURL(url)` | `entity.icon_url = url` (or `EntityClass(value=..., icon_url=url)`) | Dynamic per-result icon. If the icon is always the same for the entity type, set it on the entity definition via `icon_resource` instead of per result |
| `entity.addCustomLinkProperty(name, display, value)` | `graph.add_link(..., properties={"name": MaltegoLinkProperty(name=..., value=..., display_name=...)})` | Use `MaltegoLinkProperty` for custom link metadata |
| `UIM_PARTIAL` / progress msgs | `context.log.partial("msg")` | Also `.inform()`, `.debug()`, `.fatal()`; emitted as `result.events[].data.statusMessage`, not `status.uiMessages` |
| `response.addException("msg")` | `raise MaltegoException("msg")` | Or `MaltegoWarning`, `MaltegoHTTPServerError`, etc. |
| Custom auth handler classes | `OAuthAuthenticator` + `OAuthMiddleware` | Native OAuth validators |

---

## Entity String to Class Mapping

| TRX entity string | SDK class | Import |
|-------------------|----------|--------|
| `maltego.Domain` | `Domain` | `from maltego.entities import Domain` |
| `maltego.IPv4Address` | `IPv4Address` | `from maltego.entities import IPv4Address` |
| `maltego.EmailAddress` | `EmailAddress` | `from maltego.entities import EmailAddress` |
| `maltego.Person` | `Person` | `from maltego.entities import Person` |
| `maltego.Organization` | `Organization` | `from maltego.entities import Organization` |
| `maltego.URL` | `URL` | `from maltego.entities import URL` |
| `maltego.PhoneNumber` | `PhoneNumber` | `from maltego.entities import PhoneNumber` |
| `maltego.Alias` | `Alias` | `from maltego.entities import Alias` |
| `maltego.Location` | `Location` | `from maltego.entities import Location` |
| `maltego.Hash` | `Hash` | `from maltego.entities import Hash` |
| `maltego.BitcoinAddress` | `BitcoinAddress` | `from maltego.entities import BitcoinAddress` |
| Unknown / custom string | — | Flag as custom entity — design decision needed |

---

## Settings Migration

Settings in the SDK are injected as a `settings: Dict[str, Any]` function parameter — **not** via `context`. The decorator kwarg is `settings=` (not `transform_settings=`).

### TRX: Reading a transform setting

```python
api_key = request.getTransformSetting("API_KEY")
```

### SDK: Reading a transform setting

```python
from typing import Any, Dict
from maltego.server import register_transform, TransformSetting

@register_transform(
    display_name="My Transform",
    settings=[
        TransformSetting(name="API_KEY", display_name="API Key", auth=True, is_global=True),
    ],
)
async def my_transform(input_entity: Domain, settings: Dict[str, Any], context: MaltegoContext) -> list:
    api_key = settings.get("API_KEY", "")
    ...
```

## Transform Function Parameters

The SDK injects transform arguments by inspecting the function signature at
registration time. The complete binding rules — input by position; `settings` /
`slider` / `limit` / `context` matched by name first then annotation; and
single-entity vs `List[...]` vs `MaltegoGraph` input — live in one place:
`maltego-transform-basics` → `references/transform-authoring-patterns.md` §4.
Load that for the full table and examples rather than reproducing them here.

For migration, only two TRX source signals map to function parameters:

- `request.getTransformSetting("KEY")` → declare a `TransformSetting` and read
  it from the `settings: Dict[str, Any]` parameter.
- `request.Slider` → add a `slider: int` (or `limit: int`) parameter; the SDK
  injects the Maltego slider value (matched by name first, then `int`
  annotation).

Do not convert slider input into an ordinary `TransformSetting` unless the
source also defines a separate transform setting for that value.

---

## Response Patterns

### TRX: Adding an entity with properties

```python
entity = response.addEntity("maltego.Domain", "example.com")
entity.addProperty("fqdn", "FQDN", "strict", "example.com")
```

### SDK: Returning an entity with properties

```python
from maltego.entities import Domain

domain = Domain(value="example.com")
domain.fqdn = "example.com"
return [domain]
```

---

## Local Config / MTZ Generation — Remove

TRX projects generate local config files. In the SDK, **remove these calls entirely**:

```python
# TRX — DELETE these
registry.write_local_mtz(working_dir="./", prefix="local.")
registry.write_config(host="localhost", port=8080, path="/run", ssl=False, seed="seed")
```

The SDK server is self-describing via `/api/v3/transforms` and `/api/v3/assets/entities`.

---
