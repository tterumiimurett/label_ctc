# 04: 平台超时后正确释放未提交占位

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** 03 — 已退回 session 归档并释放名额。

**What to build:** 复用经验证的占位释放和旧session防重入机制，让 TIMED-OUT 且无答案的任务可以重新分配。

- [ ] 无答案则释放；有最终答案则保留并转人工，不套用RETURNED归档策略。
- [ ] 重复处理及超时后的迟交不重复计数或超额。
- [ ] 隔离演示超时到重新分配，验证有答案分支不被迁移。
