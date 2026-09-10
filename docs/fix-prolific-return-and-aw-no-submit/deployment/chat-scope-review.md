# 真实聊天适配独立审查

基线 `0e70eb4855966df75a0a6d077bcd40ddddfc4647`，审查提交 `45180bcd9b62bbc0c7ce2698f1542ca348e233f6`。原 Ticket 8 独立任务，工作区 `/tmp/prolific-round-d-20260910/ticket-08`。

## Standards

独立审查任务 `/root/chat_scope_standards`：无硬性标准问题。可选维护建议：消息时间戳已解析成配对后又被重复解析，可保留配对减少重复。

## Spec

独立审查任务 `/root/chat_scope_spec`：P1，尚不可合并。`_personal_scope_ready` 仅判断当前页一位成员，忽略成员响应分页和总数；`results=[researcher]`、`meta.count=2`、非空 next 可错误通过。违反必须证明完整且唯一成员的要求。需拒绝不完整/不一致响应或安全取得全部成员，再验证唯一性。

原任务已恢复修复该问题，要求回归测试、提交后独立复审。不得把此前 141 个测试通过或真实单成员查询通过当作分页正确性证明。

## 已获得的真实证据

真实成员接口 `/workspaces/{id}/members/` HTTP 200，当前一位成员与 `users/me` 一致；实际 _links 为 self+related，无 next，无 meta。修复应支持这个完整响应形状。只读修复分支验证六个 session 得到五个 prior_contact、一个 clear，18 条唯一真实消息时间字段解析成功，见 live-chat-adapter-validation.json。未部署或执行任何历史动作。
