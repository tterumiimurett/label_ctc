# Revised Ticket 4 and 6 — review in progress

2026-09-10. Authoritative requirements: main `541b4a0`; updated issues and human-review-protocol. User confirmed automatic continuation after successful tests, independent dual-axis review and fixes when no human verification matter remains. This does not authorize production.

## Fixed review ranges

- Ticket 4: `96a2ef7...f6ea952`; original independent task `01a0852b-94eb-7673-8d9d-c5502859bf0e`.
- Ticket 6: `96a2ef7...ab938e8`; original independent task `01a0852b-9a79-7be0-8386-8876171cbcde`.
- Root independently reran full tests: Ticket 4 84 passed, Ticket 6 93 passed. Passing tests did not cover the defects below.

## Standards

No hard AGENTS violations. Ticket 4 has stale answered-timeout documentation and RETURNED-specific names/messages in a shared timeout/archive path. Ticket 6 duplicates state decisions between candidate building and sending, with inconsistent outcome vocabulary. These are heuristic findings; functional consequences are independently reviewed by Spec.

## Spec — confirmed findings, final report pending

- Ticket 4: mixed recovery of an archived-answer timeout and an answerless timeout can restore a released assignment from a stale map. Reviewer reproduced completed TIMED_OUT lifecycle records with an old assignment still present. Requires mixed-intent regression and coordinated fresh assignment state.
- Ticket 6: candidate regeneration resolves arrived answers or marks prior contact as contacted instead of routing an existing missing case to manual review.
- Ticket 6: first observation of historical backlog can label it new, bypassing separate historical approval when sender activation is enabled.

## Recovery point

Original tasks resumed with Implement for fixes; Standards and Spec findings handed off. Run artifacts are `/tmp/prolific-round-c-20260909/ticket-04-review-revision.*` and `ticket-06-review-revision.*`. Queued findings must be confirmed consumed, or delivered by resuming the same task only after terminal evidence. Re-review actual fixed commits on both axes before integration. Neither ticket is merged; Ticket 8 remains blocked on this round. No production actions occurred.

## Final Spec report and follow-up

Spec confirmed one Ticket 4 P1 (mixed-intent stale assignment recovery) and four Ticket 6 findings: P1 historical origin, P1 candidate/manual routing, P1 unknown chat sender or equal-time ordering ambiguity, and P2 interrupted delivery recovery skipped by normal iteration / mismatched prior-contact vocabulary. No new human business decision was identified; all require fixes against confirmed policy.

Ticket 4 Standards-only fix `83f071f` completed; original task resumed for the remaining mixed-intent defect. Follow-up artifacts: `/tmp/prolific-round-c-20260909/ticket-04-spec-fix.*`.

Ticket 6 initial fix `f4fc465` completed, addressing shared manual transitions and prior-contact vocabulary. It is not evidence that the final Spec blockers are fixed. Original task resumed for historical-origin distinction, unknown sender/order handling, and automatic no-resend delivery recovery. Follow-up artifacts: `/tmp/prolific-round-c-20260909/ticket-06-spec-fix.*`.

Re-review must include all original findings and actual final commits. No integration approval inferred from either partial fix.

## Ticket 4 re-review at c46ef317

Standards passed; root full suite passed 85 tests. Spec still fails P1: helper-local assignment reload leaves `reconcile_timed_out` caller state stale, so pending archive A followed by a new public timeout reconciliation B can restore A. Reusable isolated repro: `/tmp/ticket04-spec-review-repro.py`; run `PYTHONPATH=. python3 /tmp/ticket04-spec-review-repro.py` from Ticket 4 worktree. Original task resumed for all-caller correction and public-entry regression in `/tmp/prolific-round-c-20260909/ticket-04-spec-fix2.*`. No new human decision needed; no merge.

## Latest review checkpoint

Ticket 4 code `8df6d3b`: Spec passes independently; public repro now leaves no assignments, 21 focused assignment tests pass; root full suite 86 passed. Standards code passes, but final report has obsolete behavior/gate claims and control characters. Original task is correcting report only in `ticket-04-report-fix.*`; verify final documentation commit before merge.

Ticket 6 `f51c7e9`: both axes still require fixes. Initial-report answer arrival resolves silently; attempted-entry rebuilding overwrites manual status; unknown/unavailable delivery does not persist manual handling; some sender branches return manual decisions without saving them. Isolated public repro `/tmp/ticket06-spec-review-repro.py`. Original task resumed in `ticket-06-spec-fix2.*` for complete-path fixes. Explicit origin and strict sender/timestamp guards improved, but do not compensate for these remaining defects. No new human policy question.

## Ticket 4 accepted and merged

Final code `33b3bcb` passed independent Standards and Spec reviews with no remaining human matters under the confirmed conditional gate. Root full suite: 87 passed before and after merge. Main merge: `b228cec`. Consent guard, both recovery repro paths, original-byte archives, identity/status isolation and old-session barriers verified. No production action. Ticket 6 still requires outbound/manual persistence fixes; Ticket 8 cannot start yet.

## Ticket 6 outbound fix checkpoint

At `9e0833a`, root expanded public reproduction now verifies: unknown origin manual/zero POST; historical unapproved zero POST; new one POST; answer arrival/prior request manual; clear/prior-contact/unavailable attempt recovery manual with zero POST and manual survives rebuilding; missing fresh row and acknowledged contact persist manual. Full suite: 95 passed. Independent dual-axis re-review remains pending; valid-identity repro success does not cover malformed identity branches or original identity preservation on mismatch.

At `9e0833a`, both reviewers confirmed two remaining identity paths: manual routing overwrites original ledger identity with conflicting fresh identity; malformed/missing identity returns a manual decision without persisting the queue state. Repros appended to `/tmp/ticket06-spec-review-repro.py`. Original implementation task is fixing these in `ticket-06-identity-fix.*`; preserve original identity and store fresh conflicting observations separately. No new human policy decision is required. Ticket 6 remains unmerged.

## Ticket 6 identity fix re-review

At `249d7df`, root expanded reproduction and 96 full tests pass all earlier cases. Standards passes. Spec identified two new helper regressions: first-observed manual cases drop valid observed study/participant if no original ledger identity exists; fresh uncertainty drops concrete draft/error/return-request details and prior evidence. Repros appended to the shared isolated script. Original task resumed in `ticket-06-evidence-fix.*` to preserve observed identities and cumulative concrete evidence. Not approved for merge; no new human decision required.

## Ticket 6 accepted and merged

Final `4b116b8` passes independent Standards and Spec reviews with no remaining human matters under the user-confirmed conditional gate. Root expanded public repro passes and 97 branch tests pass; main merge `86cec8f` passes all 107 integrated tests. Ticket 4 and 6 round complete. Ticket 8 must verify integrated trustworthy new/historical classification, real read-only prerequisites and isolated end-to-end/browser evidence. Production activation and historical messaging remain separately gated.
