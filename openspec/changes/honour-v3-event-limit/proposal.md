## Why

Previously, the default `v3_page_size_max` capped pages at 50 events. A client
that stops at its result limit requests the remainder once using
`eventPointer = read` and `eventLimit = eventCount - read`, then deletes the
run. It therefore keeps only 100 of 2,000 events (1,000 results); other V3
servers return the requested remainder.

## Scope and non-goals

In scope:

- An explicit `eventLimit` is honoured up to `v3_page_size_max`.
- The default `v3_page_size_max` becomes 10,000 (`PAGE_SIZE_MAX_DEFAULT`).
- A request without `eventLimit` (or with `eventLimit <= 0`) keeps a page of
  50 events (`PAGE_SIZE_DEFAULT`), or `v3_page_size_max` when that is lower.
- `MALTEGO_SERVER_V3_PAGE_SIZE_MAX`, the deprecated `V3_PAGE_SIZE_MAX` and
  `--v3-page-size-max` keep setting the maximum.

Non-goals:

- No change to the run, prompt or cancel endpoints, the event order, or
  `incompleteCompositeEntity`.
- No new setting.
- No change to how clients page.

## Artifacts

- The spec records the paging contract; the design explains the default.

## Compatibility and verification

- Requests with `eventLimit <= 50`: unchanged.
- Requests with `eventLimit` above 50: up to `eventLimit` events (at most
  10,000 by default) instead of 50.
- Requests without `eventLimit`: unchanged with the default settings (50).
  A server that set `v3_page_size_max` above 50 now serves 50 to such a
  request instead of its maximum.
- The `v3-page-size` OPTIONS header reports 10,000 by default.
- A contract test reads 240 events as 50 plus the remainder; on main it gets
  50 + 50, and it passes after the fix. Run the full pytest suite and
  `openspec validate --all --strict`; the changelog records the fix.
