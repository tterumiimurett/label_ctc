# Ticket 06 implementation report

Implemented an opt-in outbound engine for approved missing-result candidates. It uses the existing fresh reconciliation and message-history interfaces, rechecks current state before sending, sends exactly one ordinary message with the approved wording, and records a durable `sending` intent before the POST. Candidate approval is separate from activation; `enabled=False` is the default and callers must provide explicit session IDs. Delivery errors are reconciled once and become `delivery_unknown` when not confirmed; they are never blindly retried. Sending does not mark a submission RETURNED or alter review, payment, or allocation state.

The real adapter uses the documented `POST /api/v1/messages/` contract with `recipient_id`, `body`, and `study_id`. Tests use a controlled opener and synthetic records only; no production credentials, participant data, messages, or runtime state were used.

## Review

Standards review: fixed the initial formatting/line-length issues in the new module and adapter method. No remaining documented-standard or baseline-smell findings were identified in the isolated diff.

Spec review: the implementation covers fresh recheck, one operation, durable pre-send state, default-off activation, separate candidate approval, unknown delivery handling, and no RETURNED/payment/review mutation. Historical approval remains an operational prerequisite; this ticket does not send historical candidates implicitly.

## Verification

- `python3 -m unittest tests.test_ticket_06_outbound -v` — 5 passed
- `python3 -m unittest discover -s tests -v` — 76 passed
- `python3 -m py_compile prolific/ctc_verification_app/outbound.py prolific/ctc_verification_app/reconciliation.py`

## Operational prerequisites

Before any future live use, an operator must verify credentials, workspace/message visibility, current candidate and history approval, and the production API contract/read-only state. Live sending remains disabled by default and was not executed here.

## Defect-fix demonstration (integrated branch)

The reproduced defects are covered by controlled synthetic tests: concurrent calls sharing the JSON ledger produce one send and one manual-review result; a latest draft, archive, other-session result, local error, or `return_requested` blocks sending; changing the approved participant from `P1` to `P9` produces manual review; interrupted `sending`/`delivery_unknown` states query history and never resend; and a malformed response is recorded as delivery unknown rather than sent. The composed adapter is `ProlificFreshReconciliation` delegating its one outbound operation to `ProlificSubmissionClient.send_message`.

The exact approved body remains the `APPROVED_MESSAGE` template with the candidate session ID. The demonstration used synthetic `STUDY`/`S1`/`P1` records and controlled HTTP/openers only. Activation is still explicit (`enabled=False` by default), candidate IDs and message-history clearance are independently required, and no real message was sent.

Post-fix verification: 11 focused Ticket 06 tests and 87 full-suite tests passed.


## Revised human-review policy demonstration — 2026-09-10

The integrated policy distinguishes routine new cases from historical backlog using durable ledger provenance: candidates created by the current ten-minute/fresh-reconciliation flow carry `candidate_origin: new` and may auto-execute only when activation is enabled; legacy candidates without that provenance remain visible but require a separately supplied `historical_sessions` approval list. No participant/session list is required for routine new cases, and activation remains default-off. This is a local policy distinction, not an inference from completion code or stale exports.

Synthetic controlled outcomes: empty complete history is eligible; a researcher-only older outgoing message with no newer participant reply is eligible; a participant reply after the latest researcher outgoing message, participant-only history, missing timestamps, or failed history access is manual; a known prior return request or platform `return_requested` is manual with no POST; a final answer arriving at the per-recipient fresh check is durable manual review with no POST; drafts, archives, other-session evidence, identity drift, and read errors are manual. The exact approved ordinary wording remains unchanged, and exception cases do not receive it automatically.

The cross-ticket timeout sequence remains protected: timeout records the attempt before the POST, candidate rebuilding preserves `delivery_unknown`, recovery queries history without resending, and acknowledged `sent` remains protected even if state is mutated. Controlled HTTP tests validate the real client POST shape and the composed fresh-reconciliation adapter; no real send occurred.

Operational prerequisites remain: human approval of the activation rule, credentials and workspace/message visibility, verified API contract and message-history coverage, explicit historical backlog list approval, production scheduling/HTTPS configuration, and a separate live read-only validation.
