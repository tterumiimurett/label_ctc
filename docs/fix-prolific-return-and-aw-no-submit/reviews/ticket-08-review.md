# Ticket 8 independent review — initial implementation rejected

Base `377199a`; reviewed head `9cb14d5`. Original independent task `01a0890a-dc99-7113-afe8-d7020a3e0e2c`, workspace `/tmp/prolific-round-d-20260910/ticket-08`.

## Standards

No hard AGENTS violations. Two actionable Fowler heuristics: speculative callback/controller boundary does not compose existing services; claimed atomic/durable journal and disable semantics exceed per-object locks, unsynced marker and post-effect completion records.

## Spec

Seven findings: missing real synchronization composition; actual answered RETURNED/TIMED-OUT action names do not dispatch; stale supplied reports and missing trustworthy provenance; disabling during action A still allows B; no later approved activation path/entrypoint; missing real controlled-HTTP end-to-end crash/late/ordering evidence; browser and read-only acceptance deferred as instructions rather than executable evidence.

Actual reconciliation action names include `review_returned_with_result` and `review_timeout_with_result`; initial controller recognizes `archived_result` instead.

## Disposition

Original task resumed with Implement to complete full integration and evidence, with all Standards/Spec findings queued. Current run `/tmp/prolific-round-d-20260910/ticket-08-integration-fix.*`. Confirm queued messages consumed before accepting output. No merge or production execution.

Missing account access may block live read-only verification, but not agent-executable isolated integration/browser work. Finish concrete deliverables and independent reviews before requesting human verification. Approval of real read-only report, historical list and production activation remain separate gates. No new business-policy decision identified.

## Tool failure recovery and initial browser evidence

The first integration revision ended without a patch because default sandbox editing failed (`bwrap` loopback). This is not an external implementation blocker: root resumed the same task using normally approved escalated file editing in the authorized worktree. Current run `ticket-08-integration-fix2.*`.

Root inspected the completed browser command's actual output: exit 0, task/instruction visible, metadata/canplay true, playback advanced, no-task/network/invalid-JSON/null-payload failures visible. Sanitized output saved in `ticket-08-browser-initial.json`. This validates isolated Chromium/synthetic audio at initial9cb14d5; it does not prove complete integration or production audio. Final version must retain browser evidence and supply remaining full-chain proof.

## Re-review at 7a5d2d3 — still incomplete

Original task now added concrete service references and an ActionJournal. Standards reports missing public type annotations required by AGENTS, disable not covering outbound/candidate execution, and outcomes recorded as completed without actual result/reason. Root inspected four new tests: all use mocks, not the required actual-component chain. CLI only shows/disables the journal and explicitly lacks preview/activation execution. Existing browser proof does not close these integration gaps. Independent Spec review is checking actual trigger/report/action/status contracts before the next original-task revision. No human gate requested for incomplete work.

Final Spec at `7a5d2d3` confirmed: answered RETURNED action still skipped; normalized `TIMED OUT` passed to store is rejected; verified events do not initiate actions; arbitrary event dictionaries label whole-report history new; unbound activation boolean and disable bypass; stale lifecycle loop/outcomes/pending intents; non-executable activation CLI; mock-only integrated tests. `periodic()['report']` contract itself is correct. Root full suite 111 passed but misses these defects. Original task resumed in `ticket-08-fullchain-fix.*` for complete real-component/HTTP implementation. No new business decision required.

## Re-review at a64e1cf — rejected

Standards: public type hints/UTF-8 still incomplete; ApprovalStore's declared lock unused with shared temporary file; disable marker durability and actual manual outcomes missing. Spec: fresh APPROVED can still invoke fabricated RETURNED; answerless RETURNED is routed through TIMED-OUT; candidate/outbound phase removed and message history stubbed unavailable; caller context masquerades as accepted event and gives whole-report origin; whole-report approval digest blocks routine new cases while CLI accepts arbitrary digest; no executable execution/receiver/scheduler or pending-intent recovery; one integration test still calls a method directly and lacks message/crash/ordering/disable proof. Reader.send_message exists and is not a finding.

