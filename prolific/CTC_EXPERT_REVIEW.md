# First100 独立人工审核

## 补齐全部 100 条：剩余 35 条（2026-09-12）

已完成 65 条审核后，使用这个独立入口补齐其余 35 条：

```bash
git pull origin main
bash prolific/run_ctc_verification_expert_complement35.sh
```

打开脚本打印的完整地址，默认端口 8005。需要 Python 3.10+ 以及远程音频的网络访问；判断题不预填，不显示众包答案。沿用现有问题、草稿保存与恢复机制，一次领取 35 条，可分多次完成。保持同一完整链接和数据目录即可恢复。

任务文件 `tables/ctc_verification_expert_complement35_20260912.jsonl` 是原 first100 减去已上传审核所对应的 65 条快照，二者无重叠，合计恰好 100 个唯一 candidate_id。不按目前可能新增的众包票数重新筛选。

本次按要求保留完整 35 条，包括历史 researcher submissions 中已看过的 3 条，可在之后比较重复审核的一致性。页面 Candidate 1–35 为本次序号，合并通过 candidate_id 完成。

结果独立保存到 `prolific/ctc_verification_app/data_expert_complement35_20260912/`，不覆盖旧审核。最终提交文件为 `submissions/expert_complement35_20260912_v1.json`。全部提交后关闭服务，在仓库根目录打包并上传：

```bash
tar -czf expert_complement35.tar.gz -C prolific/ctc_verification_app data_expert_complement35_20260912
```

回传后，用已上传的 65 条与本次 35 条组成完整 100 条审核，重新计算每位标注者的 CTC 一致率、误收、漏标和有效比较数。历史 7 条作为独立版本保留；重复记录不重复计数，变更的判断单独列出供核对。运行结果不随 Git 发布。

以下是此前审核入口与历史说明。

## 历史入口：排除已审核候选后的 61 条（2026-09-10）

```bash
bash prolific/run_ctc_verification_expert_agree2_first100.sh
```

此脚本现在加载 `tables/ctc_verification_expert_agree2_remaining61_20260910.jsonl`，共 61 条。审核范围仍来自 2026-09-09 的 65 条快照，没有按新收到的众包判断扩大范围。

已找到 7 条历史 researcher submissions，位于服务器的 `prolific/ctc_verification_app/data_train_first100_prolific/excluded_submissions/2026-09-08/researcher_tests/`；其中只有 4 条与该 65 条快照重合，所以本次待审核数为 65 − 4 = 61。原始 7 条结果保持原样，不随 Git 发布，也不需要下载到审核电脑。

打开脚本打印的新完整链接。使用新的 study/session 和数据目录 `prolific/ctc_verification_app/data_expert_agree2_remaining61_20260910/`，避免旧 assignment 和草稿因任务数变化而被覆盖。旧 65 条与 100 条入口产生的数据均保留；新入口不会自动迁移旧草稿。当前 Candidate 1–61 重新编号，始终以 `candidate_id` 对应样本。

标完并关闭服务后，在仓库根目录打包上传：

```bash
tar -czf expert_agree2_remaining61.tar.gz -C prolific/ctc_verification_app data_expert_agree2_remaining61_20260910
```

最终提交文件名为 `submissions/expert_agree2_remaining61_20260910_v1.json`。
待新结果回传后，将 61 条新审核与 7 条历史审核按 `candidate_id` 合并，检查重复和冲突；预期共有 68 条唯一审核结果。其中 65 条属于本轮筛选集，另外 3 条历史结果保留但不计入该筛选集的误收率分母。历史审核是先前的 researcher tests，其审核条件与本轮可能不同，分析时保留来源并分别核查。

下文保留先前 65 条及 100 条方案说明；当前运行以上 61 条入口。

## 优先审核：至少两人认可的 65 条（2026-09-09）

现在优先使用这个较小的审核入口：

```bash
bash prolific/run_ctc_verification_expert_agree2_first100.sh
```

打开脚本打印的完整地址，默认端口 8004。筛选口径为：有效 `submissions/` 中，同一个 `candidate_id` 至少有两名不同标注者的 `relevant_interruption` 为 true；不要求 `speaker_stuck` 为 true。当前共 65 条（35 条两票认可、30 条三票认可）。不读取 drafts 或 excluded_submissions，不把同一个人的重复判断算作多票。

任务快照是 `tables/ctc_verification_expert_agree2_first100_20260909.jsonl`，只包含原候选输入，不包含众包身份或答案。在另一台电脑上运行不需要下载众包 submissions。该快照冻结本次审核范围，后续众包数据变化不会使正在审核的列表改变。

页面仍沿用原表单，判断题留空，不显示具体票数或众包答案；由于候选经过筛选，你已知它们至少得到两票认可，因此这不是对筛选条件完全盲法的审核。

