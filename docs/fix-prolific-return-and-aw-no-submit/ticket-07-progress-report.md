# Ticket 07 implementation report

Implemented a read-only HTTP/webhook and scheduled trigger boundary around the merged reconciliation module.

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
triggers. The JSON ledger uses an advisory lock plus atomic replacement for concurrent
receiver/scheduler processes on the same filesystem; deployment still requires a
shared durable filesystem and an HTTPS reverse proxy/TLS endpoint.

Validation: `python -m unittest tests.test_ticket_07_triggers
tests.test_read_only_reconciliation` and the full unittest suite are run in the
implementation session. No production API, credentials, subscription, or
runtime data was used.


Follow-up hardening: events now use durable `processing`, `pending`, `completed`,
and terminal `ignored_wrong_study` stages. A failed API read returns the event to
pending; a processing lease enables restart recovery after a crash. The receiver
is a real `ThreadingHTTPServer` factory with a tested POST contract, and
`run_periodic` is a configurable scheduler loop with a stop event. File locking
protects concurrent receiver/scheduler updates. Current submission detail is
queried before processing and must match the configured study.

Official contract evidence: Prolific documents `X-Prolific-Request-Signature` and
`X-Prolific-Request-Timestamp`, with base64 HMAC-SHA256 over timestamp plus body,
and documents `X-Event-ID` idempotency and unordered `X-Timestamp` delivery:
https://docs.prolific.com/api-reference/webhooks/verifying
https://docs.prolific.com/api-reference/webhooks/idempotency-and-the-x-event-id-header
https://docs.prolific.com/api-reference/webhooks/handling-event-order-with-x-timestamp


Spec-blocker fixes completed: reconciliation reports with `platform_query_failed`
or `local_storage_failed` remain pending, retain report/error evidence, and are
not marked complete. `periodic()` drains pending events and expired processing
leases independently of webhook replay. HTTP responses include the reviewable
report, and the ledger stores it atomically with the event. Header matching is
case-insensitive. Wrong-study events are terminally deduplicated. Processing
ownership tokens prevent an expired worker from completing or failing a newer
lease owner.

Offline wiring prerequisites: expose `make_webhook_server` through a publicly
reachable HTTPS reverse proxy and run `run_periodic` from an external scheduler
process with a configured interval. No subscription, secret, deployment, or live
API setup was performed.
