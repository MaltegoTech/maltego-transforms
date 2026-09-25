## Why

Entity definitions need to identify the properties that describe an entity's
variant and variant-specific icon. Consumers can then use declared metadata
instead of relying on particular property names.

## Scope and non-goals

Add optional `variant_property` and `variant_icon_property` settings to
`MaltegoEntityConfig`, and expose them as `variantProperty` and
`variantIconProperty` in each configured v3 entity definition.

Both settings follow `value_property` semantics: a non-`None` value is coerced
to a string, the SDK does not verify that it names a declared entity property,
and configuration inheritance selects a non-empty child value before the
parent value. Copying a configuration preserves both settings.

This change does not change entity values, property fields, overlays, base
icons, transform execution, or client rendering behavior. It does not add a
capability. The discovery members are introduced in protocol 3.3; older
protocol versions omit them, while clients that receive them may ignore the
unknown optional members.

## Artifacts

- Specs: required because v3 entity discovery gains observable response
  members.
- Design: required because the additive discovery contract and its
  compatibility behavior need a durable decision.

## Compatibility and verification

Both response members are optional. Entity definitions without either setting
continue to omit them, preserving their current discovery shape. Configured
definitions add only the corresponding member in protocol 3.3; consumers that
do not interpret the metadata continue to use the existing entity definition
fields.

Verify configuration coercion, copying, and inheritance in focused unit tests,
and verify exact protocol 3.2 and 3.3 discovery responses for configured and
unconfigured entities in a contract test. Run the affected unit and contract
test files and strict OpenSpec validation.
