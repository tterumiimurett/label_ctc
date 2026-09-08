# First100 独立人工审核

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
