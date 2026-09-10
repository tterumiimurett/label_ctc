# Fix Prolific RETURNED and awaiting review without local results

状态：已确认业务规则的规格；测试边界待用户核对。未实现、未部署，未发布 issue。


## 2026-09-10 人工核验后的优先修订

以下为用户最新批准的规则，覆盖本文旧版冲突段落及先前实现报告。具体验收以修订后的 `issues/04-timed-out-claims.md`、`issues/06-send-return-requests.md` 和 `human-review-2026-09-10.md` 为准：

- TIMED-OUT 有答案也要安全归档到独立 `prolific_timed_out` 分类并退出计数；无答案释放。保留完整字节/审计、状态隔离和人工异常处理。研究者确认本研究时限14分钟，触发仍查当前平台状态。
- 典型新缺失案例在规则及启用获批后自动发消息，不逐session审批；历史名单另批。
- 聊天为空或最后研究者发言后无参与者新回复允许自动；有待处理参与者回复则人工，不依赖Session ID或LLM。无法完整读取历史不是空历史。
- 既有缺失待联系案例后来发现答案或已联系，暂停发送进入人工队列。既有发送尝试不可逆，重复/候选重建绝不重发。
- 普通文案已批准，特殊情况先人工讨论，不自动套模板。本地可查看人工队列足够；不要求外部通知服务。
- 这次是规则修订授权，不是新实现验收或生产启用授权；仍需实施、双轴复审和必要人工核验。

## Problem Statement

研究者无法仅凭平台待审核数判断收集到的标注是否足够。当前本地正式计数没有同步平台状态：RETURNED 的已有答案继续占用名额，已退回或平台超时的未提交分配也可能继续占位。同时，部分 AWAITING REVIEW 没有对应本地最终答案。任务无法分配时，前端错误被隐藏，参与者只看到标题和身份信息。

两份历史快照中，平台待审核分别为 284 和 293，对应本地结果分别为 271 和 283。最新已提供快照的 10 条缺失包括 9 条 NOCODE 和 1 条未知码；这只是观察，不意味着完成码导致数据丢失，也不意味着其他完成码不会缺失。

RETURNED 可以发生在提交之后，不等于从未作答，也不必然表示撤回数据使用同意。NOCODE/未知码是完成码分类，不是平台状态或答案有效性判断。

## Solution

同步平台当前状态与本地记录，以研究、Session 和 Participant 的一致性对账。普通 RETURNED 自动退出正式计数并可追溯归档，未提交占位释放；TIMED-OUT 无答案释放，有答案转人工。对所有 AWAITING REVIEW 检查最终答案，缺失等待 10 分钟复查，排除疑点和重复联系后发送一次退回请求。

研究者能够先查看只读对账与拟执行清单，再确认上线。历史遗留记录按当前 API 状态核查，不假定接入前存在 webhook 历史。参与者能看到明确加载错误，确有完整答案者不会仅因异常完成码被请求退回。

## User Stories

1. As a researcher, I want platform and local counts shown separately, so that I do not mistake platform submissions for saved annotations.
2. As a researcher, I want every awaiting-review submission reconciled, so that missing answers are detected regardless of completion code.
3. As a researcher, I want study, session and participant identities checked together, so that another person's result cannot satisfy a submission.
4. As a researcher, I want NOCODE and unknown codes classified separately from platform status, so that missing-code cases are not automatically treated as invalid work.
5. As a participant, I want my complete local answer retained when my completion redirect fails, so that a missing code does not trigger an incorrect return request.
6. As a researcher, I want ordinary returned answers archived outside formal counting, so that replacements can receive available tasks.
7. As a researcher, I want returned sessions without answers to release pending claims, so that abandoned work does not block recruitment.
8. As a researcher, I want archived answers and migration evidence preserved, so that exclusions can be audited.
9. As a researcher, I want returned sessions prevented from reclaiming or recounting work, so that old links cannot undo reconciliation.
10. As a researcher, I want timed-out sessions without answers to release claims, so that platform timeouts do not leave stale reservations.
11. As a researcher, I want timed-out sessions with answers reviewed manually, so that potentially completed work is not automatically discarded.
12. As a researcher, I want explicit withdrawal of data-use consent distinguished from ordinary returns, so that archival is not mistaken for withdrawal handling.
13. As a researcher, I want missing answers rechecked after ten minutes, so that transient delays do not trigger premature messages.
14. As a researcher, I want drafts, identity mismatches, other-session results and storage failures flagged, so that ambiguous cases receive human review.
15. As a participant, I want a return request to identify my session and invite a reply if I submitted successfully, so that I can correct a mistaken missing-result finding.
16. As a participant, I want at most one automatic return request per session, so that repeated events do not cause repeated messages.
17. As a researcher, I want existing return requests and accessible conversations checked, so that historical contact is not duplicated.
18. As a researcher, I want participant conversations linked carefully to individual sessions, so that repeat participation is not conflated.
19. As a researcher, I want unavailable or ambiguous message history referred to a human, so that missing access is not interpreted as permission to contact again.
20. As a researcher, I want a return request distinguished from an actual return, so that capacity is not released just because a message was sent.
21. As an operator, I want signed status events verified and current API state checked, so that forged or stale events cannot alter records.
22. As an operator, I want duplicate and out-of-order events handled safely, so that counts and communications remain correct.
23. As an operator, I want failed queries retried without classifying them as missing data, so that outages do not cause erroneous actions.
24. As an operator, I want uncertain message delivery reconciled before retrying, so that a timeout does not produce duplicate contact.
25. As an operator, I want interrupted reconciliation recoverable after restart, so that archive and allocation records remain consistent.
26. As a researcher, I want a current-state backfill and periodic reconciliation, so that pre-integration discrepancies and missed events are detected.
27. As a researcher, I want historical message candidates approved as a list, so that enabling integration does not unexpectedly contact past participants.
28. As a researcher, I want changes to previously archived platform submissions raised for review, so that automatic restoration does not overfill a sample.
29. As a participant, I want assignment errors visible on the page, so that I understand why no task appeared.
30. As a researcher, I want isolated tests and a real-data read-only preview before activation, so that production actions are reviewable.
31. As an operator, I want credentials and participant records excluded from versioned documentation, so that implementation does not expose operational data.

