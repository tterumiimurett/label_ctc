# Round 2 review status

Base: `37e6db5`. No ticket in this round is approved for merge yet.

## Ticket 03

Reviewed `cb945ed`; implementer subsequently completed `5ca77f5`. Standards: zero hard violations. Spec: blocked by conflicting archive loss of original answers, missing durable recovery, archive byte/hash and allocation audit preservation, full session identity checking and explicit consent withdrawal handling. Root resumed the original session with these findings; pending fixes and independent re-review.

## Ticket 05

Implementation `5717b30`. Standards: zero hard violations. Independent Spec review failed: draft/archive evidence, return-request timestamps and real history adapter, fresh ten-minute recheck, persisted identity, concurrency-safe candidate creation, and durable reviewable candidate output. All six findings sent to the same interactive session for fixes; no merge approval.

## Ticket 07

Implementation `a625399`. Root review identified incomplete durable retries/restart recovery, HTTP receiver and configurable periodic scheduling. Original session resumed for fixes; independent dual-axis review required after completion.

All reproduction uses synthetic isolated data. No production archival, message, subscription or activation action is authorized by these reviews.


## Subsequent re-review checkpoints

- Ticket 03 `e4484a0`: Standards passed; Spec blocked because unvalidated PENDING recovery could release mismatched assignments. `3d6dca9`: Standards passed; Spec reproduced late submission after pending intent breaking recovery. `1e687eb`: entry gating and atomic byte writing added, but implementer explicitly omitted required fault/multiprocess tests; original task resumed to add them. No merge approval.
- Ticket 05 `9effc5d`: Standards passed; Spec still blocked by storage/identity anomalies silently resolved, incomplete personal 30-day history treated clear, inbound session mentions misclassified as prior return requests, configurable one-minute wait, and missing supported durable review queue. Findings sent to original interactive session.
- Ticket 07 `52c1326`: Standards passed; Spec blocked failed reports marked complete, absent autonomous pending drain, discarded reports, HTTP header/order timestamp handling, stale lease ownership and wrong-study terminal handling. Fix `e6da61a` is now in independent dual-axis re-review.

The next round remains blocked on all three tickets passing their own final reviews and merging. These are implementation/review defects, not evidence of newly observed production incidents.


## Approved code merges

Ticket 03 final `473a913`: Standards 0 / Spec 0 remaining blockers. Assignment now uses the same recovery gate as submit and drafts. Independent tests: 12 focused CTC tests; root full suite 44 passed. Merged to main.

Ticket 07 final `687876e`: Standards 0 / Spec 0 code blockers. Detail identity/schema, occurrence timestamp ordering and durable periodic reports verified; 14 trigger tests independently passed. Merged to main with production execution disabled. HTTPS, real workspace/API permissions and subscription inventory remain operational acceptance items for activation.

Combined main after these merges: 58 unittest tests passed. Ticket 05 `6f09b6c` remains Spec-blocked: real history adapter never yields clear, fresh uncertainty wrongly cancelled, history manual reasoning not fully durable. Original interactive session is fixing these. Tickets 04/06 have not started.
