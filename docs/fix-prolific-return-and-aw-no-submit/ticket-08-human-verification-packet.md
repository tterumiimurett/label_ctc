# Ticket 8 human verification packet

Agent-executed evidence is complete for isolated controlled components; this packet records decisions that require human authority only.

## Commands and artifacts

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_ticket_08_authentic_recovery tests.test_ticket_08_concurrent_disable tests.test_ticket_08_crossresource tests.test_ticket_08_lifecycle_guards -v
NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
```

Current result: **125 tests passed**. Browser artifact: [`artifacts/ticket08/browser-final.json`](../../artifacts/ticket08/browser-final.json). No production data or credentials are in evidence.

## Decisions requiring human authorization

- Routine policy: approve/reject future eligible NEW cases for the named study, scope, and activation boundary.
- Historical list: separately approve exact identity-bound action/contact records. Unlisted or mismatched historical rows remain manual.
- Production activation: separately approve credentials, current read-only report, workspace visibility, HTTPS receiver/subscription inventory, scheduler ownership, and final action lists.

Production remains disabled. This packet does not authorize payment/review/return-state changes, participant messages, webhook enablement, deployment, service restart, or production-data migration.
