# Ticket 8 independent review — initial implementation rejected

Base `377199a`; reviewed head `9cb14d5`. Original independent task `01a0890a-dc99-7113-afe8-d7020a3e0e2c`, workspace `/tmp/prolific-round-d-20260910/ticket-08`.

## Standards

No hard AGENTS violations. Two actionable Fowler heuristics: speculative callback/controller boundary does not compose existing services; claimed atomic/durable journal and disable semantics exceed per-object locks, unsynced marker and post-effect completion records.

## Spec

Seven findings: missing real synchronization composition; actual answered RETURNED/TIMED-OUT action names do not dispatch; stale supplied reports and missing trustworthy provenance; disabling during action A still allows B; no later approved activation path/entrypoint; missing real controlled-HTTP end-to-end crash/late/ordering evidence; browser and read-only acceptance deferred as instructions rather than executable evidence.

Actual reconciliation action names include `review_returned_with_result` and `review_timeout_with_result`; initial controller recognizes `archived_result` instead.

## Disposition

Original task resumed with Implement to complete full integration and evidence, with all Standards/Spec findings queued. Current run `/tmp/prolific-round-d-20260910/ticket-08-integration-fix.*`. Confirm queued messages consumed before accepting output. No merge or production execution.

Missing account access may block live read-only verification, but not agent-executable isolated integration/browser work. Finish concrete deliverables and independent reviews before requesting human verification. Approval of real read-only report, historical list and production activation remain separate gates. No new business-policy decision identified.
