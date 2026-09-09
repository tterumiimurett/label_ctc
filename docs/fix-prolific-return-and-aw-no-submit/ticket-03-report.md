# Ticket 03 implementation report

Implemented returned-session local lifecycle integration. `VerificationStore.reconcile_returned` accepts only a current `RETURNED` observation, validates study/participant identity, archives an existing final result under `excluded-results/prolific-returned/` with SHA-256/path evidence, or releases the pending assignment. A durable lifecycle record makes processing idempotent and prevents old returned sessions from reclaiming tasks. No Prolific API writes, messaging, webhooks, deployment, or runtime data changes were performed.

## Verification

- `python3 -m unittest discover -s tests -q` — 39 tests passed.
- Focused assignment/reconciliation tests — 16 tests passed.
- `python3 -m py_compile prolific/ctc_verification_app/app.py` — passed.

## Limitations and human checkpoints

Ticket 05 contact candidates and Ticket 07 triggers are intentionally not implemented. The lifecycle now writes a pending intent before archive/release effects, recovers pending intents on assign, uses an OS file lock for cross-process coordination, and rejects differing archive collisions without deleting the source. Archives use `excluded_submissions/YYYY-MM-DD/prolific_returned/` and preserve exact bytes. Consent withdrawal is an explicit manual-review input. Production execution remains off; current platform state must be read and independently verified by the caller before invoking the seam. Status reversal and consent withdrawal require human handling.