## Implementation Decisions

- Extend the existing CTC verification workflow; retain standard-library-first service conventions and existing task identity and redundancy semantics.
- Introduce a cohesive reconciliation boundary shared by webhook-triggered processing and current-state backfill. Keep platform access and clock controllable for tests; storage and real allocation/submission behavior remain exercised end to end.
- Subscribe to submission.status.change through a publicly reachable HTTPS endpoint. Verify authenticity, durably record accepted events, and make processing restart-safe. Check existing workspace subscriptions/secrets before configuration; do not overwrite unrelated integrations.
- Webhook data identifies submission, participant and status. Query submission details to obtain current status, study and entered completion code; do not expect completion codes or historical replay from the event body.
- Query failure, unreadable files, corrupt data and identity mismatch are not absence. Pending work stays pending or enters manual review; no archive or message is triggered on uncertain evidence.
- Reconcile formal results, excluded results, drafts, assignments and possible other-session results. A different session's answer does not count as the missing session's answer and triggers manual review.
- For confirmed RETURNED, use the already agreed dated excluded-results archive with a dedicated prolific-returned category. Preserve contents, hashes, previous identity/allocation state, original location, reason and processing time. Keep researcher-test archives distinct.
- Archive, count exclusion and allocation-state updates must coordinate with normal assignment and submission writes and recover from interruption. Returned sessions must not reclaim or repopulate formal results through old links. Do not reset unrelated participants.
- For TIMED-OUT without a final answer, release the pending claim. If an answer exists, retain it and refer the case to manual review. Do not silently apply RETURNED archival policy.
- Explicit withdrawal of data-use consent follows separate human handling; this feature does not implement or substitute archival for a deletion process.
- Check all AWAITING REVIEW, not only unusual completion codes. Record the first confirmed missing-result observation and wait at least ten minutes before reassessment. Repeated events must not create duplicate schedules or bypass the waiting period.
- Before contacting, re-read current platform status and local result state. Any draft, other-session result, identity ambiguity or suspected save failure is referred to manual review.
- Check the platform return-request timestamp, accessible conversation history and durable local contact ledger. Respect message API time-window and workspace permission limits. Do not assume participant-level chats belong to one session. Inaccessible or ambiguous history blocks automatic contact pending human review.
- Send no more than one automatic return request per session. Persist the attempt state before sending; a network timeout with unknown delivery status triggers reconciliation against platform messages/request state, not blind resend.
- The API offers both a structured return-request operation and ordinary messaging. Use one outbound operation per request. The structured endpoint is experimental and generates its own wrapper text; validate whether it can preserve the approved wording. If not, use ordinary messaging with the approved text and local request ledger. Do not send both messages.
- Sending a request is not confirmation of RETURNED and does not itself release an awaiting-review claim or alter payment/review status.
- After an archived record changes to APPROVED or another incompatible state, surface it for human review; do not automatically restore it into a now-filled sample.
- Periodic API reconciliation compensates for missed events. Use current API state for historical backfill, then present a historical action/contact list for user approval. Do not use stale CSV status as a production action trigger.
- Make loading failures visible in the participant interface. Verify both error visibility and successful task/instruction/audio loading; do not infer success from HTTP 200 alone.
- Separate read-only evaluation from production action execution. Start with isolated validation, then a live API read-only report; activate archive/release/messaging only after the user approves the report and validation. Historical messaging requires its own confirmed list.
- Durable reconciliation records must capture source identity, observations, missing-result timing, processing stage, action evidence and message-attempt outcome. Exact storage format, scheduler cadence and hosting configuration remain implementation choices subject to the above behavior; they were not settled in grilling.

Approved message text:

