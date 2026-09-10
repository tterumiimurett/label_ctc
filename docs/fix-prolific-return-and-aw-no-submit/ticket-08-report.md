# Ticket 8 implementation report

Final reviewed implementation: `356078c`; merged into main as `d72663b`. Current acceptance: [completion-audit.md](completion-audit.md).

## Reproducible evidence

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 tests/ticket08_cli_smoke.py > artifacts/ticket08/cli-smoke-final.json
python3 -m unittest tests.test_ticket_08_cli_smoke tests.test_ticket_08_approved_transition tests.test_ticket_08_answer_arrival_guards -v
python3 -m unittest tests.test_ticket_08_authentic_recovery tests.test_ticket_08_concurrent_disable tests.test_ticket_08_crossresource tests.test_ticket_08_lifecycle_guards -v
python3 -m unittest tests.test_ticket_08_lifecycle_guards.NoOpLifecycleRegressionTest tests.test_ticket_08_concurrent_disable.ConcurrentDisableIntegrationTest -v
NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
```

Current full-suite evidence: **135 tests passed**. Browser evidence is at [`artifacts/ticket08/browser-final.json`](../../artifacts/ticket08/browser-final.json): visible task/instructions, audio playback, no-task state, network failure, invalid JSON, and null-payload states.

Controlled integration evidence covers signed receiver/archive and timeout paths, routine NEW ten-minute message delivery, reconstructed scheduler state, cross-resource isolation, disconnected POST restart recovery, concurrent disable, durable lifecycle manual outcomes, consent-source validation, historical approval records, and missed-event surfacing. These are isolated localhost/temp-store tests only.

## Read-only pagination correction

The documented Prolific `ordering=started_at` parameter is now sent on every submissions list page. The focused transport regression asserts the query on the first and subsequent page requests while retaining duplicate-ID, stable-count, malformed-response, and pagination-failure safeguards. Root's separate read-only evidence records 2,952 rows, 2,952 unique IDs, zero overlap, stable metadata, and equality with the study-scoped endpoint in [`sorted-pagination-evidence.json`](/home/label/label_ctc/docs/fix-prolific-return-and-aw-no-submit/sorted-pagination-evidence.json) and [`live-pagination-investigation.md`](/home/label/label_ctc/docs/fix-prolific-return-and-aw-no-submit/live-pagination-investigation.md). No live API call was made in this change.

## CLI controlled configuration

The actual executable setup is `python3 tests/ticket08_cli_smoke.py`; it creates and removes its own temporary localhost fixture and produced [`artifacts/ticket08/cli-smoke-final.json`](../../artifacts/ticket08/cli-smoke-final.json).

Sanitized fixture configuration:

```json
{
    "study_id": "STUDY-FIXTURE",
    "data_dir": "/tmp/ticket08-controlled/data",
    "base_url": "http://127.0.0.1:39001/api/v1",
    "token": "CONTROLLED_FIXTURE_ONLY",
    "auto_labels": ["/tmp/ticket08-controlled/candidate.jsonl"],
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

The JSON above is a shape-only production template: its paths, token, dates, and
fixture URL are not production credentials or activation instructions. The tested
fixture is generated with current UTC scope dates by `tests/ticket08_cli_smoke.py`,
uses a temporary `candidate.jsonl`, and places `approval.json` below the same
temporary `data_dir`.

The smoke harness actually tested the following operator sequence:

```sh
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl preview --report /tmp/ticket08-controlled/report.json
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl approve --approval /tmp/ticket08-controlled/data/approval.json --study-id STUDY-FIXTURE --preview-sha256 DIGEST --approved-by fixture-reviewer --preview-report /tmp/ticket08-controlled/report.json --routine-policy
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl status
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl receiver --config /tmp/ticket08-controlled/config.json --secret CONTROLLED_SECRET --port 38991
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl scheduler --config /tmp/ticket08-controlled/config.json --interval 0.1
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl disable "fixture stop"
python3 -m prolific.ctc_verification_app.activation_cli --journal /tmp/ticket08-controlled/journal.jsonl status
```

Receiver and scheduler are default-off; `--execute` is required for any controlled mutation. Preview emits the normalized digest used by approval. Historical approvals contain exact normalized action, identity, and digest records; routine policy is independent of the changing report hash.

## Human/live gates

The implementation task made no live calls. Root completed authorized real API read-only reconciliation and code classification (see completion-audit.md); credentials and read access were verified. No production writes, webhook enablement, deployment, restart, or participant messages were performed. Before activation, verify workspace/message visibility, HTTPS receiver/subscription inventory and scheduler ownership, then obtain explicit production/historical-action authorization. Previously confirmed business rules are not re-submitted for approval.


The documented CLI preview/approve/status/receiver/scheduler/disable/restart sequence was executed by `python3 tests/ticket08_cli_smoke.py > artifacts/ticket08/cli-smoke-final.json` against temporary sanitized data; it returned approved, status disabled=false, preview-only receiver response, scheduler cycle observed, disabled, and status disabled=true after restart. The harness dynamically binds its local port, signs the receiver request with request and event timestamps, and cleans up all processes and temporary files. Receiver/scheduler remain default-off unless `--execute` is explicitly supplied.

## Answer-arrival amendment

The authoritative amendment is copied to [`answer-arrival-amendment.md`](answer-arrival-amendment.md) and synced into the spec and missing-result ticket. An identity-matched complete final answer in `AWAITING REVIEW` now resolves a waiting case without a message or new manual item, including initial observation and reconstructed fresh reassessment; the authentic approved-transition fixture submits through `VerificationStore`, reconstructs the stack, and repeats assessment. Status changes, prior contact, uncertain delivery, identity conflicts, drafts, errors, other-session results, existing manual records, and outbound attempts remain protected. The focused amendment tests cover initial answer, five-minute answer arrival after a durable first-missing observation, ten-minute reconstructed reassessment, due fresh-only candidate-builder answer arrival behind a fixture-local read barrier followed by a separately reconstructed scheduler stack, repeated reconstruction, approved-status manual behavior, stored-identity conflict, contacted-without-attempt metadata, and delivery-unknown recovery without attempt metadata; answer paths produce zero POSTs while guarded states remain manual/recovery-protected. The positive approved-new fixture separately proves one accepted POST, a persisted `sent` state before reconstruction, and a reconstructed follow-up `manual_review` with attempt count unchanged at one.

## Explicit personal-message scope

The existing workspace scope remains unchanged. A separate config may explicitly select personal history only with `message_scope.mode: "personal"` and proof for the sole-member workspace:

```json
{
  "message_scope": {
    "mode": "personal",
    "researcher_id": "RESEARCHER-FIXTURE",
    "workspace_id": "WORKSPACE-FIXTURE",
    "coverage_start": "2026-09-01T00:00:00Z",
    "coverage_end": "2026-09-30T00:00:00Z",
    "workspace_visibility_verified": false,
    "verification_note": "separate sole-member personal-history proof",
    "checked_at": "2026-09-10T00:00:00Z",
    "expires_at": "2026-09-10T23:59:59Z",
    "personal_proof": {
      "proof_kind": "current_users_me_and_workspace_members",
      "sole_member_id": "RESEARCHER-FIXTURE"
    }
  }
}
```

Personal mode verifies the authenticated `users/me` identity and current workspace membership on each history inspection, requiring exactly one matching member. It reads the authenticated participant history without adding a workspace query. Missing identity, membership changes, permission failures, incomplete paging, unknown senders, expired scope, and malformed/conflicting timestamps fail closed. Message time aliases `datetime_created`, `created_at`, and `sent_at` are accepted only when valid and non-conflicting. The verified real environment currently has no workspace-message visibility and the personal-history mode has not been activated or live-tested by this change.