Original task resumed in `ticket-08-contract-fix.*`, keeping full existing phases while fixing the actual integration boundary. No new human policy decisions; complete agent-executable work before the live/human gates.

## cf268b0 and db553b2 checkpoints

Spec pinned cf268b0 reproduction `/tmp/ticket08-cf268b0-spec-repro.py` confirms disabled journal can still produce one message POST and normalized timeout causes zero timeout lifecycle calls. Public annotations/UTF-8/indentation, approval/routine provenance, audit/recovery and CLI execution remain unaccepted. That repro deliberately loads the old pinned code; final regressions must exercise current code.

Original task added receiver HTTP coverage at `db553b2`, reporting 114 tests, actual signed listener plus real API adapter/store for RETURNED final and answerless cases. It explicitly left timeout, positive message, historical suppression, restart, late answer, concurrent disable and scheduler paths incomplete. Continue original task in `ticket-08-remaining-matrix.*`; do not treat partial test coverage as final acceptance or request human approval yet.

## Bounded implementation checkpoints (not final acceptance)

`99c1341` added guards/CLI hardening but still left the full matrix incomplete. Root continues implementation in the same independent task through explicit checkpoints without changing the full goal.

`204edc8` adds two actual receiver HTTP timeout tests (final answer exact-byte/hash timeout archive; answerless release with no archive), duplicate event and blocked old-session checks. Implementer reports 116 full tests and browser pass. This does not prove the remaining message/provenance/restart/scheduler paths or close final dual review.

Current checkpoint `ticket-08-contact-matrix.*`: actual signed receiver, controlled API message POST, real candidate ledger/verified history, ten-minute controllable clock, durable per-resource origin and routine-policy approval versus historical separation. Subsequent checkpoints remain restart/unknown delivery, late-answer/status reversal, concurrent disable, scheduler and executable human packet. Production remains untouched; no human gate requested for unfinished implementation.

## 6a604ba positive-path test remains insufficient

The added test directly calls execute after ten minutes with a manufactured accepted_event and supplied study/event identity; it does not prove receiver/scheduler reassessment. Independent pinned fd8bac6 real HTTP repro produces candidate_origin_unknown despite verified history. No implementation changed in 6a604ba. Original task resumed in ticket-08-authentic-contact.* to fix durable event handoff and prove a routine future session without per-session preapproval. Final matrix, dual review and human gate remain pending.

## cf541f6 receiver checkpoint

Original task reports actual signed receiver reassessment after ten minutes, exact-one controlled message POST, 117 full tests and isolated browser pass. Independent verification pending. Continued same task in ticket-08-scheduler-recovery.* to prove scheduled reassessment without another event, restart and per-session provenance isolation, and uncertain delivery without resend. Full Ticket8 acceptance remains pending.

## Independent cf541f6 verification

Spec authentic positive HTTP reproduction passes with empty per-session approval lists. Cross-resource reproduction /tmp/ticket08-cf541f6-http-crossresource.py instead sends twice, including an unrelated pre-boundary OLD session without historical approval. Receiver applies one event origin to the whole report. Exact event lookup, scheduler action reassessment, and CLI boundary/scope/routine-policy wiring remain deficient. Findings queued to the active original task; no production calls occurred.

Root acceptance-packet audit: current packet still describes injected callbacks, asks for exact session/action approval without distinguishing routine policy from historical list, and defers executable read-only commands and existing browser evidence. Final packet must be rewritten around tested actual components and concrete operator steps after code is fixed; it is not ready for user verification.

## 0c94e50 scheduler checkpoint

