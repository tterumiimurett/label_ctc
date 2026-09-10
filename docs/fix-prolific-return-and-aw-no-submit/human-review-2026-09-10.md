# Human review corrections — 2026-09-10

These user decisions supersede conflicting earlier Ticket04/Ticket06 assumptions. Neither ticket is approved for merge as currently implemented.

## Ticket04

User requires confirmed platform TIMED-OUT handled like RETURNED: final answers archived intact into a distinct dated prolific_timed_out category outside formal counting; release corresponding claims, preserve hashes/audit, block old-session reuse. No final answer means release only, do not manufacture an answer. Identity/storage ambiguity remains manual. Do not change Prolific payment/review state. This replaces the previous final-answer-present => keep formal/manual-only policy; implementation and tests must change before re-review/human gate.

## Ticket06

User approves the existing ordinary return-request wording. Routine eligible cases should send automatically once the rule and production activation are approved, without per-session human approval for every new eligible case. Exceptions require a durable manual queue and potentially different wording; do not automatically send the ordinary return request to exceptions. Historical backlog remains separately approved unless user changes that rule. Manual notification/UI mechanism is not yet delivered; current code uses explicit approved_sessions input and a local queue, not an interactive approval service. Candidate eligibility, history access, ten-minute recheck and irreversible no-resend safeguards remain required.

## Official timeout evidence

- https://researcher-help.prolific.com/en/articles/445206-submission-statuses-explained : timed out means not completed within allowed time; excluded from requested totals. Maximum based on intended duration. Active participants can sometimes finish beyond limit before replacement. Clear good-faith completion can still warrant manual approval; local archiving is our counting policy, not a finding that no work occurred.
- https://docs.prolific.com/api-reference/studies/get-study : maximum_allowed_time is minutes; API documents minimum 2 + 2*t + 2*sqrt(t). This is not evidence of this study's actual configuration.
- Current root environment lacks PROLIFIC_API_TOKEN; read-only GET was not issued. Existing inspected reports did not contain duration fields. Actual maximum_allowed_time for study 6a1bb20dfc7bbfabecc480ff remains unverified. N/A time taken alone cannot establish timeout minutes or absence of work.

Interruption/repetition refer to backend crash/restart and duplicate webhook/periodic processing, not audio interruption labels or participant repeating the task. Recovery/idempotency must preserve files and free each claim only once.


## Further user clarification

- User confirms this study's maximum allowed time is 14 minutes. Source is explicit researcher confirmation, not a root API observation. User approves backend interruption recovery and duplicate-processing safeguards.
- For a detected missing-result case under consideration for contact, a final answer subsequently arriving or evidence of prior contact must produce a durable manual-review item for the researcher, with no outbound message while awaiting review. Do not silently resolve/drop these cases. This is not an instruction to put all ordinary successful submissions into the missing-result review queue.
- User accepts a locally stored, inspectable manual queue; external notification service is not required by this clarification.
- User rejects interpreting any historical chat as automatic-contact disqualification. They suggest using whether a participant has replied since the researcher's latest outgoing message. Distinguishing the latest arbitrary outgoing message from a prior return request and deciding the effect of a pending participant reply requires clarification. No final rule is inferred yet; maintain one automatic return request per session and no blind resend.

These corrections are requirements for revisions, not approval of the existing Ticket04/06 branches or live operations.


## Final agreed chat rule and implementation authorization

User confirmed: complete empty history => automatic eligibility; no participant reply after researcher latest outgoing message => automatic chat eligibility; participant newer reply => manual. This does not bypass existing same-session request/attempt deduplication. Missing session text does not mean unrelated. User now authorizes revising both independent Ticket04/06 implementations and repeating the review loop. Standard message approved; exceptional-case custom wording remains manual. Previously accepted code versions are superseded for these changed behaviors and must not be merged unchanged.
