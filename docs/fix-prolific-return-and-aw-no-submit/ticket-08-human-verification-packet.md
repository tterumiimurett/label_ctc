# Ticket 8 human verification packet

Agent-executable isolated work is complete through the evidence commands in `ticket-08-report.md`; human review is only for decisions and live authorization.

## Code gate

Reviewer runs:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_ticket_08_crossresource tests.test_ticket_08_approved_transition -v
NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
```

Expected current count: 120 passing tests. Evidence is temporary controlled HTTP/store/ledger data only; no participant or production data is used.

## Routine policy gate

Approve or reject the routine rule bound to the study, message-visibility scope, and activation boundary. Approval permits eligible NEW cases after the ten-minute recheck; it does not approve historical sessions.

## Historical gate

Review and separately approve the exact historical session/contact list. An unlisted historical session remains manual and receives no automatic message.

## Production gate

Before any production activation, a human must provide/verify authorized credential, study/workspace identity, current read-only report, existing subscription/secret inventory, HTTPS receiver, scheduler ownership, and the final action/contact lists. No payment/review/return-state changes, participant messaging, webhook enablement, deployment, restart, or production-data migration is authorized by this packet.

Record `PASS`, `FAIL`, or `BLOCKED`, reviewer, timestamp, evidence paths, routine-policy decision, historical-list decision, and separate production authorization decision.
