# Round 3 review and human gate

Tickets 04/06 remain unmerged. Required human verification must occur after concrete reviewable evidence is prepared and before dependent merge/next-wave progress. No production sends or state changes authorized.

## Ticket04

Initial `dfd3ed9` (base `916ca46`): Standards passed; Spec failed interrupted release retaining capacity and repeated timeout observation identity bypass. Root also identified conflict state must not enter RETURNED recovery. Original session `01a0852b-94eb-7673-8d9d-c5502859bf0e` is fixing and integrating latest main in `/tmp/prolific-round-c-20260909/ticket-04`.

## Ticket06

Initial `00782dc` (base `916ca46`): Standards passed; Spec reproduced duplicate concurrent sends, sending despite draft evidence, approved identity substitution, missing uncertain-delivery recovery, and unvalidated success responses. Integration `748ebf1` includes main's real API pagination changes but does not itself close these findings. Original session `01a0852b-9a79-7be0-8386-8876171cbcde` is fixing in `/tmp/prolific-round-c-20260909/ticket-06`.

Human verification materials must show exact synthetic identities, candidate evidence and approved text, cancellation on changed data, once-only sending under repetition/concurrency, unknown-delivery handling and disabled production behavior. Synthetic send demonstrations must not contact real participants. Full current-state production lists remain separate read-only evidence; no claims of live positive-path validation without evidence.


## Follow-up review findings

Ticket04 `6c1bbbf`: Standards passed; Spec still reproduced repeated timeout identity mismatch acknowledged as already processed. Root requested persisted identity checks before recovery/acknowledgement and preventing RETURNED entry from consuming timeout/manual records; original session is fixing with regressions.

Ticket06 `a043f8f`: Standards passed (nonblocking duplicate uncertainty-rule suggestion); Spec reproduced actual cross-ticket resend: timeout -> delivery_unknown -> Ticket05 candidate pass -> candidate -> second POST. Fix requires both candidate-builder lifecycle preservation and irreversible send-attempt barrier in outbound, plus fresh per-recipient checks. Original session is fixing; no human-ready completion claim yet.


## Code review complete; human gate pending

Ticket04 `cf3792c`: Standards/Spec both pass; root83 tests, independent18 assignment tests. Ticket06 `f433324`: Standards/Spec pass; root91 tests, independent14 outbound tests plus actual candidate/ledger/outbound duplicate-delivery reproduction. Neither branch is merged. User-facing evidence is in `ticket-04-human-verification.md` and `ticket-06-human-verification.md`. Await explicit user verification of both; no Ticket08 start and no production actions.
