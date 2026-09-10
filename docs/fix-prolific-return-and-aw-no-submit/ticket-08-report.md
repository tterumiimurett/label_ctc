# Ticket 8 implementation report

Implemented the isolated activation boundary in `prolific/ctc_verification_app/activation.py`.

- `preview()` consumes only a completed read-only reconciliation report and records a hashed action preview. It requires study, workspace, permission, identity, and read-only gates.
- `execute()` is usable with temporary local storage and injected archive/release/candidate callbacks. It records every completion/failure and refuses production execution.
- A durable sidecar disable switch prevents future actions. Failures record type and session without secrets or participant content.
- Candidate execution requires explicit `candidate_origin` (`new`, `historical`, or `unknown`); unknown is never upgraded automatically.

## Evidence boundary

Isolated evidence: `tests/test_ticket_08_activation.py` and the existing full suite. No production API GET, credential, HTTPS endpoint, webhook, assignment, message, archive, release, service restart, or production-data mutation was performed. Therefore live validation is **not verified**.

The repository does not contain a trustworthy workspace identifier, authorized credential, HTTPS receiver inventory, scheduler inventory, or a production-data copy in this worktree. Those are concrete human/operator prerequisites, not inferred from tests.
