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

## Re-review at a64e1cf — rejected

Standards: public type hints/UTF-8 still incomplete; ApprovalStore's declared lock unused with shared temporary file; disable marker durability and actual manual outcomes missing. Spec: fresh APPROVED can still invoke fabricated RETURNED; answerless RETURNED is routed through TIMED-OUT; candidate/outbound phase removed and message history stubbed unavailable; caller context masquerades as accepted event and gives whole-report origin; whole-report approval digest blocks routine new cases while CLI accepts arbitrary digest; no executable execution/receiver/scheduler or pending-intent recovery; one integration test still calls a method directly and lacks message/crash/ordering/disable proof. Reader.send_message exists and is not a finding.

Original task resumed in `ticket-08-contract-fix.*`, keeping full existing phases while fixing the actual integration boundary. No new human policy decisions; complete agent-executable work before the live/human gates.

## cf268b0 and db553b2 checkpoints

Spec pinned cf268b0 reproduction `/tmp/ticket08-cf268b0-spec-repro.py` confirms disabled journal can still produce one message POST and normalized timeout causes zero timeout lifecycle calls. Public annotations/UTF-8/indentation, approval/routine provenance, audit/recovery and CLI execution remain unaccepted. That repro deliberately loads the old pinned code; final regressions must exercise current code.

Original task added receiver HTTP coverage at `db553b2`, reporting 114 tests, actual signed listener plus real API adapter/store for RETURNED final and answerless cases. It explicitly left timeout, positive message, historical suppression, restart, late answer, concurrent disable and scheduler paths incomplete. Continue original task in `ticket-08-remaining-matrix.*`; do not treat partial test coverage as final acceptance or request human approval yet.

## Bounded implementation checkpoints (not final acceptance)

`99c1341` added guards/CLI hardening but still left the full matrix incomplete. Root continues implementation in the same independent task through explicit checkpoints without changing the full goal.

`204edc8` adds two actual receiver HTTP timeout tests (final answer exact-byte/hash timeout archive; answerless release with no archive), duplicate event and blocked old-session checks. Implementer reports 116 full tests and browser pass. This does not prove the remaining message/provenance/restart/scheduler paths or close final dual review.

Current checkpoint `ticket-08-contact-matrix.*`: actual signed receiver, controlled API message POST, real candidate ledger/verified history, ten-minute controllable clock, durable per-resource origin and routine-policy approval versus historical separation. Subsequent checkpoints remain restart/unknown delivery, late-answer/status reversal, concurrent disable, scheduler and executable human packet. Production remains untouched; no human gate requested for unfinished implementation.
