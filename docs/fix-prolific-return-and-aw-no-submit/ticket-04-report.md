# Ticket 04 implementation report

## Current behavior

Confirmed platform `TIMED-OUT` observations are handled by `VerificationStore` after session, study, and participant identity validation.

- With a final local answer, the original bytes are archived unchanged under `excluded_submissions/YYYY-MM-DD/prolific_timed_out/`. The lifecycle records the SHA-256, source identity, original assignment, reason, processing stage, and timestamps. The source result and matching claim are removed atomically through the staged exclusion transaction, releasing capacity exactly once.
- Without a final answer, only the matching pending claim is released. No answer file or archive is manufactured.
- Timeout lifecycle records remain explicitly `TIMED_OUT`; they are never converted into `RETURNED` records. Archive collisions, identity mismatches, inconsistent state, consent withdrawal, and unreadable data remain manual-review cases.
- Shared locking and recovery drain timeout intents globally, reload assignment state after each recovered archive, preserve archive bytes, prevent stale-map resurrection, and block old-session assignment, draft, and late-submit reuse.

## Relevant verification

- `python3 /tmp/ticket04-spec-review-repro.py` with `PYTHONPATH=.` now reports `remaining assignments []` after mixed archive and claim-release recovery.
- Commit `8df6d3b` contains the public-entry mixed-intent regression and prior timeout recovery coverage.
- `python3 -m unittest discover -s tests -v` — 86 tests passed.
- `python3 -m py_compile prolific/ctc_verification_app/app.py` — passed.
- `git diff --check` — passed.

## Review status

The requested Standards documentation finding is fixed in this report. Root’s independent Standards+Spec review of the current implementation remains pending; this report does not claim final Spec approval.

Per the latest human-review protocol (`main` `541b4a0`), automatic continuation is allowed only when review identifies no issue requiring human verification. If review identifies such an issue, root must pause and present the concrete evidence and required decision before merging or advancing the next wave.

## Human-verification demo and operational prerequisites

The evidence is synthetic and local only. A reviewer can create a temporary one-candidate store, assign and submit session A, create an answerless session B, confirm platform `TIMED-OUT` for both, and verify A’s exact bytes/hash in `prolific_timed_out`, no A/B assignments remain, a new participant receives the released capacity, and A/B cannot assign, save drafts, or late-submit. Inject failures after timeout intent, archive write, and claim deletion; reconstruct the store and verify one archive/release only. Submit mismatched study/participant observations and a subsequent `RETURNED` observation; verify manual review and unchanged timeout lifecycle.

Required operational prerequisites remain researcher confirmation of the study’s 14-minute maximum, current platform status through the read-only API/webhook path, credentials and workspace/subscription inventory, HTTPS receiver, scheduler, and any human verification required by the independent review. No production API calls, writes, archives, messages, deployment, restart, or runtime mutation were performed.
