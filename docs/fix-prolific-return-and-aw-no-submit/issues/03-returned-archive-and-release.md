# 03: 已退回 session 归档并释放名额

**Status:** Approved draft — pending tracker publication

**Publication label:** ready-for-agent

**Blocked by:** 02 — 研究者能只读查看平台与本地差异。

**What to build:** 对账确认 RETURNED 后，受控执行归档/释放，使下一个合格新 session 可领取正确名额。

- [ ] 有最终答案则保留内容和审计证据归档；无最终答案则仅释放占位。
- [ ] 与正常提交/分配并发和进程中断时可恢复，不丢数据、不重复释放、不超额。
- [ ] 旧 RETURNED session 不能重新占位或使归档结果再次计数。
- [ ] 已归档后状态反转转人工，不自动恢复；明确撤回同意单独标记处理。
- [ ] 隔离演示“退回→归档/释放→新分配”，默认生产执行关闭。
