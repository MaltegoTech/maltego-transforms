## Approach

`TransformExecutionContext` keeps a pending outcome until output-producing phases finish. Stop requests are latched and dispatched on the owning loop; they cancel the active phase, not the orchestration that must finish cleanup. Inactivity cleanup requests timeout through the same lifecycle instead of overwriting a live result state. Result polling keeps its state-first snapshot.

Remaining eligible after-hooks run after ordinary hook failures, with existing per-hook timeouts. Timeout outranks failure, failure outranks cancellation, and cancellation outranks success. Multi-input results stay active until every child is final, then use that precedence.

## Compatibility

| Surface | Behaviour |
| --- | --- |
| POST cancel | Unchanged immediate 200/CANCELED acknowledgement; not proof of finished cleanup. |
| GET results/status | Same fields and states; terminal publication waits for cleanup. FINISHED was already nonterminal. |
| Timeout | Header/internal TIMED_OUT still maps to body FAILED. |
| Middleware | Existing signature and call_on_failure flag; later eligible hooks now run after an earlier hook fails. |
| Paging | Existing cursors and page limits; final output must still be drained. |

No capability negotiation or new wire state is needed. Consumers must not interpret POST acknowledgement or FINISHED as final output. Browser and other clients must poll/drain every terminal outcome before DELETE; that consumer follow-up is not implemented by this SDK patch.

## Risks and proof

Final status may arrive later, and a later cleanup hook may now execute where an earlier failure previously skipped it. Test phase cancellation, hook failure/timeout precedence, repeated stops, single/multi-input execution and retained paginated output. Exercise actual local HTTP requests as well as the full suite; client deployment compatibility requires its own verification.
