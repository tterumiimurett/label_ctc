# Ticket 5 implementation report

Implemented the read-only missing-result contact-candidate engine.

- Added `prolific/ctc_verification_app/contact_candidates.py`. It consumes the merged reconciliation report, records the first confirmed missing-result observation in a durable atomic JSON ledger, waits ten minutes across restarts, rechecks current rows, checks platform `return_requested`, and delegates session-scoped message-history inspection.
- Produces only `waiting`, `candidate`, `already_contacted`, `manual_review`, or `pending` decisions. It never sends messages or changes platform status. Candidate output includes the exact session ID, evidence, and approved message text.
- Added synthetic tests covering restart persistence, timing, NOCODE with a complete result, uncertain evidence, API failure, existing requests, and platform return-request deduplication.

Validation:

- `python3 -m unittest tests.test_contact_candidates -v` — 6 passed.
- `python3 -m unittest discover -s tests -v` — 43 passed.
- `git diff --check` — passed.

Limitations and human checkpoints:

- The message-history adapter and reconciliation scheduler/API wiring remain external seams; this ticket intentionally does not send or activate production contact.
- A human must review generated candidates and approve any later outbound operation, including historical candidates.
- No production credentials, participant data, API writes, subscriptions, deployments, or runtime mutations were used.


## Spec-blocker follow-up

- Replaced fabricated-report-only due processing with `ProlificFreshReconciliation`, which reruns the real read-only reconciliation and fetches current submission details/messages before candidate generation.
- Reconciliation rows now preserve `return_requested`; the adapter respects the 30-day message query window and treats permission, schema, identity, and ambiguous history failures as non-clear.
- Drafts, archived results, save/read errors, other-session evidence, identity changes, and changed current status are durable manual/cancelled outcomes.
- Added process/thread locking and atomic per-process temporary files for ledger updates.
- Added integrated synthetic API/storage tests covering fresh participant changes and durable manual queues.

Follow-up validation: `python3 -m unittest discover -s tests -v` — 45 passed.


## Final Spec blocker closure

- `local_read_error` and `identity_mismatch` rows are routed to durable manual review before any resolution branch.
- `return_requested` preserves the official nullable timestamp and any truthy timestamp is deduplicated.
- Empty or unscoped 30-day message results are never treated as clear. Automatic prior-contact recognition requires workspace visibility, coverage evidence, researcher sender identity, participant relevance, session ID, and explicit return-request wording; inbound participant help is ambiguous.
- The wait parameter is fixed at exactly ten minutes; shorter values are rejected.
- Pending, manual-review, and candidate records are exposed by `queue_report` and `python3 -m prolific.ctc_verification_app.contact_candidates --ledger ...`, with identity, approved text, reason, and evidence persisted.
- Added official query-combination tests and synthetic integrated reconciliation/message tests.

Final validation: `python3 -m unittest discover -s tests -v` — 49 passed; no outbound or live API operations.


## Final three-blocker correction

- Added `VerifiedMessageScope` as explicit local operator evidence: approved researcher/workspace IDs, coverage start/end, verified workspace visibility, and a required verification note. The adapter uses only documented message `results`; it does not require invented API response metadata.
- The documented `created_after + study_id + workspace_id` query is used. Submission `started_at` must fall within the locally verified coverage window. A genuinely covered empty result is `clear`; absent/invalid setup evidence is unavailable/manual.
- Fresh `local_read_error` and `identity_mismatch` are checked before status cancellation. Every non-clear history outcome goes through durable `_manual` with identity, approved text, reason, and evidence.
- The integrated controlled-API test reaches a candidate through `ProlificFreshReconciliation` with empty official results and local scope evidence; no `FakeFresh` bypass or live messaging is used.

Final validation: `python3 -m unittest discover -s tests -v` — 49 passed.


## Participant-scoped history correction

- Message inspection now uses the documented participant-scoped `user_id + workspace_id + created_after` query and deliberately omits `study_id`, so unassociated participant chats are included.
- It relies only on documented message fields (`sender_id`, `body`, `channel_id`, `data`) and treats inbound participant help or outbound return wording without the exact session ID as ambiguous/manual.
- A covered empty participant history is clear only when local scope evidence is current, unexpired, within the API's 30-day query limit, workspace visibility is verified, and the session `started_at` is covered through the latest read.
- Added tests for participant-scoped query shape, inbound/no-session messages, unassociated chats, old sessions, stale scopes, valid empty history, and the real adapter candidate path.

Final validation after this correction: `python3 -m unittest discover -s tests -v` — 50 passed.


## Read-only production verification follow-up

- A researcher-approved, read-only verification used the configured credential and production data path without recording secrets or participant identifiers in version control. No platform messages, status changes, or production file writes were performed.
- The live submissions response uses `_links.next.href`, and the study response contained repeated submission IDs across pages. Reconciliation now follows that documented response shape, deduplicates by submission/session ID, and fails closed unless the unique count matches `meta.count`.
- Message history now follows every same-origin `_links.next.href` page before deciding that covered participant history is clear.
- The historical missing-result list supplied a real completion-code transition: one currently awaiting-review submission had no matching local result and no platform return-request timestamp, but another session for the same participant had a final result. Ticket 5 correctly routed this case to durable manual review rather than producing an automatic contact candidate.
- Other currently awaiting historical missing-result cases had platform return-request timestamps and were classified as already contacted. The verified live set therefore contained no unambiguous automatic-contact candidate; no positive production send recommendation was manufactured.
- The durable manual queue was read successfully from a separate process with full identity, proposed message, reason, and evidence. The live participant-specific report remains outside the repository.
- Added controlled-HTTP integration tests for real submission reconciliation pagination/deduplication and participant message pagination, including a second-page inbound message that must prevent a clear-history decision.
- Corrected local-evidence manual reasons so the ledger records `uncertain_local_evidence` instead of the generic missing-result classification.

Code-review closure:

- Submission pagination requires a stable `meta.count`; missing or mismatched counts fail closed.
- Message pages require the actual `_links` envelope. A terminal page may contain only `_links.self`, as observed in the read-only API; continuation links must preserve the exact participant/workspace/time query, message resource path, host, and HTTPS scheme.
- Durable manual evidence retains each concrete local error string, and initial/fresh local uncertainty uses one shared decision helper.
- Full validation after review: `python3 -m unittest discover -s tests -v` — 56 passed; syntax and diff checks passed.