新页面的 Candidate 1–65 按子集重新编号，与原 100 条列表的序号不同；`candidate_id` 保持不变，用它匹配后续分析。
结果及草稿保存到独立目录 `prolific/ctc_verification_app/data_expert_agree2_first100_20260909/`。原 100 条审核的进度保留，新入口不会自动导入旧草稿。可分多次完成，恢复时保持同一完整链接和数据目录。
最终提交文件为 `submissions/expert_agree2_first100_20260909_v1.json`。完成并关闭服务后，在仓库根目录打包回传：

```bash
tar -czf expert_agree2_first100.tar.gz -C prolific/ctc_verification_app data_expert_agree2_first100_20260909
```

本轮主要评估该筛选集的误收比例，也可在其中比较两票和三票认可的结果。由于未审核其余候选，本轮不能估计完整召回率。以下 100 条入口仍保留，需要扩展审核范围时再使用。

## 本地启动

在包含本次变更的提交已同步到远端后，在自己的电脑上执行：

```bash
git pull
bash prolific/run_ctc_verification_expert_train_first100.sh
```

需要 Python 3.10+，服务本身只使用标准库，无需安装 Label Studio。
打开启动脚本打印的完整地址：

```text
http://127.0.0.1:8003/verify?PROLIFIC_PID=expert&STUDY_ID=expert_train_first100&SESSION_ID=expert_train_first100_v1
```

这些参数是本地审核专用代号，不需要真实 Prolific 账号或 completion code。
默认只监听本机。端口被占用时使用 `PORT=8004 bash prolific/run_ctc_verification_expert_train_first100.sh`，并打开脚本打印的新地址。
可用 `PYTHON_BIN=/path/to/python3` 指定解释器。
音频使用候选文件中的远程地址，电脑需要能访问这些地址；音频不是随 Git 下载的本地文件。

## 审核内容与保存

- 使用已跟踪的 `tables/ctc_verification_train_balanced_first100.jsonl`，与众包 first100 study 使用同一份候选输入，不需要复制众包 submission 到本机。
- 一次分配全部 100 个候选，每个只审核一次。保留原 `candidate_id` 和 `task_id`，用于之后逐条匹配。
- 沿用原表单及校验规则；是否帮助完成句子、是否卡住等判断留空，众包答案和票数不显示。原有自动转录及时间边界仍会预填，需要听音频核对。
- 草稿和最终结果独立保存到 `prolific/ctc_verification_app/data_expert_train_first100/`，不覆盖内部训练或众包数据。
- 可分多次完成。暂停前切换到另一条候选、等待草稿保存；恢复时启动同一脚本并打开同一个完整地址，保持数据目录和三个身份参数不变。可从候选下拉框跳转。
- 全部标完后提交；以 `submissions/expert_train_first100_v1.json` 存在为最终提交依据，`drafts/` 仅为草稿。最终提交后不要通过更换身份重复领取。
- 边界案例在 note 中说明，之后可以单独检查，不需要为了与众包一致而调整判断。

## 回传结果

关闭服务后，在仓库根目录打包：

```bash
tar -czf expert_train_first100.tar.gz -C prolific/ctc_verification_app data_expert_train_first100
```

将该压缩包作为文件上传回来即可，不需要提交运行数据到 Git。
完整目录包含 assignment、草稿和最终 submission，方便恢复和检查；默认目录和压缩包已加入 `.gitignore`。
如设置自定义 `DATA_DIR`，打包路径也要相应调整。

## 后续分析约定

以你的独立判断作为这次实验的参考标签，通过 `candidate_id` 合并众包与审核结果。
分别报告 `relevant_interruption`（帮助完成句子）和 `candidate_valid`（帮助完成且卡住）的比较，不提前将两者混为同一个 CTC 定义。
比较“至少 2 个认可”与“3 个全部认可”，重点报告通过筛选的候选数、人工否定数和误收比例（人工否定数 / 筛选通过且已审核数），并列出分歧案例。

2026-09-08 本地检查：当前有效 submissions 为 271 份，仍覆盖全部 100 个候选；74 个有 3 份、23 个有 2 份、3 个只有 1 份。此计数会随有效数据整理变化。分析时重新统计实际票数，只读取有效 `submissions/`，不把 `drafts/` 或 `excluded_submissions/` 算进去。
对缺票候选单独报告；“3/3”要求有 3 份有效判断且都为正，不能把只有 2 份且都为正称为 3/3。还应在有完整 3 份判断的候选上比较两种规则，以免缺票混淆结果。

验收目标为误收率不超过 1%，理想零误收。报告应同时给出样本量及不确定性；本批零错误不能直接证明未来误收率低于 1%。结论仅适用于这套候选来源和筛选流程，不外推为每个标注者单独标注都可靠。
