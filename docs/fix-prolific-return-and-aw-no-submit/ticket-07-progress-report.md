# Ticket 07 implementation report

Implemented a read-only trigger boundary around the merged reconciliation module.

- `triggers.py` verifies Prolific webhook HMAC signatures, requires the documented
  event type and resource ID, and treats `X-Event-ID` as an idempotency key.
- Events are durably recorded with an atomic JSON replacement; the latest
  `X-Timestamp` is tracked per submission so out-of-order notifications cannot
  make an old event authoritative.
- Webhook and periodic paths both call `reconcile_current_state`; neither path
  performs archive, allocation, return-request, message, subscription, or
  deployment work. Production execution is rejected explicitly.

Assumptions: the merged reader’s `get_submission` call remains the source of
truth for status/study/participant/completion code; webhook bodies are only
triggers. The JSON ledger is intended for one scheduler/receiver process; a
multi-process deployment needs a transactional store owned by a later ticket.

Validation: `python -m unittest tests.test_ticket_07_triggers
tests.test_read_only_reconciliation` and the full unittest suite are run in the
implementation session. No production API, credentials, subscription, or
runtime data was used.