Original task reports one event followed by scheduler +600 seconds yields one controlled message; 117 tests/browser pass. Still explicitly missing cross-session separation, restart/unknown-send, late/status-reversal, concurrent disable and final packet. Standards cf541f6 still flags public type hints and private trigger persistence coupling. Original task resumed in ticket-08-isolation-recovery.* with complete review findings and remaining matrix; no merge/human gate yet.

## 0c42926 isolation patch — regression not yet supplied

Implementation adds exact public event lookup, normalized headers and resource filtering; reports 117 tests/browser pass but explicitly omits requested cross-resource regression and remaining matrix. Continued original task in ticket-08-crossresource-test.* to execute authentic multi-session receiver/scheduler and restart regression. Patch-only claim does not close Spec finding.

## Independent scheduler/restart evidence at 0c94e50

/tmp/ticket08-0c94e50-scheduler-review.py reconstructs real components against local HTTP. Positive one-event/restart/ten-minute scheduled case passes exact-one POST and no resend. Actual late VerificationStore.submit passes zero POST with durable manual reason. APPROVED transition sends nothing but incorrectly leaves prior missing observation indefinitely observed; original task notified to preserve identity and fresh status evidence in durable manual routing. These scoped passes do not close the remaining cross-resource, unknown-delivery, disable, CLI or final review gates.

## Independent lifecycle audit at 3139e19 — effects remain unsafe

/tmp/ticket08-3139e19-lifecycle-review.py uses pinned controller and real temporary VerificationStore. Claim removal occurs with production_enabled=False/no approval, fresh wrong-study/manual identity state, local read error, and explicit consent withdrawal evidence. Conversely routine-approved future sessions outside fixed lists are skipped. Scheduled reconciliation ignores discrepancies without completed events. All findings handed to active original task ticket-08-final-matrix.* PID1790798; fix real effects gates/fresh evidence/consent propagation and add regressions before acceptance. No production access occurred.

## 51384f5 remains unaccepted

Root inspected committed execute: lifecycle default-off and fresh validation defects remain despite completion-themed commit title. Full dual-axis review started pinned51384f5. Original task terminal; resumed same session in ticket-08-lifecycle-gates.* with actual-store reproduction and mandatory regression cases. Previous tests allowing lifecycle effects while disabled must use explicit local approval rather than weakening new guards. No merge/production.

## c6f8e8d lifecycle guard checkpoint

Original task added five-case actual VerificationStore regression and reports121 full tests. Default-off, fresh uncertainty/consent and routine future lifecycle addressed; independent field-contract review pending. Continued same session in ticket-08-outbound-recovery.* for actual uncertain HTTP delivery/restart and concurrent disable, with missed-event, CLI digest, Standards and final packet still required. No acceptance/merge/production.

## Independent c6f8e8d review — immediate guards pass, integration incomplete

/tmp/ticket08-c6f8e8d-lifecycle-review.py verifies immediate no-mutation/default-off guards. Manual lifecycle guard results are not durably journaled. Real reconciliation classification/proposed_action must be consumed; consent flag is injected in tests but not emitted by reconciliation, so explicit consent evidence source must be connected. Unconditional non-contact selection bypasses historical lifecycle approval. Findings queued to current ticket-08-outbound-recovery.*; final acceptance still withheld.

## 8d8252b recovery evidence rejected

Root inspected committed test_ticket_08_recovery_matrix.py: candidate is handwritten, reconciliation/history are canned, restart only reopens ledger, and disable test checks journal.begin rather than next controller effect. Report claim of reconstructed scheduler is unsupported. Original task resumed in ticket-08-authentic-unknown.* for actual one-event/ten-minute/HTTP-disconnect/reconstructed-components scheduler proof. Component pass123tests does not close full-chain requirement.

## 53da6fc authentic unknown-delivery proof

