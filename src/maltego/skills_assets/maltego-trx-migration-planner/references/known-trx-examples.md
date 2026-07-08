# Known TRX Examples And SDK Equivalents

These are familiar public patterns from `MaltegoTech/maltego-trx-examples`, kept
locally so migration work does not depend on network access. Use this guide as a
comparison aid when a source project looks like the public TRX examples, not as
a compatibility target.

## Comparison Table

| Public TRX example | Legacy pattern | SDK-native target |
|---|---|---|
| `GreetPerson` | `DiscoverableTransform.create_entities(...)` plus `response.addEntity(Phrase, ...)` | `@register_transform` async function returning `Phrase(value=...)` |
| `DNSToIP` | `DiscoverableTransform.create_entities(...)`, `request.Value`, `request.Slider`, `response.addEntity(...)`, `response.addUIMessage(...)` | `input_entity.value`, `slider: int`, `context.log.partial(...)`, `IPv4Address(...)` |
| `legacy_transform.py` | `register_transform_function(trx_DNS2IP)` and `MaltegoTransform().returnOutput()` | `@register_transform` async function that returns entities directly |
| `NameFromCSV` | sidecar `phone_to_names.csv` lookup with `open("phone_to_names.csv")` | packaged local data access plus SDK entity return values |

## Class-Based Transforms

The public examples use `DiscoverableTransform` subclasses such as `GreetPerson`
and `DNSToIP`. The migration target is an async SDK transform:

```python
@register_transform(display_name="Greet Person")
async def greet_person(input_entity: Person, context: MaltegoContext) -> list[Phrase]:
    return [Phrase(value=f"Hi {input_entity.value}, nice to meet you!")]
```

Key TRX signals to map:

- `request.Value` becomes `input_entity.value`.
- `response.addEntity(...)` becomes returned SDK entities.
- `response.addUIMessage(...)` becomes `context.log.inform(...)` or
  `context.log.partial(...)` depending on intent.
- `UIM_PARTIAL` and `UIM_TYPES["partial"]` indicate partial progress, not a
  separate authoring model.
- Entity aliases like `maltego_trx.entities.IPAddress` should resolve to the
  SDK entity class, such as `maltego.entities.IPv4Address`.

## Function-Style Legacy Transforms

`legacy_transform.py` shows the older function route:

```python
register_transform_function(trx_DNS2IP)
# ...
return response.returnOutput()
```

For migration, treat that as behavior evidence for a normal SDK transform, not
as a pattern to preserve. Keep the logic, drop the TRX wrapper, and author the
transform as `@register_transform`.

## Project Registration

The public examples register both function and class transforms with
`register_transform_function(...)` and `register_transform_classes(...)`.
Migrated SDK projects should rely on SDK discovery instead:

- author transforms with `@register_transform`
- serve discovery through `/api/v3/transforms`
- do not keep `maltego_trx` imports in the migrated code

## UI Messages And Slider Input

`response.addUIMessage(...)` in the public examples is usually a user-facing
status or partial-progress note. In the SDK, prefer `context.log.*` helpers.
Those helpers emit `result.events[].data.statusMessage`, not `status.uiMessages`.

`request.Slider` is a TRX-era input convention from `DNSToIP`. In the SDK,
model that input as a `slider: int` function parameter when the transform still
needs a count or limit. The SDK maps the Maltego slider input to that argument.
Do not keep the TRX request object or convert the slider into a named
`TransformSetting`.

```python
@register_transform(display_name="DNS to IP")
async def dns_to_ip(
    input_entity: DNSName,
    slider: int,
    context: MaltegoContext,
) -> list[IPv4Address]:
    limit = slider
    ...
```

## Sidecar Data Files

`NameFromCSV` reads `phone_to_names.csv` next to the transform. That is useful
behavior evidence for file-backed lookups, but the SDK migration should package
or load the data explicitly rather than assuming a working-directory lookup.

## Final Rule

These examples are behavior evidence. They help you understand the legacy
transform intent, but they are not a compatibility target and should not pull
`maltego_trx` imports into the SDK rewrite.
