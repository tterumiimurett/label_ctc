# 已验证事实与证据

记录日期：2026-09-09。CSV 对账是上传时的平台快照，不代表当前实时平台状态。

## 两次快照

| 快照 | 平台 AWAITING REVIEW | 对应本地结果 | 无对应本地结果 |
|---|---:|---:|---:|
| 用户导出 (2).csv | 284 | 271 | 13 |
| 用户导出 (3).csv | 293 | 283 | 10 |

两次间新增 12 条待审核且有本地结果；原缺失的 13 条中 3 条变成 RETURNED。因此 284 + 12 - 3 = 293。

2026-09-09 再查 (3).csv：待审核正常完成码 283 条均匹配本地身份及结果；NOCODE 9 条和未知码 1 条均无对应正式提交、归档、草稿或分配记录。10 个 session 对应 8 人，其中一人在其他 session 下有结果。此观察不是因果规律，不能推广为异常码必然无结果。

生产明细保持在受控运行数据与用户附件中，不复制进本目录。一次性 /tmp 审计表不是永久证据来源。

## 当前代码

- `prolific/ctc_verification_app/app.py`：`submit()` 先校验并保存答案，再返回完成跳转地址；不查询 Prolific 状态。
- 同文件 `_submitted_participants_by_candidate()` 扫描正式提交文件，按候选的不同参与者计数，不排除平台 RETURNED。
- `_claim_counts()` 叠加尚未本地超时的未提交分配；平台退回或超时不会立即释放本地占位。
- `assign()` 是有写入副作用的 GET 路径，不可用真实参与者刷新来声称只读测试。
- `static/app.js` 的 `showFatal()` 添加 errors 类；`static/style.css` 的该类为 display:none。已在真实失败页面读到被隐藏的任务不足错误；尚未修复。

## 官方证据（2026-09-09 查询）

- [参与者可在完成后退回](https://participant-help.prolific.com/en/articles/445041-how-to-return-a-submission-on-prolific)
- [NOCODE/错误码可能有完整答案，也可能未完成](https://researcher-help.prolific.com/en/articles/445211-participants-are-completing-my-study-with-nocode-or-the-wrong-completion-code)
- [Webhook 事件体](https://docs.prolific.com/api-reference/webhooks/receiving)：submission.status.change 包含 resource_id、participant_id、status，不直接携带完成码。
- [查询 submission](https://docs.prolific.com/api-reference/submissions/get-submission)：读取 entered_code、study_id、participant、status、return_requested；submission ID 对应 SESSION_ID。
- [请求退回](https://docs.prolific.com/api-reference/submissions/request-submission-return)：实验性 API，发送请求消息，不可把示例响应当成强制退回保证。
- [接入要求](https://docs.prolific.com/documentation/core-concepts/monitoring-study-progress)：公网 HTTPS 接收地址及鉴权/签名配置。

## 未证实

未证明异常完成码导致本地保存失败，未证明 Prolific 丢失本地答案。平台 CSV 不提供足够状态历史来确定每人为何及何时退回。RETURNED 不必然是撤回数据使用同意。网页“ineligible”也不能由本地满额直接解释。

## 消息 API（2026-09-09 官方文档核查）

- [读取消息](https://docs.prolific.com/api-reference/messages/get-messages)：GET /api/v1/messages/；user_id 或 created_after 必须提供其一。study_id 过滤仅支持与 created_after 合用，不能与 user_id 合用；时间查询最近 30 天。workspace_id 需要相应权限及启用工作区消息。
- [发送消息](https://docs.prolific.com/api-reference/messages/send-message)：POST /api/v1/messages/，recipient_id、body、study_id。
- [未读消息](https://docs.prolific.com/api-reference/messages/get-unread-messages)：只返回收到的未读消息，不包含已发送消息，不可用于查重全部历史。

以上是文档能力确认；尚未使用本研究凭证读取聊天或发送消息。
