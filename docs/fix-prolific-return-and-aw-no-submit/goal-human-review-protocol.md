# Goal 替换文案

2026-09-10。下方正文用于替换应用内 goal；保存本文件不代表应用内 goal 已更新。

## 正文

完成 Prolific return / awaiting-review-without-submission 修复项目。先读取 docs/fix-prolific-return-and-aw-no-submit/ 下的 spec.md、issues/ 和 human-review-protocol.md；实现和审查均以用户确认后的最新要求及各票复核决定为准。

按 1、2 → 3、5、7 → 4、6 → 8 逐轮推进。每票由独立任务执行 Implement → 必要测试 → Code Review 双轴独立审查 → 修复及复审 → 完成所需人工核验 → 合并，上一轮完成后再推进下一轮。监测任务完成与失败，保留简短进度、验证证据和恢复位置。

人工修改意见先经 Grill Me 确认，并询问是否再次人工核验，将确认结果同步给实现和审查 Agent。需要人工判断时暂停相关合并及依赖步骤，等待明确核验；通过后按已确认规则继续。其他任务中的人工核验须读取聊天和对应提交核实。

结束条件：所有票完成实现、验证、审查及所需人工核验并合入 codebase，隔离端到端验证和可执行上线验收准备齐备。合并或人工核验通过不等于生产授权；生产迁移、发送消息和启用服务仍按既定审批边界处理。

## 配套文档

- [通用人工核验流程](human-review-protocol.md)
- [Ticket 4：超时归档及本轮复核决定](issues/04-timed-out-claims.md)
- [Ticket 6：自动联系及本轮复核决定](issues/06-send-return-requests.md)
