# Archive-only activation — 2026-09-11

## Authorization and scope

The user explicitly requested deployment of automatic archival after learning that preview services had not moved existing RETURNED/TIMED-OUT results. This authorizes existing and future confirmed RETURNED/TIMED-OUT local results for study 6a1bb20dfc7bbfabecc480ff. The latest timeout decision supersedes the initial spec's manual-only timeout rule; see ../issues/04-timed-out-claims.md and ../human-review-2026-09-10.md.

No outbound messages, platform submission/payment changes, study resumption, or automatic restoration are enabled by this deployment. A dedicated archive-only polling entrypoint uses the existing transaction implementation; the combined activation scheduler remains preview-only. HTTPS webhook ingress is not a dependency of polling and remains a separate unfinished deployment item.

## Acceptance

- Fetch current platform detail and verify session, participant and study identity before archival; uncertain evidence must not be treated as no answer.
- Move exact original bytes to dated excluded_submissions/<date>/prolific_returned or prolific_timed_out categories.
- Preserve lifecycle evidence and release allocation once; repeated runs must not repeat moves or restore excluded answers.
- Recover interrupted transactions; API/storage/identity errors appear in the private report for review.
- Run automatically with a persistent systemd user timer, every five minutes after the previous run finishes. This is polling, not immediate webhook delivery.
- Keep all real participant records, private config and logs out of Git. Log safe status summaries without credentials or completion codes.
- Validate current archival against pre-run file hashes, leave unaffected results unchanged, confirm the annotation page and health remain available, and validate a second run is harmless.

## Deployment status

Deployed and verified for automatic archival of local final results. The service and enabled timer are active; first and second execution evidence is recorded below.

## Operator controls

Unit names: prolific-archive.timer and prolific-archive.service. Stop both units to stop scheduled and in-flight processing: `systemctl --user stop prolific-archive.timer prolific-archive.service`. A stopped in-flight transaction retains its recovery journal. Do not delete lifecycle records or move files back by hand. Restart timer with `systemctl --user start prolific-archive.timer`; an immediate check can be requested with `systemctl --user start prolific-archive.service`.

Private report: logs/prolific-sync/archive-status.json. A timer being active is not evidence that a run succeeded: inspect the service exit status and report checked_at/counts, including manual_review entries. Per-session read/identity/archive failures are retained in that report and do not authorize sending messages.

Host persistence: user linger was enabled successfully for label on 2026-09-11 so the user timer can run without an interactive login. Unit configuration was validated using systemd-analyze before installation.

Pre-run backup: logs/deployment-backups/archive-20260911T015509Z contains 295 final result files and allocation state, with a private hash manifest. Fresh read-only detail checks confirmed two RETURNED and one TIMED-OUT local results with matching three-field identities. Real identities and hashes are retained only in logs/prolific-sync/archive-preflight.json.

## Independent review

Implementation commit 28f4e129d29c19c8ba412ec9b116d62504eb41fd, fixed baseline 835775a. Two independent code-review axes completed:

- Standards: no hard breaches; one nonblocking coupling observation (poller calls the store's private recovery helper under the shared lock). Six archive tests independently passed. No new human decision required.
- Spec: no blocking findings; six archive tests independently passed. Fresh identity/status checks, byte preservation, consent/error protection and no messaging scope matched the approved request. Actual deployment verification remains necessary.

This change preserves existing app recovery defaults; it does not claim that every pre-existing annotation-app recovery path now revalidates remote status.

Final merged-code test run: 152 tests passed in 13.727 seconds. Real read-only polling produced unchanged=292, would_archive=3, with no manual-review rows. Browser smoke check showed task, instructions and playable audio in the isolated preview, no production API calls, and the production entry returned its expected heading. This is not evidence of a new real participant submission being saved.

## First production execution

First archive service execution finished with Result=success and ExecMainStatus=0. Counts: processed=3, unchanged=292, no manual-review rows. Two results were archived under prolific_returned and one under prolific_timed_out. All three archive hashes match the original bytes; original formal paths and associated assignments are absent; lifecycle terminal statuses match their categories. All 292 remaining formal results are byte-identical to the pre-run backup. Evidence is private: archive-first-run.json, archive-validation.json, archive-preflight.json under logs/prolific-sync/.

Timer is enabled and user Linger=yes. A second real execution was started to verify repeated checks do not move or modify results again; final evidence follows when it finishes.

## Completion evidence

Second real execution completed with unchanged=292, no processed/manual rows. All formal results, excluded result JSON files, assignments and lifecycle bytes match the post-first-run snapshot (zero changes). Archive-only deployment is complete for the authorized local-results scope. Future runs start five minutes after the preceding run ends; actual detection latency also includes API scan duration.

Stop command: `systemctl --user stop prolific-archive.timer prolific-archive.service`. Combined sync remains preview-only; webhook delivery, no-result claim reconciliation, outbound messaging and study resumption are not claimed complete here.
