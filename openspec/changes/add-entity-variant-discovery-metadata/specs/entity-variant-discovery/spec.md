## Purpose

Entity authors can publish optional metadata that identifies the property used
as an entity variant and the property used for its variant-specific icon.

## ADDED Requirements

### Requirement: Entity configuration accepts variant property references

`MaltegoEntityConfig` MUST accept optional `variant_property` and
`variant_icon_property` values. For each value, the SDK MUST use the same
semantics as `value_property`: preserve `None`; otherwise coerce the value to
a string; and do not reject the value because it does not name a declared
entity property.

Configuration copying MUST preserve both values. When entity configuration is
inherited, each non-empty child value MUST override its corresponding parent
value; an omitted or empty child value MUST inherit the corresponding parent
value. As with `value_property`, an inherited value cannot be cleared with an
empty value.

#### Scenario: A configured entity preserves its metadata references
- **WHEN** an entity configures `variant_property` as `"profile_kind"` and
  `variant_icon_property` as `"network_favicon"`
- **THEN** the effective configuration retains those exact strings.

#### Scenario: A child config inherits an omitted variant reference
- **WHEN** a parent configures `variant_property` and its child does not
  configure that setting
- **THEN** the child's effective configuration uses the parent's value.

#### Scenario: An unchecked reference is accepted
- **WHEN** an entity configures either variant setting with a string that does
  not match a declared entity property
- **THEN** configuration and discovery serialization complete without SDK
  validation of that reference.

### Requirement: V3 discovery exposes configured variant metadata

`V3EntityDefinition` MUST model optional variant metadata. Protocol 3.3 entity
discovery MUST serialize a configured `variant_property` as `variantProperty`
and a configured `variant_icon_property` as `variantIconProperty`, retaining
their effective string values. The two members MUST be independent:
configuring one does not require configuring the other. Protocol 3.1 and 3.2
entity discovery MUST omit both members.

#### Scenario: Discovery returns both configured members
- **WHEN** an entity configures both variant settings
- **THEN** its v3 discovery definition contains `variantProperty` and
  `variantIconProperty` with the configured values.

#### Scenario: Discovery omits absent metadata
- **WHEN** an entity configures neither variant setting
- **THEN** its v3 discovery definition omits both members.

### Requirement: Existing entity discovery remains unchanged by default

For an entity that does not configure variant metadata, the SDK MUST preserve
its existing v3 discovery fields and values, including property definitions,
overlays, base icon, and transform behavior. Configured variant metadata MUST
require protocol 3.3, but MUST NOT require a separate client capability.

#### Scenario: A consumer does not use variant metadata
- **WHEN** a consumer reads a configured entity definition but does not
  interpret `variantProperty` or `variantIconProperty`
- **THEN** the SDK still provides the entity's existing discovery fields for
  the consumer's established behavior.

#### Scenario: Earlier protocol versions omit configured metadata
- **WHEN** an entity configures both variant settings and the client requests
  protocol 3.2
- **THEN** its discovery definition omits `variantProperty` and
  `variantIconProperty`.

## Protocol examples

The following compact payload snippets show the variant members. Unshown
discovery and run-result members retain their existing protocol behavior.

### Configured entity with both values

Discovery declares the property IDs:

```json
{
  "id": "example.Profile",
  "variantProperty": "profile.kind",
  "variantIconProperty": "profile.icon_url"
}
```

A returned entity supplies the current property values:

```json
{
  "type": "example.Profile",
  "properties": [
    {"name": "profile.kind", "value": "user", "type": "STRING"},
    {
      "name": "profile.icon_url",
      "value": "https://example.test/user.png",
      "type": "STRING"
    }
  ]
}
```

### Configured entity with absent values

Discovery remains configured:

```json
{
  "id": "example.Profile",
  "variantProperty": "profile.kind",
  "variantIconProperty": "profile.icon_url"
}
```

When both instance values are absent, neither property appears in the returned
entity's property list:

```json
{
  "type": "example.Profile",
  "properties": [
    {"name": "profile.id", "value": "42", "type": "STRING"}
  ]
}
```

### Entity configured only with a variant property

The two metadata members are independent:

```json
{
  "id": "example.Profile",
  "variantProperty": "profile.kind"
}
```

```json
{
  "type": "example.Profile",
  "properties": [
    {"name": "profile.kind", "value": "community", "type": "STRING"}
  ]
}
```

### Entity without variant metadata

An ordinary entity does not receive either discovery member:

```json
{
  "id": "example.Person"
}
```
