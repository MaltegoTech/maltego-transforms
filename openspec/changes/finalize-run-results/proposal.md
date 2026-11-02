## Why

Clients can miss the last error or cleanup output when a run reports completion too early. Cancellation can also fail to wake a worker, and an inactive run can time out but later report success.

## What changes

Make terminal GET results mean execution and eligible cleanup have finished. Deliver cancellation on the worker loop, finalize inactivity expiry, and wait for all inputs before reporting an aggregate outcome. Keep the existing response format and immediate POST cancellation acknowledgement.

This change needs a small execution spec and compatibility design. Verify it with deterministic lifecycle tests, paginated HTTP requests, and the full suite.

## Scope

SDK execution, polling, retained output and regression tests. Clients must still fetch remaining pages before DELETE; changing client UI or result-limit policy belongs to their implementations.
