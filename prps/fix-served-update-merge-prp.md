# PRP: Stop merging updates into events a client may already have read

## Problem

`TransformResultSet.__gather` merges an incoming UPDATE into the last event in
`output` when both have the same `(id, "UPDATE")` identity. It does this even
when a results poll already served that event. `eventCount` does not grow, the
client's `eventPointer` is already past the event, and the later change is never
delivered. Desktop, Graph Browser and Machine Operator only ever page forward, so
none of them recovers it.

`_merge_update_event` also combines non-property updates with `dict.update`. A
display field or overlay notification carries one new item under the key
`display_information` or `overlays`, so a second one replaces the first and the
client receives only the last, even within one poll interval.

## Change

- `__gather` records the length of `output` when it starts and merges an UPDATE
  only into an event appended during the same call. An event gathered by an
  earlier call is never changed again. Bursts of updates between two polls still
  coalesce into one event.
- `_merge_update_event` collects `display_information` and `overlays` values into
  a list instead of replacing them. `MaltegoEntity.to_v3_run_entity_update`
  renders every item of such a list.
- The public multiplexed result set needs no change: a child never changes an
  event the parent has already copied.

Unchanged: the v3 protocol and response schema, ADD rendering, property merging
by name, and coalescing of updates drained in one pass.

## Verification

- Unit: an UPDATE gathered after a poll is appended, and the served event keeps
  its original updates; two display fields and two overlays in one pass render
  both; a multiplexed child's later update gets a new parent index.
- Contract: a gated transform polled while `RUNNING` delivers the final value.
- Run `poetry run pytest src/tests/unit/test_runner.py -q` and
  `poetry run pytest -q`.
