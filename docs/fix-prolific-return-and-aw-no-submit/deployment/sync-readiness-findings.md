# 自动同步接入核查（2026-09-10，UTC）

真实样例页面已获用户确认；本次为自动同步部署核查，未执行真实归档、发信或恢复研究。

## 已验证

- 实际研究 API 返回 PAUSED；研究、当前用户、工作区、订阅列表、签名密钥列表均返回 200。
- 本工作区订阅和签名密钥列表 results 均为空，meta.count 均为 0。
- 当前 Tailscale HTTPS 服务为 tailnet only，根路径代理既有其他服务。不能直接用作公网 webhook，也不能把该根路径服务顺带公开。
- systemd 用户服务管理器返回 running。
- 六位历史缺失结果候选的 workspace_id 聊天查询均为空；相同 user_id、created_after 的个人查询中，五位非空，一位为空。非空记录数为 4、11、11、11、3；后三个 11 属于同一参与者的不同 session，不应视为三个独立对话。
- 五个非空查询均存在研究者消息同时包含 return 和 submission。这只是既定关键词检测命中，不是人工确认每条消息指向该 session。一个查询最后消息来自参与者，其余来自研究者。当前不能自动重发。
- 真实消息使用 datetime_created 时间字段；当前 inspect_messages 要求 created_at，未发现字段归一化。非空真实历史会被判为 ambiguous。

私人原始响应在 /tmp/prolific-sync-inventory（目录 0700，文件 0600），不纳入 Git。

## 尚待验证和处理

1. 确定覆盖既有个人聊天的读取范围；不得以空工作区查询证明未联系，也不得把 workspace_visibility_verified 直接设为 true。
2. 适配真实时间字段并沿既定 Implement → Code Review → 修复流程验证。
3. 配置隔离公网 HTTPS 入口及预览订阅、常驻调度；尚未声称收到真实事件。
4. 刷新具体历史操作清单，用户确认后才能归档、发信、启用自动动作和恢复研究。

## 官方依据

- [消息 API](https://docs.prolific.com/api-reference/messages/get-messages)：workspace messaging 未启用时工作区消息查询可以返回空；官方示例时间字段另为 sent_at，故需兼容实际返回并验证格式。
- [工作区消息](https://researcher-help.prolific.com/en/articles/445238-workspace-messaging)：开通需联系支持且不可逆，本次未开通。
- [订阅](https://docs.prolific.com/api-reference/webhooks/subscribing)：需要公网 HTTPS；新建密钥前需查清既有密钥，避免替换影响其他订阅。

## 本轮复查及执行进度

- 工作区仅一位成员，ID 与当前令牌所属用户相同；个人聊天仍需独立验证，不能冒充已验证的工作区查询。
- 本轮刷新 2952 条唯一平台记录，无新增、丢失或身份/状态变化：299 awaiting review、2593 returned、60 timed out。本地 957 条读取记录无解析错误。
- 六个缺失结果 session 均再次核实无本地 final；五个 submission 详情明确带 return_requested 时间，只有一个为 null 且个人聊天为空。两份拟归档结果实时状态仍分别为 RETURNED、TIMED-OUT，身份匹配且各有一份本地结果。
- 具体名单在私有文件 `/home/label/label_ctc/logs/prolific-sync/historical-actions-for-approval.md`，不纳入 Git，所有动作仍未执行。
- 原 Ticket 8 独立任务 `01a0890a-dc99-7113-afe8-d7020a3e0e2c` 已恢复处理真实聊天适配，要求 Implement、测试、双轴 Code Review、修复复审后提交分支，尚未合并。
- 创建新 webhook 签名密钥和保存凭据被自动审批拒绝，理由是需要对外部认证变更和持久化凭据作具体授权。该操作未执行，已向用户提出授权请求；其他只读工作继续。
