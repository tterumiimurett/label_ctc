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
