# Ticket 8 human verification packet

This packet is a stop point. Do not activate production actions until a human signs each gate.

## Operator supplies

1. Study ID, workspace ID, authorized read-only credential, and confirmation that message visibility is permitted.
2. Existing webhook subscription/secret inventory, HTTPS receiver and scheduler ownership. Do not overwrite existing integrations.
3. A sanitized current-state report and a separately approved historical candidate list. Never paste tokens, completion codes, or participant data into git or chat.

## Read-only gate

Run the reconciliation/backfill with GET-only credentials and save the report outside git. Verify pagination counts are consistent; any `platform_query_failed`, identity mismatch, storage error, or permission error is pending/manual and not absence. Confirm proposed archive/release/message actions against session, study, and participant identity.

## Isolated action gate

Run the activation tests with a temporary `VerificationStore` and injected callbacks. Exercise RETURNED with/without answers, TIMED-OUT with/without answers, duplicate/out-of-order events, restart recovery, late answers, delivery-unknown, and action-log disable. Confirm no payment/review/return-state API is called.

## Browser gate

Using the isolated preview server only, use a real browser to: load instructions; start the task; play the supplied audio and observe controls; trigger an unavailable-assignment/API failure and observe visible failure text. Capture screenshots or a screen recording. A synthetic HTTP 200 is insufficient. Do not create production allocations or use the production participant page.

## Activation decision

Human reviewer records: `PASS` / `FAIL` / `BLOCKED`, evidence paths, date, reviewer identity, and the exact approved session/action list. Production activation remains a separate approval. This implementation does not enable webhooks, send messages, archive/release production records, migrate data, or restart services.
