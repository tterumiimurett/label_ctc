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

## Tool failure recovery and initial browser evidence

The first integration revision ended without a patch because default sandbox editing failed (`bwrap` loopback). This is not an external implementation blocker: root resumed the same task using normally approved escalated file editing in the authorized worktree. Current run `ticket-08-integration-fix2.*`.

Root inspected the completed browser command's actual output: exit 0, task/instruction visible, metadata/canplay true, playback advanced, no-task/network/invalid-JSON/null-payload failures visible. Sanitized output saved in `ticket-08-browser-initial.json`. This validates isolated Chromium/synthetic audio at initial9cb14d5; it does not prove complete integration or production audio. Final version must retain browser evidence and supply remaining full-chain proof.

## Re-review at 7a5d2d3 — still incomplete

Original task now added concrete service references and an ActionJournal. Standards reports missing public type annotations required by AGENTS, disable not covering outbound/candidate execution, and outcomes recorded as completed without actual result/reason. Root inspected four new tests: all use mocks, not the required actual-component chain. CLI only shows/disables the journal and explicitly lacks preview/activation execution. Existing browser proof does not close these integration gaps. Independent Spec review is checking actual trigger/report/action/status contracts before the next original-task revision. No human gate requested for incomplete work.

Final Spec at `7a5d2d3` confirmed: answered RETURNED action still skipped; normalized `TIMED OUT` passed to store is rejected; verified events do not initiate actions; arbitrary event dictionaries label whole-report history new; unbound activation boolean and disable bypass; stale lifecycle loop/outcomes/pending intents; non-executable activation CLI; mock-only integrated tests. `periodic()['report']` contract itself is correct. Root full suite 111 passed but misses these defects. Original task resumed in `ticket-08-fullchain-fix.*` for complete real-component/HTTP implementation. No new business decision required.
