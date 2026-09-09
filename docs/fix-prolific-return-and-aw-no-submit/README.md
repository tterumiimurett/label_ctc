# Fix Prolific RETURNED and awaiting review without local results

状态：8 张票及依赖已批准，正在独立任务中实施和审查；issue 待 tracker 配置发布。自动同步及自动消息尚未上线。

本目录集中保存本任务的 grilling、术语、证据、spec 和 tickets；不保存真实参与者明细、完成码、API token 或生产提交。任务级术语放在此目录，以遵循用户要求，避免扩展仓库其他工作流。

- [术语](CONTEXT.md)
- [已验证事实与证据](evidence.md)
- [Grilling 讨论与待决事项](grilling.md)
- [规格](spec.md)
- [实施 tickets](tickets.md)

用户已确定方向：同步平台 RETURNED 到本地归档；对平台待审核但无本地结果的记录进行核查，并在确认条件满足后自动请求退回。业务边界已在 grilling Rounds 1–3 确认。

已有操作：2026-09-08 经授权将 22 份 RETURNED、7 份研究者测试结果归档，保留分配历史及迁移清单。此操作不是持续同步机制。

尚无满足必要性条件的架构决策记录（ADR）；不把未确定提案写成已接受 ADR。

## 实施与合并门槛（2026-09-09 确认）

每张票都必须经过 Implement skill 实施 → Code Review skill 的 Standards / Spec 双轴审查 → 修复审查问题 → 复审通过 → 合并到 codebase。不能以实现者自检或测试通过替代独立审查。

轮次顺序：1、2 全部合并后 → 并行 3、5、7 全部合并后 → 并行 4、6 全部合并后 → 8。每轮中的每张票均执行完整循环；存在阻塞审查问题时不得推进依赖轮次。

实施使用独立 Codex 任务；Ticket 5 需要可供用户直接介入的交互任务。需要人工判断时交由用户处理。代码合并授权不代替生产动作清单与启用确认。

当前核验：Ticket 1 的提交 `187576c` 已通过 Standards 和 Spec 复审（各 0 项剩余问题），隔离 Chromium 验证任务、说明和合成音频实际播放；该验证不代表生产音频已验收。Ticket 2 的提交 `b3b53d3` 已通过双轴复审（各 0 项剩余问题）。第一轮已合并至 `37e6db5`，合并后 37 项 unittest 通过。


第二轮已启动，固定基准 `37e6db5`：

| Ticket | 独立 session | Workspace | 类型 |
| --- | --- | --- | --- |
| 03 | `01a0850f-df47-7a72-9cfc-7b1c86d863ab` | `/tmp/prolific-round-b-20260909/ticket-03` | exec |
| 05 | `01a08510-334a-7271-9798-69f96b8b4f6c` | `/tmp/prolific-round-b-20260909/ticket-05` | cli，交互 |
| 07 | `01a0850f-ea14-7bf3-970a-4eac1b194ae2` | `/tmp/prolific-round-b-20260909/ticket-07` | exec |

使用持续目标监测各票进展。Ticket 5 的 cli 来源和 workspace 已通过本机任务索引核实；用户远端 UI 的实际可见性仍待用户确认。必要时可运行 `codex resume 01a08510-334a-7271-9798-69f96b8b4f6c` 直接进入。
