# Ticket 8 implementation report

Follow-up implementation replaces the callback-only controller from `9cb14d5`.

- `ActivationController` composes the existing signed `ReconciliationTrigger`, `VerificationStore`, `JsonContactLedger`, and real adapter contracts. It performs a fresh reconciliation immediately before actions.
- RETURNED and TIMED-OUT observations call the real store lifecycle methods; missing-result candidates use the existing candidate builder and outbound ledger/adapter.
- Candidate provenance is derived from durable event/backfill context: event + event ID is `new`, historical backfill is `historical`, and everything else is `unknown`/manual.
- `ActionJournal` uses a shared process file lock, fsync, intent-before-effect, durable outcomes, a synchronized disable marker, and a kill check before each action. Existing store/outbound idempotency handles restart recovery.
- `activation_cli.py` provides an executable journal/disable entrypoint. Production execution requires explicit activation approval and was not run.

Evidence: 50 focused integration/regression tests pass; the full repository suite is pending final run. The real isolated Playwright browser proof passed task/instruction visibility, audio playback (`currentTimeAdvanced: true`), no-task state, network failure, invalid JSON, and null-payload visible errors.

Live prerequisites remain externally missing: authorized credential, trustworthy study/workspace identity, HTTPS receiver/scheduler inventory, and human approval of the concrete action list. No production GET, POST, message, webhook, assignment, deployment, restart, or production-data mutation was performed.