Independent pinned8d8252b /tmp/ticket08-8d8252b-unknown-http-review.py passes actual signed-event, ten-minute scheduler, recorded HTTP POST/disconnect and reconstructed full-stack recovery: one POST, manual_review, unknown outcome, attemptcount1 retained. Original task added equivalent repository test53da6fc and removed superseded mock proof;122tests reported. Continued same task ticket-08-final-guards.* for remaining lifecycle durability/real schema/consent source/historical approval, missed events, concurrency and Standards. Full acceptance remains pending.

## 8dc871c guard persistence and concurrent-disable evidence

Original task reports durablemanual, historical approval and missed-event surfacing122tests; newbehavior still needs explicit regression/final review. Independent /tmp/ticket08-53da6fc-concurrent-disable.py passes realtwoNEW/signedHTTP/firstPOSTblocked/separateprocessdisable: onePOST, no subsequent RETURNED release, restartedcontroller disabled. Audit limitation: locally prevented secondsend misclassified unknownattempt. Continued original ticket-08-final-evidence.* to retain authentic test, distinguish auditreason, finish Standards/sharedfixtures/actualrestart and guard regressions.

## f6fcf1c and remaining audit binding gaps

Local prevented-send reason distinguished from networkunknown; constructor typed;122tests. Spec8dc871c repro /tmp/ticket08-8dc871c-guards-review.py still finds earlymanual branches notjournaled, consent no real source, historical approval onlysession not exactaction/identity/digest. Continued same ticket-08-audit-binding.* to close with realregressions. Cleanup/reconstruction/disableproof/finalreview/humangate remain.

## 914a7a5 approval/consent checkpoint

Three production-code/docs files changed, no newtests;122tests reported. Independentreview checking realCLI approval record construction, consent source and earlymanualdurability. Continued same session ticket-08-fixture-cleanup.* for shared4spaceUTF8 fixtures, actualcrossresourcerestart, authenticconcurrentdisable retention and missingguardregressions. Full acceptance not established.

## 9aef32e reconstruction tests, configuration findings still open

Actualcrossresourcereconstruction and basicconsent/Approval objecttests added124tests+browserreported. Spec914a7a5 actual /tmp/ticket08-914a7a5-consent-review.py shows rootarray/malformedrecords/identitymismatch/conflictingduplicates failopen. CLIhistoricalrecords empty; earlymanual branch stillnotpersisted. No productioncode changed9aef32e; original resumed ticket-08-contract-closure.* for actualCLI/adapter regressionfixes. Cleanup/authenticdisable/finalreview/humangate pending.

## dd7af1b contract closure awaiting independent verification

Original reports earlymanual journal, CLIhistoricalrecords and consent4malformedcases pending nowfixed;124existingtests, no permanentnewregressions incommit. Independentrepro requested. Continued ticket-08-shared-fixtures.* to finish previouslydeferred shared4spaceUTF8 fixtures/authenticseparateprocessdisable and retainguardregressions before fullreview/humangate.

## 3f7ce78 concurrency retained; two configuration failures

Authentic separateprocessdisable repositorytest125fulltestsreported. Independentdd7af1b proves earlymanualpersistence; schema-valid consent record withrecord_id/samesessionwrongstudy stillignored. ActualCLI historical stores release_claim_proposal vs normalizedrelease_claim and rejects unchangedapprovedcase. Repros /tmp/ticket08-dd7af1b-{consent-review,cli-historical}.py. Original resumed ticket-08-final-normalization.* for2fixes/permanenttests and deferredfixtureStandards.

## 461c87f normalized actions and final review cycle

Original reports sharedCLI/controller actionnormalization and validconsentidentityconflict guard125tests; fullStandards+Spec pinned461c87f against377199a started. Original resumed ticket-08-cleanup-only.* to complete deferredfixtureStandards and accurateexecutablehumanpacket. Humanpacket still stale120 and unsupportedcompleteclaim atrootaudit; must correctbefore user gate.

## 388d4e3 cleanup; normal-success no-op defect

