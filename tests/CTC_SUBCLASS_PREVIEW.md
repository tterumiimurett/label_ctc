# CTC subclass JSONL 本地预览

这个工具用于只读查看 `tables/` 下的 subclass JSONL。它独立于原有
`prolific/run_ctc_verification_review_app.sh`，不会读取、覆盖或写入
`prolific/ctc_verification_app/data/`。

## 能看什么

- 按 `Stuck word`、`Stuck guide`、`Not stuck`、`Not CTC` 筛选。
- 搜索 interaction ID、candidate key、transcript 或 completion target。
- 同时显示原始录音绝对时间和当前音频片段的相对时间。
- 在波形上标出 main speaker 最后一个词结束时间，以及 interrupter 第一个词开始时间。
- 查看分类依据、上下文、对话轮次和完整原始 JSONL row。

当前三个文件的实际分布如下：

| Split | Rows | Stuck word | Stuck guide | Not stuck (`unstuck`) | Not CTC |
| --- | ---: | ---: | ---: | ---: | ---: |
| dev | 369 | 39 | 0 | 102 | 228 |
| test | 292 | 28 | 0 | 73 | 191 |
| train | 6217 | 765 | 0 | 1550 | 3902 |

`Stuck guide` 是预览器支持的类别，但当前这三个 JSONL 中实际都是 0 条。

## 运行环境

需要 Python 3.10 或更高版本。启动脚本会优先使用仓库中的
`.venv/bin/python`，不存在时再使用系统 `python3`。预览 server 只使用
Python 标准库，不需要额外安装 Web 框架。

## 预览 test

在仓库根目录运行：

```bash
./tests/run_ctc_subclass_preview_app.sh
```

浏览器打开：

```text
http://127.0.0.1:8004/preview
```

test 是默认 split，脚本会自动使用：

```text
tables/high_confidence_candidates_test_doubao_gemini_audio_check_subclass.jsonl
label_studio/data/tasks_test_predictions.json
```

## 预览 dev

只需切换 JSONL；脚本会根据文件名自动选择 dev 的 source tasks：

```bash
JSONL=tables/high_confidence_candidates_dev_doubao_gemini_audio_check_subclass.jsonl \
PORT=8005 \
./tests/run_ctc_subclass_preview_app.sh
```

浏览器打开 `http://127.0.0.1:8005/preview`。

## 预览 train

仓库目前没有 `tasks_train_predictions.json`，因此 train 可以查看分类、
上下文、时间戳和原始 JSON，但默认没有可播放音频：

```bash
JSONL=tables/high_confidence_candidates_train_doubao_gemini_audio_check_subclass.jsonl \
PORT=8006 \
./tests/run_ctc_subclass_preview_app.sh
```

浏览器打开 `http://127.0.0.1:8006/preview`。页面会明确显示 audio match 为
`0/6217`，这不是 JSONL 加载失败。

如果本地另有对应的 train source-task JSON，可以显式传入：

```bash
JSONL=tables/high_confidence_candidates_train_doubao_gemini_audio_check_subclass.jsonl \
SOURCE_TASKS=/absolute/path/to/tasks_train_predictions.json \
PORT=8006 \
./tests/run_ctc_subclass_preview_app.sh
```

source-task JSON 的结构应与仓库中的
`label_studio/data/tasks_test_predictions.json` 相同。

## 常用参数

```bash
HOST=127.0.0.1
PORT=8004
JSONL=/path/to/candidates.jsonl
SOURCE_TASKS=/path/to/tasks.json
PYTHON_BIN=/path/to/python
```

- 默认只监听本机 `127.0.0.1`。
- 如果端口被占用，换一个 `PORT`。
- `SOURCE_TASKS=''` 可以强制关闭音频匹配，只查看 JSONL 内容。
- 使用 `Ctrl+C` 停止 server。

## 时间戳含义

- `Absolute`：原始 conversation timeline 中的时间。
- `Clip-relative`：浏览器音频和波形中的时间，计算方式为
  `absolute timestamp - candidate clip start`。
- 红色标记：`main_speaker_last_word_end_time`。
- 紫色标记：`interrupter_first_word_start_time`。
- `Gap`：上述两个绝对时间之差，对应 JSONL 中的
  `subclass_gap_seconds` / `subclass_gap_ms`。

## 验证

运行完整测试：

```bash
.venv/bin/python -m unittest discover -s tests -v
```
