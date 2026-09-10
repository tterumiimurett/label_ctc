# Ticket 8 implementation report

Current branch: `codex/prolific-ticket-08-20260910`. Latest implementation commits include `0c42926` (resource-isolated receiver/scheduler), `204edc8` (real timeout HTTP matrix), `6a604ba`/`0c94e50`/`0c42926` follow-up integration, and the current approved-transition fix.

## Executable evidence

From the repository root:

```sh
python3 -m unittest discover -s tests -v
NODE_PATH=/tmp/ticket1-ctc/node_modules node tests/browser_ticket_01_ctc.cjs
python3 -m unittest tests.test_ticket_08_crossresource tests.test_ticket_08_approved_transition -v
```

Current evidence: full suite `120` tests passing; browser artifact: [`artifacts/ticket08/browser-final.json`](../../artifacts/ticket08/browser-final.json). The real Playwright browser proof passes task/instruction visibility, audio playback (`currentTimeAdvanced: true`), no-task state, network failure, invalid JSON, and null-payload error states. Controlled HTTP evidence includes RETURNED archive/release, TIMED-OUT archive/release, routine missing-result message delivery, durable scheduler reassessment, cross-resource receiver/scheduler isolation, and APPROVED-after-missing durable manual review.

The authentic adapted cross-resource fixture is `tests/ticket08_crossresource_http_fixture.py`; its scheduler variant is `tests/ticket08_crossresource_scheduler_fixture.py`. The approved-transition fixture is `tests/ticket08_approved_transition_fixture.py`.

## Policy separation

Routine policy is represented by the persisted approval’s `routine_enabled` rule and study binding. It authorizes future eligible NEW cases; it is not a per-session NEW allowlist. Historical sessions remain separately listed and require explicit historical approval. The executable CLI configuration requires `verified_message_scope`, `activation_boundary`, and `routine_policy: true`; execution remains off unless the operator supplies the explicit `--execute` flag and a persisted approval. Code acceptance is evidenced by isolated tests and controlled HTTP only. Human gates remain required for production activation, live credentials/message visibility, HTTPS receiver/subscription inventory, and the historical action/contact list. Production authorization is not present and no production action was run.

## External blockers

No authorized live credential/workspace/HTTPS production receiver inventory was available. No live GET or write was attempted. These are live-operation prerequisites, not substitutes for the isolated implementation evidence.


## CLI acceptance shape

A controlled fixture configuration must contain `study_id`, `data_dir`, `base_url`, `token`, `auto_labels`, `verified_message_scope` (researcher/workspace IDs, coverage interval, visibility verification, note, checked/expiry times), `activation_boundary`, and explicit `routine_policy: true`. Run `python3 -m prolific.ctc_verification_app.activation_cli --journal <journal> receiver --config <fixture.json> --secret <fixture-secret>` for default-off reception; add `--execute` only against an approved local controlled API fixture. `approve --routine-policy` records the future-NEW rule, while `--historical-session` remains a separate explicit list.
