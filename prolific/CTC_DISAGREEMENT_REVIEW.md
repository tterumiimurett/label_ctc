# 使用原标注页面复核分歧

在仓库根目录运行（Python 3.10+）：

```bash
bash prolific/run_ctc_verification_researcher_disagreements.sh
```

打开终端打印的完整 URL。默认领取 65 条：至少有一名有效众包标注者的 `relevant_interruption` 与 researcher 的完整 first100 审核不同。包括众包认可、researcher 否定，以及相反的情况；“分歧”不等于已裁决的标注错误。

如果先看全体三人认可、researcher 否定的 4 条：

```bash
REVIEW_SET=unanimous bash prolific/run_ctc_verification_researcher_disagreements.sh
```

两种模式都直接启动原 `ctc_verification_app/app.py`，使用原页面、波形、话轮、题目和验证规则，不使用另做的 review.html。此提交不增加 confidence 字段；其前后端改动另行确认。

任务文件是原 first100 候选内容的固定子集，不包含 participant ID、众包答案或 researcher 答案。按 candidate_id 对齐，页面序号按当前子集重新编号。完整模式和四条模式使用不同的 study/session/data-dir，避免覆盖已有审核或互相占用 assignment。不要给两种模式指定同一个 DATA_DIR。

可以分次完成；保持同一完整链接、模式和数据目录恢复草稿。切换模式前停止当前服务，或用 PORT 指定另一个端口。音频需要联网访问。

全部提交后，结果分别位于：

- 完整分歧：`prolific/ctc_verification_app/data_researcher_disagreement_all_v1/submissions/researcher_disagreement_all_v1.json`
- 四条全票分歧：`prolific/ctc_verification_app/data_researcher_disagreement_unanimous_v1/submissions/researcher_disagreement_unanimous_v1.json`

把对应 JSON 上传回分析环境即可。旧审核保持原样；重复复核版本不会自动覆盖原参考。

## Confidence 待确认范围

复用原表单，在 CTC 判断附近增加必填单选：Confident、Somewhat Confident、Not Confident，不预选。对 Yes 和 No 都必填，仅表示对 CTC 判断的信心。新增字段 `ctc_confidence`，前端草稿、恢复、导出和最终 submission 均保存；后端校验三个枚举值。历史记录缺失值保留为未知，不补默认答案。建议以显式启用选项控制新必填规则，避免让已在进行的旧任务突然无法提交；是否启用以及正式发布另行确认。
