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
