# 真实聊天适配独立审查

基线 `0e70eb4855966df75a0a6d077bcd40ddddfc4647`，审查提交 `45180bcd9b62bbc0c7ce2698f1542ca348e233f6`。原 Ticket 8 独立任务，工作区 `/tmp/prolific-round-d-20260910/ticket-08`。

## Standards

独立审查任务 `/root/chat_scope_standards`：无硬性标准问题。可选维护建议：消息时间戳已解析成配对后又被重复解析，可保留配对减少重复。

## Spec

独立审查任务 `/root/chat_scope_spec`：P1，尚不可合并。`_personal_scope_ready` 仅判断当前页一位成员，忽略成员响应分页和总数；`results=[researcher]`、`meta.count=2`、非空 next 可错误通过。违反必须证明完整且唯一成员的要求。需拒绝不完整/不一致响应或安全取得全部成员，再验证唯一性。

原任务已恢复修复该问题，要求回归测试、提交后独立复审。不得把此前 141 个测试通过或真实单成员查询通过当作分页正确性证明。

## 已获得的真实证据

真实成员接口 `/workspaces/{id}/members/` HTTP 200，当前一位成员与 `users/me` 一致；实际 _links 为 self+related，无 next，无 meta。修复应支持这个完整响应形状。只读修复分支验证六个 session 得到五个 prior_contact、一个 clear，18 条唯一真实消息时间字段解析成功，见 live-chat-adapter-validation.json。未部署或执行任何历史动作。

## b53a243 复审

Standards 无硬性问题。Root 独立运行 144 个完整测试通过（13.845 秒），真实成员 API 经修复后分页方法读取成功。

Spec 仍有 P1：公共 continuation 解析优先使用顶层 next，当其为 null 而 _links.next 非空时，可能忽略后者。需拒绝两种分页表示的矛盾或无效形状。原独立任务已再次恢复修复，仍不允许合并。

## 最终通过并合并

`ee61adf347c65803e32b7b7c91a72c872ab55b3e` 经同两路独立任务复审：Standards 无硬性问题，Spec 无剩余阻塞（独立运行 11 个 personal-scope 测试通过）。修复已合并为 `0749e8a`。主代码库完整 146 测试通过，13.803 秒，日志 `/tmp/prolific-merged-chat-full-tests.log`。

此结论仅为代码修复及合并通过；预览接收器/订阅尚未配置，未执行生产归档、发信或恢复研究。
