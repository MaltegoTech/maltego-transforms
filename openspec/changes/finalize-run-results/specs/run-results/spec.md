## ADDED Requirements

### Requirement: Terminal results are final

GET results SHALL report a terminal state only after the transform and eligible after-hooks finish. Final messages and graph events SHALL remain available through pagination until the run is deleted or expires.

#### Scenario: Failure with cleanup output

- **WHEN** a transform fails and an after-hook emits a message
- **THEN** the message is available before GET reports FAILED

#### Scenario: Inactivity timeout

- **WHEN** an active run expires
- **THEN** its execution is stopped and cleanup finishes before timeout is published, and the run cannot later become successful

### Requirement: Cancellation is acknowledged separately from finality

POST cancel SHALL keep its immediate 200/CANCELED acknowledgement. Cancellation SHALL reach the owning execution loop, including requests made before a phase starts. GET SHALL remain nonterminal until cleanup finishes. Repeated cancellation SHALL NOT restart or repeatedly interrupt cleanup.

#### Scenario: Cancellation while cleanup is pending

- **WHEN** POST cancel succeeds while a hook is still finishing
- **THEN** clients can keep polling and receive its final output before GET becomes terminal

### Requirement: Eligible cleanup continues after ordinary hook failures

After-hooks SHALL retain their order and individual timeout limits. A hook failure SHALL be recorded without preventing later eligible hooks from running. Success-only hooks SHALL be skipped once the run has failed. Timeout SHALL take precedence over failure, failure over cancellation, and cancellation over success.

#### Scenario: A hook fails before another cleanup hook

- **WHEN** an after-hook raises and a later failure-enabled hook logs a message
- **THEN** both the error and message are retained before the final failure state

### Requirement: Multi-input finality includes every input

A multi-input run SHALL remain nonterminal while any input can still produce output. Once all inputs finish, its outcome SHALL use the same timeout/failure/cancellation precedence. Cancelling the run SHALL also stop inputs that have not started.

#### Scenario: One input fails while another is still running

- **WHEN** a multi-input run has both an ended and an active input
- **THEN** it remains nonterminal and eventually retains both inputs' output without masking the failed input

### Requirement: Clients drain final pages before teardown

A terminal response SHALL describe final production, not imply that one page contains all events. Clients SHALL advance by the actual page length and drain through the final eventCount before DELETE. INITIALIZED, RUNNING and FINISHED remain nonterminal; internal TIMED_OUT remains FAILED in the results body.

#### Scenario: A failed run spans several pages

- **WHEN** a terminal response has more events than fit in its page
- **THEN** the remaining pages are readable before the client deletes the run