> Hello, our records show that your Prolific submission is awaiting review, but we could not find a final annotation result for this session: {SESSION_ID}. If you were unable to complete the annotation, please return this submission on Prolific. If you believe you submitted your answers successfully, please reply so we can investigate. We’re sorry for the inconvenience.

## Testing Decisions

Test observable outcomes: available allocation capacity, preserved/excluded answers, participant-facing page state, manual-review decisions and outbound-message effects. Avoid assertions that merely mirror private helper implementation.

Proposed main seam: drive the reconciliation boundary through a signed incoming event or a current-state backfill using a controlled platform API and clock, with temporary real storage and the real CTC assignment/submission operations. Add thin HTTP contract tests for authentication/event acceptance and browser tests for presentation. This minimizes new seams while testing the behavior spanning platform state and local capacity.

Prior art: existing unittest tests use temporary directories and VerificationStore to cover candidate exclusion across sessions, three-unique-participant capacity, and expiry followed by late submissions. Extend those behaviors rather than introduce a parallel fake allocation model. The conversation-annotation suite provides additional patterns for identity mismatch and repeated submission handling, but it is a different delivery workflow.

Required cases:

- RETURNED with an answer archives it without content change, releases the correct capacity once and blocks old-session recounting.
- RETURNED without an answer releases its pending claim once without manufacturing an answer or mutating unrelated assignments.
- TIMED-OUT with/without results follows the two distinct agreed policies.
- Normal code, NOCODE and unknown code each work with both present and absent results. Unusual code plus a complete answer causes no return request.
- Missing results are rechecked only after the ten-minute window; arrival before contact cancels the request.
- Drafts, archived answers, other-session answers, inconsistent identities and storage/API errors prevent automatic missing-result messaging.
- Past requests, ambiguous chats, unavailable permissions and repeated participation do not cause incorrect cross-session deduplication or duplicate messages.
- Signature failure, wrong study, duplicate/old events, status reversal and concurrent late submission cannot corrupt capacity or cause premature contact.
- Restart during archive/state update or after a possibly delivered message recovers without double actions. A request endpoint response alone is not treated as a return event.
- Read-only backfill produces the same proposed decisions as event processing without moving production data, writing assignments or sending messages.
- A real browser shows visible no-task/error text; a synthetic isolated successful session displays instructions and task and plays audio. No production participant page is used to create test allocations.
- Validate API contracts using official test facilities where available before exercising real-account read-only data. Do not claim tests or live integration have run merely because they are specified here.

Test seam status: proposed from existing repository tests; user confirmation outstanding under to-spec. This is the only requested technical checkpoint, not a renewed business interview.

## Out of Scope

- Automatic approval, rejection, payment, bonus or forced platform return.
- Assuming NOCODE/unknown code invalidates a result, or inferring return motives from current status.
- Automatically judging annotation quality or blaming participants for technical failures.
- Automatically deleting data for consent withdrawal, automatically restoring reversed archive states, or silently reusing one session's answer for another.
- Changing study eligibility, recruitment quotas, reopening studies or bypassing browser security warnings.
- Automatically offering retries or contacting historical participants without the approved list.
- Replaying nonexistent historical webhook data or guaranteeing chat-history completeness before account-level verification.
- Refactoring unrelated MTurk, Label Studio or conversation annotation workflows.

## Further Notes

Business decisions from grilling Rounds 1–3 and the message-history discussion are accepted. The production activation checkpoint remains in force. Creating this spec does not deploy a service or send participant messages.

Previously authorized manual archival moved 22 returned answers and 7 researcher tests outside formal submission counting and preserved allocation history. Treat existing archives/manifests as migration inputs, not as a reason to repeat actions. Later counts are time-dependent; backfill must read current platform and local state.

Required operational prerequisites: appropriate Prolific credentials and message visibility, identified workspace, existing subscription/secret inventory, HTTPS receiver and scheduler. Keep secrets, real completion codes and participant datasets out of version control.

Official evidence and the timeline remain in the companion evidence document. Key contracts:

- https://docs.prolific.com/api-reference/webhooks/receiving
- https://docs.prolific.com/api-reference/submissions/get-submission
- https://docs.prolific.com/api-reference/messages/get-messages
- https://docs.prolific.com/api-reference/messages/send-message
- https://docs.prolific.com/api-reference/submissions/request-submission-return

Publication target: not configured. A GitHub remote exists, but no explicit project issue tracker/triage configuration was found. Requested triage label: ready-for-agent. Run /setup-matt-pocock-skills to provide tracker configuration; publishing has not occurred.


## Confirmed answer-arrival amendment (2026-09-10)

During the missing-result wait, an identity-matched, complete, valid final answer for the same session resolves normally: no participant message and no new manual-review item. This applies to initial observation, ten-minute fresh reassessment, and reconstructed durable state. Platform status changes, prior contact, uncertain delivery, identity mismatch, drafts, errors, and other-session results remain manual. Existing outbound attempts, `delivery_unknown`, and established manual records are never cleared by a later answer. See `answer-arrival-amendment.md`.
