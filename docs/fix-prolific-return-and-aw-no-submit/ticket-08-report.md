# Ticket 8 implementation report

Branch: `codex/prolific-ticket-08-20260910`. Latest checkpoint: `461c87f` plus fixture cleanup changes in progress.

## Reproducible evidence

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_ticket_08_authentic_recovery tests.test_ticket_08_concurrent_disable tests.test_ticket_08_crossresource tests.test_ticket_08_lifecycle_guards -v
NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
```

Current full-suite evidence: **125 tests passed**. Browser evidence is at [`artifacts/ticket08/browser-final.json`](../../artifacts/ticket08/browser-final.json): visible task/instructions, audio playback, no-task state, network failure, invalid JSON, and null-payload states.

Controlled integration evidence covers signed receiver/archive and timeout paths, routine NEW ten-minute message delivery, reconstructed scheduler state, cross-resource isolation, disconnected POST restart recovery, concurrent disable, durable lifecycle manual outcomes, consent-source validation, historical approval records, and missed-event surfacing. These are isolated localhost/temp-store tests only.

## CLI controlled configuration

Sanitized fixture configuration:

```json
{
    "study_id": "STUDY-FIXTURE",
    "data_dir": "/tmp/ticket08-controlled/data",
    "base_url": "http://127.0.0.1:39001/api/v1",
    "token": "CONTROLLED_FIXTURE_ONLY",
    "auto_labels": [],
    "routine_policy": true,
    "activation_boundary": "2026-01-01T00:00:00Z",
    "verified_message_scope": {
        "researcher_id": "RESEARCHER-FIXTURE",
        "workspace_id": "WORKSPACE-FIXTURE",
        "coverage_start": "2025-12-01T00:00:00Z",
        "coverage_end": "2026-02-01T00:00:00Z",
        "workspace_visibility_verified": true,
        "verification_note": "controlled fixture only",
        "checked_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-02-01T00:00:00Z"
    },
    "consent_evidence_path": "/tmp/ticket08-controlled/consent.json"
}
```

The executable operator sequence is:

```sh
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl preview --report /tmp/ticket08-controlled/report.json
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl approve --approval /tmp/ticket08-controlled/approval.json --study-id STUDY-FIXTURE --preview-sha256 DIGEST --approved-by fixture-reviewer --preview-report /tmp/ticket08-controlled/report.json --routine-policy
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl receiver --config /tmp/ticket08-controlled/config.json --secret CONTROLLED_SECRET
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl scheduler --config /tmp/ticket08-controlled/config.json
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl disable "fixture stop"
```

Receiver and scheduler are default-off; `--execute` is required for any controlled mutation. Preview emits the normalized digest used by approval. Historical approvals contain exact normalized action, identity, and digest records; routine policy is independent of the changing report hash.

## Human/live gates

No production GET, write, webhook enablement, deployment, restart, or participant message was performed. Live prerequisites remain: authorized credentials, verified workspace/message visibility, HTTPS receiver/subscription inventory, scheduler ownership, and human approval of routine policy, historical action/contact lists, and production activation. No human is asked to repeat agent-executable isolated tests.
