## Decision

Add two independent optional `MaltegoEntityConfig` fields:

- `variant_property`, serialized as `variantProperty`
- `variant_icon_property`, serialized as `variantIconProperty`

They are property-name references, not values and not icon resources. Their
constructor coercion, copy behavior, and child-first inheritance mirror
`value_property` in `src/maltego/model/entity/config.py`. In particular, the
SDK does not validate that either reference appears in the entity's declared
fields.

Add corresponding optional fields to
`src/maltego/protocol/v3/discovery/entity.py`, then pass the effective config
values through `MaltegoEntity.to_v3_entity_definition` in
`src/maltego/model/entity/__init__.py`. The v3 routes already exclude optional
members whose value is `None`.

Flat fields make the property-reference meaning explicit and avoid introducing
a new nested schema for two independent optional values. A `variant` object was
not selected because it adds structure without a current additional member.

## Compatibility

| Consumer | Current behavior | Target behavior | Gate or fallback | Verification |
| --- | --- | --- | --- | --- |
| Entity author without variant metadata | No variant members in discovery | Unchanged response shape | Settings are optional; unset fields are omitted | Contract response for an unconfigured entity |
| Entity author with variant metadata | Cannot declare these references | Declares either or both property references | Additive opt-in configuration | Unit and contract responses |
| Consumer that uses the metadata | Relies on its current entity fields | Can read the two additive discovery members in protocol 3.3 | No separate capability; requests protocol 3.3 | Exact member names and values in contract test |
| Consumer that does not use the metadata | Uses existing discovery fields | Continues to receive those fields unchanged | Protocol 3.1/3.2 omit metadata; 3.3 clients may ignore it | Regression assertion for existing fields |

The change does not alter the default discovery payload of existing entity
configurations. It deliberately does not use a client capability: configured
metadata is included only when the negotiated protocol version is 3.3 and is
omitted for earlier versions. A client that understands protocol 3.3 but does
not use variants can ignore the optional members.

## Risks and focused verification

The references may be misspelled or point to no declared property. This is
intentional parity with `value_property`; consumers determine how to handle an
unusable reference. Focused unit tests must cover string coercion, copies, and
child-first inheritance. A v3 contract test must assert camel-case member
names, independent optionality, and omission for an entity with no metadata.
