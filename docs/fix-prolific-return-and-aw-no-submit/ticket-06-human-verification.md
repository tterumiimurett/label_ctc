# Ticket 06 — human verification, pending

Reviewed commit: `f43332472549b67ef4b58ce7d62c55634b45cb85`.
Workspace: `/tmp/prolific-round-c-20260909/ticket-06`.
Independent session: `01a0852b-9a79-7be0-8386-8876171cbcde`.

Standards and Spec passed independently. Root ran all 91 tests successfully; Spec reviewer ran all 14 outbound tests and independently replayed the cross-ticket unknown-delivery sequence. This does not replace the human gate below. No real message was sent.

## Concrete isolated outcomes to inspect

| Synthetic case | Observed result | Required human check |
| --- | --- | --- |
| Approved candidate S1 / STUDY / P1, still AW and missing final, clear history | One ordinary message send; server message ID retained | Correct identity, wording and one-message behavior |
| Final answer arrives before recipient send | Cancel, no message for that recipient | Do not request return after answer arrives |
| First POST times out; repeat processing and candidate generation | Delivery remains unknown; total send calls stays 1 | Unknown delivery must not trigger a blind resend |
| Force state back to candidate with prior durable attempt | Still no second POST | Existing attempt wins over regenerated candidate state |
| Draft/archive/other-session evidence or changed participant | No send; manual review | Ambiguous cases need a human |

Approved wording for synthetic session S1:

> Hello, our records show that your Prolific submission is awaiting review, but we could not find a final annotation result for this session: S1. If you were unable to complete the annotation, please return this submission on Prolific. If you believe you submitted your answers successfully, please reply so we can investigate. We’re sorry for the inconvenience.

To inspect independently, open the workspace and run `python3 -m unittest tests.test_ticket_06_outbound -v`, or resume the independent session and request a walkthrough of these synthetic cases. Fixtures use controlled adapters/HTTP; do not substitute real credentials or enable production sends.

## Decision boundary

Awaiting user's explicit human verification of these outcomes and wording before Ticket06 merge. Approval here is approval of isolated behavior/code integration, not approval to send to any real participant. Historical recipient lists, live message access and production activation remain separate checkpoints. Ticket08 cannot start until the entire 04/06 round is complete.
