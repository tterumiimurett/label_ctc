# Code review — Tickets 1 and 2

日期：2026-09-09。只读审查；未合并、部署或修复。通过 codex exec resume 与两个原独立 Session 续聊，双方已回复。双方确认此前仅阅读技能，未执行独立双轴审查；本次由根会话补齐。

基线：4a19c7e。Ticket 1 审查 git diff 4a19c7e...6747fb4，提交 cfd2a49、6747fb4。Ticket 2 审查 git diff 4a19c7e...4557b08，提交 bc0a708、4557b08。两个 diff 非空。规范来源：AGENTS.md；规格来源：本任务 spec 与各自票据。

## Standards

Ticket 1：0 项明确规范问题。

Ticket 2：0 项硬性规范违规；1 项判断性建议 possible Duplicated Code。reconciliation.py 的 26–46、55–64、123–127 行重复维护存储目录、读JSON与worker提取，还在同一轮多次读文件。建议形成一次读取的证据集合供各索引复用，减少路径不一致和读取时点差异。此项是可维护性判断，不是AGENTS硬性违规。

## Spec

### Ticket 1

- P1：修改错应用。改动落在 conversation_annotation_app/static/app.js:290，而实际CTC故障应用未改；CTC showFatal 添加errors及CSS display:none仍存在。违反票据实际故障路径及spec CTC workflow要求。原实现Session已确认。
- P2：未完成真实浏览器验收。报告承认没有浏览器，却宣称spec pass；HTTP检查不能证明任务、说明、音频及可见错误。必须在正确应用以隔离数据验证。

### Ticket 2

- P1：reconciliation.py:16–21,38–42 吞读取/解析错误。损坏JSON被分类 awaiting_without_final_result；违反读取失败不得判无答案。根会话与Spec审查各自隔离复现。
- P1：28,33,57 行扫描 excluded-results 浅层目录，漏掉已约定的 excluded_submissions 日期分类归档。实际布局模拟返回空证据。
- P1：145–152 行先匹配final，RETURNED/TIMED-OUT已有答案输出 matched/none，漏掉平台状态差异与拟执行动作。
- P1（根会话补充）：130–131 行只读取 participant_id，官方详情字段 participant 未适配且 None 时跳过校验。合成官方形状响应＋本地错误participant，得到 matched/none。需在API边界明确规范化且缺身份不能默许匹配。
- P2：115–116 行占位计算忽略submitted和超时；过期分配及已归档的提交历史可能仍计占位。隔离2020年分配复现。
- P2：89–95 行把正常码限定为OK/COMPLETE/COMPLETED，无法按研究真实完成码分类。
- P2：135–142 行跨所有参与者扫描 other session；无关参与者结果也使当前session出现 other_session_result。
- P2：缺少可运行的实际平台读取入口，仅定义Protocol；尚未交付从API到报告的完整切片，分页/限流/认证合同未验证。

## Verification and replies

根会话临时目录实证：损坏JSON→awaiting_without_final_result；错participant（平台使用participant字段）→matched；RETURNED有答案→matched/none。无生产数据写入。

Ticket 1 回复：实现cfd2a49、报告6747fb4；报告测试27项通过，但承认改错应用且无真实浏览器验收。
Ticket 2 回复：实现bc0a708、报告4557b08；报告测试30项通过，但无真实API验证，承认未完成双轴审查，已收到根会话发现。

## Disposition

两个Session已结束实现轮次，但两张票都不能验收。未指派修复或更改其代码。Tracker配置缺失不阻塞基于已批准本地票据的本次审查。

统计：Standards 1项判断性建议（最严重为重复证据读取），0项硬性违规；Spec 10项发现（Ticket1 2，Ticket2 8），最高严重级别P1，分别为改错应用及错误对账。


## 最终复审与合并（2026-09-09）

### Standards

Ticket 1 `187576c`、Ticket 2 `b3b53d3`：均 0 项剩余规范问题。独立 Standards reviewer 已核对最终增量。

### Spec

Ticket 1：0 项剩余阻塞；独立 reviewer 运行隔离 Chromium，任务/说明可见，合成 WAV 可播放且播放时间推进；四种加载失败均可见。

Ticket 2：0 项剩余阻塞；独立 reviewer 验证不存在/非目录根路径、畸形平台列表及详情均报告故障；9 项聚焦测试通过。

两票已合并至 `37e6db5`，主工作区 37 项 unittest 通过。未由此启用平台同步、消息或数据迁移；生产浏览器音频及真实平台只读验收留给后续阶段。
