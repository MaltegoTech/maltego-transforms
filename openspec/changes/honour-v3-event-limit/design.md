## Decision

Separate the default page size from its maximum:

- `PAGE_SIZE_DEFAULT = 50` applies when `eventLimit` is absent or nonpositive.
- `PAGE_SIZE_MAX_DEFAULT = 10_000` is the default `v3_page_size_max`.
- `get_event_limit()` caps the requested or default size at that maximum.

The maximum bounds a response, not its target size. Pages reference retained
events; a typical entity-plus-link result adds about 280 bytes per event.

Alternatives considered:

- Raising only the maximum would enlarge pages without `eventLimit` from 50
  to as many as 10,000 events without clients requesting them.
- Removing the existing maximum would remove the operator's response-size limit.
- Relying on deployment configuration would leave each SDK server capped at
  50 until its operator finds and changes the setting.

## Compatibility

| Consumer | Current behavior | Target behavior | Gate or fallback | Verification |
| --- | --- | --- | --- | --- |
| Client sends `eventLimit` <= 50 | up to `eventLimit` events | unchanged | none | existing contract tests |
| Client sends `eventLimit` > 50 | 50 events | up to `eventLimit` events (max 10,000) | `MALTEGO_SERVER_V3_PAGE_SIZE_MAX` | new contract test |
| Client sends no `eventLimit` | 50 events | unchanged | none | new contract test |
| Server sets `v3_page_size_max` = N > 50 | N events without `eventLimit` | 50 events without `eventLimit`; explicit requests up to N | none | new contract test |
| Server sets `v3_page_size_max` = N < 50 | at most N events | unchanged | none | new contract test |

## Risks and focused verification

- Larger requested pages produce larger responses; operators can lower the maximum.
- On main, the contract test reads 50 + 50 of 240 events and returns 100
  without `eventLimit` when the maximum is 100; it passes after the fix.
  Run the full pytest suite and `openspec validate --all --strict`.
