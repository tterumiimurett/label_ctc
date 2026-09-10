# Ticket 8 人工核验与恢复位置

状态：等待用户核验，尚未合并。

待核验版本：`cc98597`，分支 `codex/prolific-ticket-08-20260910`。独立任务 `01a0890a-dc99-7113-afe8-d7020a3e0e2c`，工作区 `/tmp/prolific-round-d-20260910/ticket-08`。

## 已验证证据

- 核心实现与操作验证版本 `5a63637`：Standards 和技术 Spec 独立审查通过。后续 `3a89d70` 仅修正两处文档示例。
- 协调任务独立运行完整测试：127 项通过。
- 真实隔离浏览器：任务、说明可见，音频可播放且播放时间前进；无任务、网络错误、无效 JSON 和空响应提示可见。证据位于独立工作区 `artifacts/ticket08/browser-final.json`。这是合成音频/隔离环境证明，不是生产页面验证。
- 真实本地 HTTP：RETURNED/TIMED-OUT 归档和释放、十分钟复查、跨 session 隔离、迟交答案、重启、发送响应丢失不重发、并发停用均有专项证据。
- 命令行验证：实际调度周期在重启前后从 1 增至 2；停用后零消息 POST；注入调度器退出码 7 时验证脚本明确失败。证据位于独立工作区 `artifacts/ticket08/cli-smoke-final.json`。

## 需要用户确认

确认是否接受以上技术结果；若需要修改，先 Grill Me 确认修改内容和是否再次人工核验，再实施、审查。技术验收通过不等于生产授权。

## 仍缺少的线上证据

用户已提供 `source ~/.prolific_profile`，凭据可用。默认分页30页2952行却只有1424个唯一ID，完整性校验正确阻止报告。只读对照增加官方支持的 `ordering=started_at` 后，30页2952个ID无重复，和研究专用接口集合完全一致；平台当次状态为299 AWAITING REVIEW、2593 RETURNED、60 TIMED-OUT。这不是本地有效答案数量，也不能用于替代旧CSV时点。

证据见 `live-pagination-investigation.md`、`sorted-pagination-evidence.json`。客户端排序修复已提交cc98597并通过独立双轴审查。修复后的真实CLI完成全部2952条对账，status=ok、唯一session2952，未出现身份冲突/本地读取错误分类。299条AW中293有匹配结果、6缺失；本地最终结果295条，其中1条Returned、1条Timed Out。零临时占用。6条缺失中5条NOCODE，另1条未提供有效完成码集合故代码类别unavailable，不能称Unknown Code。汇总证据 live-reconciliation-summary.json；完整私有报告 /tmp/prolific-ticket08-sorted-live-reconciliation.json，不提交参与者明细。

查询是顺序读取，非平台原子快照。后续动作仍须执行前复查；本次没有归档、释放、发信或变更状态。有效完成码分类、workspace/webhook 配置清单和具体历史动作批准仍待核实。人工门槛不变，生产迁移、消息发送和启用服务仍需明确批准。

## 恢复步骤

收到用户决定后，读取具体意见与对应版本，按 human-review-protocol.md 处理。未通过需要的人工核验前不合并 Ticket 8；未取得线上只读验收证据前不声称项目已完全完成。已完成的 Tickets 1–7 不重复实施。

## 逐项人工核验记录

- 归档：用户明确回复“符合预期，可以通过。”已通过 RETURNED/TIMED-OUT 有答案完整归档、无答案仅释放的四项隔离案例。证据：archive-human-verification-evidence.json。此决定仅为归档技术核验，不授权线上归档，不代表其他项目通过。
- 缺失结果复查：已向用户展示首次发现、9分59秒等待、十分钟后复查、期间收到答案或变为APPROVED的结果；证据 missing-recheck-human-evidence.json。等待用户明确通过或修改意见，自动续跑不算批准。
- 防重复发送、异常转人工、停用机制：尚待逐项展示与核验。
