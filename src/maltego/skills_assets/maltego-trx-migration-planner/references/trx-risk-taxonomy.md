# TRX Risk Taxonomy

Classification guide for TRX transform idioms. Use this during migration planning to classify each transform as Simple, Medium, or Complex and flag manual decision points.

---

## Difficulty Levels

### Simple

Migration is a near-mechanical rewrite. Low risk of behavioral differences.

**Criteria — ALL of these must be true:**
- Class body only uses `request.Value` to read the input.
- Results added via `response.addEntity(entity_type, value)` with no or minimal property setting.
- No settings, no OAuth, no custom auth.
- No overlays, link labels, or link styling.
- No generated config or MTZ writing in the transform body.
- No multi-entity input reading (no `request.getSourceEntity().getProperty()` beyond simple cases).

**Example:**

```python
class DomainToIP(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        domain = request.Value
        results = resolve(domain)
        for ip in results:
            response.addEntity("maltego.IPv4Address", ip)
```

**Action:** Straight rewrite. No manual review needed.

---

### Medium

Migration requires care but is well-defined. Some manual verification needed.

**Criteria — any one of these is present:**
- Uses `request.getTransformSetting(name)` for one or more settings.
- Uses OAuth tokens or API keys read from settings (but not custom auth class).
- Returns multiple entity types in the same transform.
- Uses `entity.addProperty()` for a few properties beyond the primary value.
- Uses `request.getSourceEntity().getProperty(name)` for secondary entity properties.
- Uses `request.Slider` for result count control.
- Has pagination logic (next page token in settings or response).
- Chained transform output feeds into another transform (test sequencing required).
- Uses overlays (`setOverlayRow()`, `addOverlay()`) — rewrite with `entity.add_overlay(OverlayTypes.*, OverlayPositions.*, ...)`.
- Uses link labels, link styling, or link color — rewrite with `entity.link_label = ...` and the `LinkColor` / `LinkStyle` / `LinkThickness` enums.
- Uses `setBookmark()` — rewrite with `entity.bookmark = Bookmark.*`.

**Example:**

```python
class PersonToEmail(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        name = request.Value
        api_key = request.getTransformSetting("API_KEY")
        results = lookup(name, api_key)
        for r in results:
            e = response.addEntity("maltego.EmailAddress", r["email"])
            e.addProperty("source", "Source", "loose", r["source"])
```

**Action:** Rewrite with settings mapping. Verify property migration. Test against live API.

---

### Complex

Migration requires significant manual analysis. High risk of behavioral differences or missing SDK equivalents.

**Criteria — any one of these is present:**
- Uses a custom authentication handler class (not just reading an API key from settings).
- Constructs raw XML in the transform body.
- Contains complex error handling with `UIM_FATAL` or structured error responses.
- Uses `getSourceEntity().getLinkedEntities()` or graph traversal (no SDK equivalent — flag for redesign).
- Uses entity flags with no direct SDK equivalent (verify against the SDK source before assuming).

> Overlays, link labels, link styling/color, and `setBookmark()` are **not** Complex —
> they all have direct SDK equivalents and are Medium. See the Medium criteria above and
> `references/trx-to-sdk-mapping.md`.

**Example:**

```python
class OAuthDomainTransform(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        token = OAuth2Handler.get_token(request.getTransformSetting("CLIENT_ID"))
        entity = response.addEntity("maltego.Domain", "result.com")
        entity.setOverlayRow(1, "Risk: HIGH", "red")
        entity.setLinkLabel("via OAuth")
```

What makes this Complex is the **custom `OAuth2Handler` auth class**, not the overlay or
link label — those are Medium idioms with direct SDK equivalents (`entity.add_overlay(...)`,
`entity.link_label`).

**Action:** Flag for manual review. Break into subtasks. Implement incrementally.

---

## Idiom Reference Table

| Idiom | Risk Level | Note |
|-------|-----------|------|
| `request.Value` | Simple | Direct mapping to `input_entity.value` |
| `response.addEntity(type, value)` | Simple | Return `EntityClass(value=value)` |
| `request.getTransformSetting(name)` | Medium | Map to `settings.get(name)` (via `settings: Dict[str, Any]` param) |
| `entity.addProperty(name, ...)` | Medium | Map to typed attribute or `entity.add_property(...)` |
| `request.getSourceEntity().getProperty(name)` | Medium | Map to `input_entity.<typed_attr>` |
| Multiple entity types in one transform | Medium | Return `MaltegoGraph` with multiple `add_entity()` calls |
| OAuth / token-based auth class | Medium | Use `OAuthAuthenticator` and `OAuthMiddleware` natively supported by SDK |
| `request.Slider` | Medium | Map to a `slider: int` or `limit: int` transform parameter |
| `entity.setOverlayRow(...)` / `addOverlay(...)` | Medium | `entity.add_overlay(OverlayTypes.*, OverlayPositions.*, ...)` |
| `entity.setLinkLabel(...)` | Medium | `entity.link_label = "..."` (or `graph.add_link(..., label=...)`) |
| `entity.setLinkColor/Style/Thickness(...)` | Medium | `LinkColor` / `LinkStyle` / `LinkThickness` enums on the entity |
| `entity.setBookmark(...)` | Medium | `entity.bookmark = Bookmark.*` |
| `UIM_PARTIAL` progress | Medium | Rewrite using `context.log.partial()` |
| `registry.write_config(...)` | Simple to remove | Not needed in the SDK |
| `registry.write_local_mtz(...)` | Simple to remove | Not needed in the SDK |
| Raw XML construction | Complex | Rewrite using SDK entity API |
| `getLinkedEntities()` | Complex | No graph traversal in the SDK; flag for redesign |

---

## How to Use This Taxonomy

1. For each transform class, scan the `create_entities` body.
2. Match idioms against the table above.
3. Assign the highest matching difficulty level.
4. Document the specific idioms found for the implementer.
5. Group transforms by difficulty in the migration plan.

Recommended migration order:
1. **Simple** transforms first — build confidence and test pipeline.
2. **Medium** transforms next — resolve settings and property mappings.
3. **Complex** transforms last — schedule manual review before implementation.
