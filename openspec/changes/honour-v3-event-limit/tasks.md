## 1. Establish evidence

- [x] 1.1 Confirm `get_event_limit()` caps every results page at `v3_page_size_max` (default 50) and uses it as the page size when `eventLimit` is absent.
- [x] 1.2 Add contract tests for a page of the rest of a 240-event run, a page without `eventLimit`, and a lowered `v3_page_size_max`; confirm they fail before the fix.

## 2. Implement

- [x] 2.1 Add `PAGE_SIZE_MAX_DEFAULT = 10_000` as the default of `v3_page_size_max`.
- [x] 2.2 In `get_event_limit()`, use `PAGE_SIZE_DEFAULT` for an absent `eventLimit`, then cap at `v3_page_size_max`.

## 3. Verify and complete

- [x] 3.1 Run the new contract tests, then `poetry run pytest -q`.
- [x] 3.2 Update `CHANGELOG.md` (Unreleased, Fixed) and run `openspec validate --all --strict`.
