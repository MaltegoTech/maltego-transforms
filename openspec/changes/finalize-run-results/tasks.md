## 1. Regression coverage

- [x] 1.1 Add deterministic tests for failure/timeout cleanup, cancellation before/during phases, repeated stops, and mixed multi-input outcomes; observe failures before implementation.
- [x] 1.2 Move the polling tests to integration/server, synchronize race injection, assert expected failure messages and polling deadlines, and cover terminal-page drainage and unchanged cancel acknowledgement.

## 2. Implementation

- [x] 2.1 Defer terminal publication through eligible cleanup and retain all hook errors/messages with explicit outcome precedence.
- [x] 2.2 Dispatch stop requests on their owning loop, finalize active inactivity expiry, and cancel inputs that have not started.
- [x] 2.3 Aggregate only finalized inputs and preserve state-first results polling.

## 3. Delivery

- [x] 3.1 Merge current main, bump the package patch version, and update concise release notes.
- [x] 3.2 Verify local HTTP discovery/execution/cancel/drain, focused tests, the full suite, lint, packaging and OpenSpec validation.
- [x] 3.3 Explain the client follow-up: after cancellation acknowledgement, keep polling through nonterminal states and drain all terminal pages before DELETE.
