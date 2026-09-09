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
