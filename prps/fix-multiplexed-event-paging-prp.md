# PRP: Fix multiplexed event paging

## Problem

A multi-input transform rebuilt its result list by concatenating each input's
current events on every poll. A late event from an earlier input could shift
positions, so clients paging by index could miss or repeat events. Sharing one
`MaltegoContext` also placed logs, prompts, and upstream errors under the wrong
input.

## Change

`MultiplexedTransformResultSet` keeps one append-only event list and advances
each child's cursor by the events actually copied. Paging, event counts, and
composite boundaries use that same list. `MaltegoContext.for_input()` gives
each input its own log, prompt, and upstream errors while sharing the request
and graph.

## Verification

- Positional paging returns each event once, including an event added during
  collection.
- Logs stay with their input, and the V3 snapshot reflects the corrected order.
- Run `poetry run pytest src/tests/unit/test_runner.py -q` and
  `poetry run pytest -q`.
