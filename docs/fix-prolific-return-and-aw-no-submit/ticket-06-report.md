# Ticket 06 implementation report

## Final behavior

Routine newly eligible cases may be sent automatically only when activation is enabled and the candidate carries explicit `candidate_origin: new` provenance. The sender does not require an individual approved-session list for those cases. Historical candidates require a separate explicit `historical_sessions` approval set. Unknown origin is fail-closed and enters the manual queue.

All outbound lifecycle transitions use the shared durable ledger and lock. The sender persists `sending` and attempt metadata before the POST. A first POST timeout or malformed response may remain `delivery_unknown` as the delivery observation, but any recovery examination—clear, inaccessible, unresolved, or prior-contact history—persists `manual_review` without resending. Missing latest submissions, latest reconciliation failures, history failures before POST, arrived answers/status, drafts, archives, other-session results, identity changes, and acknowledged sends all persist manual review. Accepted `message_id`, `send_outcome`, timestamps, original identity, and evidence remain in the ledger when a sent case is requeued for confirmation.

Chat eligibility uses complete ordered history: empty history and researcher-only history with no newer participant reply are clear; participant-only history, newer participant replies, unknown senders, equal timestamps, missing timestamps, and unreadable history are manual/ambiguous. A known prior request or platform `return_requested` is manual and never POSTed. No Session-ID text inference or LLM is used.

## Origin contract for Ticket 8

`build_contact_candidates(..., candidate_origin=...)` requires one of `new`, `historical`, or `unknown`. Ticket 8 must derive this from a durable processing/activation or backfill context and persist it. It must never infer `new` from first observation time, AW status, completion-code class, or absence of a ledger row. `new` is the only auto-eligible origin; `historical` is eligible only when named in `historical_sessions`; `unknown` queues manual review.

## Reproduction evidence

`PYTHONPATH=. python3 /tmp/ticket06-spec-review-repro.py` now reports: unknown origin `manual_review`/0 POSTs; historical origin `candidate`/0 POSTs pending separate approval; authorized new origin `sent`/1 POST; answer arrival `manual_review`; return requested `manual_review`; clear/prior-contact/unavailable recovery all `manual_review`/0 POSTs; candidate rebuilding preserves manual state; missing latest row persists manual with the original stored identity; and acknowledged sent reprocessing persists manual while retaining send evidence.

These are synthetic controlled adapters/JSON ledgers only. No production API, participant data, message, archive, deployment, or runtime mutation was used.

## Verification

- Focused Ticket 06/Ticket 5 tests: 34 passed
- Full suite: 96 passed
- Public reviewer reproduction: passed with the expected ledger states
- `git diff --check`: clean

Root’s independent dual-axis review remains pending. This report does not claim review approval or production authorization.

## Operator prerequisites

Before any live activation: root review must pass; an operator must approve the activation/rule context, verify credentials and workspace/message visibility, validate current read-only API state and history coverage, separately approve any historical backlog list, and configure the controlled scheduler/HTTPS environment. Live sending remains disabled by default and was not performed here.


## Identity-preservation review fix

Manual queue transitions now preserve the original ledger `study_id`, `participant_id`, and session identity, along with all irreversible attempt fields. A fresh conflicting identity is recorded separately as `observed_study_id`/`observed_participant_id` with conflict evidence; malformed or missing values are recorded as invalid observations and never promoted to trusted identity. Builder and outbound callers use the same helper.

The expanded synthetic reproduction now also verifies original identity preservation and malformed-identity manual queuing. Root independent dual-axis review remains pending.
