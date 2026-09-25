## 1. Establish evidence

- [x] 1.1 Add focused `MaltegoEntityConfig` tests for variant-reference
  coercion, copying, child-first inheritance, and absent-property acceptance.
- [x] 1.2 Add a focused v3 discovery contract fixture that configures both
  references, plus an unconfigured control entity.

## 2. Implement

- [x] 2.1 Add `variant_property` and `variant_icon_property` to
  `src/maltego/model/entity/config.py`, mirroring `value_property` in the
  constructor, `copy`, and `merge_with`.
- [x] 2.2 Add optional discovery-model fields in
  `src/maltego/protocol/v3/discovery/entity.py` and serialize them from
  `MaltegoEntity.to_v3_entity_definition`.
- [x] 2.3 Introduce protocol 3.3 and return variant metadata only through
  protocol-3.3 entity discovery; do not introduce a separate capability.

## 3. Verify and complete

- [x] 3.1 Run the affected unit and v3 contract test files with Poetry.
- [x] 3.2 Run `openspec validate add-entity-variant-discovery-metadata --strict`
  and reconcile the proposal, design, and requirements with the final tests.
- [x] 3.3 Verify protocol 3.2 omits configured metadata and protocol 3.3
  includes it.
