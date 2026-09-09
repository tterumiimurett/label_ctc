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