Standalonefixtures formatted andpacket rewritten125tests/browserreported; Standards re-review started. Spec461c87f authenticCLI consent/historicalmatching/rejectwrongactionidentity PASSES. UnrelatedAPPROVED proposed_action none createsfalsemanual record; original resumed ticket-08-noop-fix.* to correctwhilepreserving existingmissingstatuschange. Operationalcommands still require actualcontrolledverification; human/live gatespending.

## 2e05b21 technical checkpoint

Root independently ran fullsuite126tests exit0. Spec reviewedcode requirements pass including actualCLI no-op/historical and existingmissingstatuschange; operationalrunbook P2 remains: emptyauto_labels cannotconstructstore, approvalpath differsdata_dir, fixtureAPI/files absent, expiredscope. Standards only9explicitUTF8calls remain; duplicatefixtures NONBLOCKING. Original task ticket-08-encoding.* PID1829882 fixes exactcalls; runbookfindingsqueued. No human gate until runnablecontrolledsetup checked.

## 801458a explicit UTF-8 closure

Original ASTscan allTicket8testtextIO explicitUTF8 and126testsreported; Standardsfinalcheck requested. Continued same ticket-08-runnable-runbook.* to create/run actualisolatedoperator setup resolving brokenauto_labels/approvalpath/scope/API assumptions, capture proof, correctpacket. CoreSpecpass2e05b21; live/human gate remains afteroperationalreview.

Standards final801458a PASS: all9reported IOcalls and entirechangedPython textIO verifiedexplicitUTF8; priorannotation/indentationpassescarry. Duplicationnonblocking. Speccore2e05b21pass remains; runnableoperatorrunbook andhumanacceptance pending.

## f018997/1028718 runbook smoke rejected as insufficient

Root normalrunexit0/receiverpreview passes; Spec faultinjection schedulerexit7 stillsmokeexit0 /tmp/ticket08-f018997-smoke-scheduler-failure.json. Schedulercycle notasserted/restartstatus notactualrestart/hardcodedport/finallychildcleanup missing. Docs1028718updated butscriptunchanged; original resumed ticket-08-smoke-failure.* to proveactualcycle/restart/noeffects and detectfailedscheduler. No human gate yet.

## Final technical acceptance — 3a89d70

Standards5a63637 PASS; finalSpec3a89d70 PASS (subsequentdiffdocs-only). Root127fulltestsPASS. Independentsmoke normal0 cycles1to2 actualrestart/noPOST, faultinjectedexit7=>smoke1 verified. Final2doccommands corrected. No outstanding technicalfinding. Requiredhuman/live gates remain; ticket-08-technical-human-review.md records exactversion/evidence/recovery. Ticket8 unmerged, production untouched.

## Pagination correction: cc98597 (2026-09-10)

Pinned incremental diff: 3a89d70...cc98597. Independent Standards reviewer /root/pagination_standards: PASS, 0 documented violations; optional Speculative Generality observation: ordering parameter only accepts started_at and could instead be fixed inside transport. Not a blocker. Independent Spec reviewer /root/pagination_spec: PASS, no actionable findings. Both verified transport ordering on both pages and retained completeness guards. Root independently ran 12 reconciliation tests: pass; original Implement task reports full127pass. No new manual question from the correction; existing archive-only approval and remaining human gates remain unchanged.

Actual cc98597 read-only reconciliation is running under exec session30751, output /tmp/prolific-ticket08-sorted-live-reconciliation.json. Do not infer completion or start duplicate. Pending validation of full platform identities/local answers. No deployment, messages, lifecycle data changes or Ticket8 merge.

Live reconciliation session30751 completed exit0 atcc98597: statusok,2952uniqueplatformsessions,295localfinalresults,0temporaryclaims;299AW=293matched+6missing;1Returnedwithresult and1TimedOutwithresult. No writes. Summary live-reconciliation-summary.json. This supersedes earlier running-state note. Completion-code mapping remains partial (no validcode configured); human gates remain.
