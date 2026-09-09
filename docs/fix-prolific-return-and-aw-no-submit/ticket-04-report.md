# Ticket 04 implementation report

Implemented durable timeout lifecycle handling in `VerificationStore`.

- `TIMED-OUT` without a final result records a terminal `TIMED_OUT` lifecycle, releases the matching assignment exactly once, and prevents assignment, draft, or late-submit reuse.
- `TIMED-OUT` with a final result remains untouched and returns `manual_review`; no RETURNED archive is created.
- Interrupted claim release is recovered under the existing lifecycle lock.
- Existing RETURNED semantics and archive/recovery behavior remain separate.

## Review

### Standards

Pass with one minor judgment call: the new method follows the existing standard-library-first, typed public-helper, atomic JSON, and lock conventions. The method is somewhat long and repeats identity validation patterns already present in RETURNED handling, but keeping the transaction beside the existing lifecycle transaction preserves the current seam and avoids sibling-ticket refactoring.

### Spec

Pass for Ticket 04. The implementation covers no-answer release, final-answer manual review, idempotency, old-session blocking, late-submit protection, lock coordination, and interrupted-operation recovery. No outbound API, archive, participant message, deployment, or runtime mutation was added.

## Verification

- `python3 -m py_compile prolific/ctc_verification_app/app.py`
- `python3 -m unittest discover -s tests -v`   71 tests passed
- `git diff --check`   passed

## Operational prerequisites

Production activation remains off. Before live use, operators must complete the spec's existing prerequisites: approved Prolific credentials and workspace, current API/subscription inventory, HTTPS receiver/scheduler, read-only validation/report review, and explicit activation approval. No production API calls, messages, restart, or deployment were performed.


## Final regression coverage

Added regressions for:

- repeated wrong-study/participant timeout observations returning manual review with lifecycle and assignment bytes unchanged;
- TIMED_OUT_MANUAL followed by RETURNED remaining manual with no conversion;
- crashes after timeout intent persistence and after claim deletion recovering on a new store/new participant allocation exactly once.

Human verification remains required before root merges. The concrete local synthetic demo is: timeout S1, allocate S2, repeat the timeout with mismatched identity, simulate each fault point, and verify preserved manual conflict when a final result exists. No production API, messaging, deployment, or runtime action is authorized or performed.
