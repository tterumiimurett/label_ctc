# 02: 研究者能只读查看平台与本地差异

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** None (can start immediately).

**What to build:** 从平台当前 submission 状态到本地答案核对，输出分类与拟执行动作的只读报告，建立后续动作共用的对账入口。

- [ ] 核对研究、session、参与者；分别展示平台计数、本地答案、临时占位。
- [ ] 全量 AW 按完成码和结果有无分类，检查正式/归档/草稿/其他session结果。
- [ ] 展示 RETURNED 与 TIMED-OUT 的本地关联情况，不修改业务数据或发送消息。
- [ ] API/文件读取失败是未知或故障，不被算成无答案；遍历完整结果并遵循API分页/限流约束。
- [ ] 复用现有分配与提交测试模型，使用临时存储和可控平台响应；必要的轻量接口提取在本票内完成，不做独立宽泛重构。
