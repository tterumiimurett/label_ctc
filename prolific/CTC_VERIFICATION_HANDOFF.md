# CTC Verification App 交接文档

本文档说明当前 CTC verification 标注任务的数据来源、采样方式、server 启动方式、配置参数，以及 Prolific 上的设置方式。

## 1. App 功能

这个 app 用于让标注者检查预标注的 CTC 候选。每条候选里，标注者需要判断：

```text
第二个说话人是否补全/帮助补全了第一个说话人未完成的句子
第一个说话人是否卡住
interruption type
红线：interruption 前最后一个有效词的结束时间
橙线：interrupting utterance 的真实开始时间
transcript 是否需要修正
```

App 所在目录：

```text
prolific/ctc_verification_app/
```

主要文件：

```text
prolific/ctc_verification_app/app.py
prolific/ctc_verification_app/static/verify.html
prolific/ctc_verification_app/static/app.js
prolific/ctc_verification_app/static/style.css
```

## 2. 数据和采样

当前正式 800 条数据文件是：

```text
tables/ctc_verification_train_balanced_800.jsonl
```

该文件包含：

```text
800 total candidates
400 subclass = stuck word
400 subclass = unstuck
800 unique candidate_key values
786 unique interaction_id values
800 rows with tos_audio
```

这个文件从下面的候选文件中采样得到：

```text
label_studio/data/high_confidence_candidates_train_doubao_gemini_audio_check_subclass_with_tos_urls.jsonl
```

采样目标：

```text
400 stuck candidates
400 non-stuck / unstuck candidates
candidate_key 保持唯一
每条样本都可以通过 tos_audio 找到音频 URL
```

App 也可以使用下面这个 source-task / upload mapping 文件：

```text
label_studio/data/seamless_ctc_train_upload_checkpoint.jsonl
```

`SOURCE_TASKS` / `--source-tasks` 是历史兼容参数：旧版 candidate 文件没有稳定的公网音频 URL 时，app 会从 source-task / upload mapping 文件里补 `audio_url`。

当前 train first100 / balanced 800 不需要 `SOURCE_TASKS`，因为下面两个文件本身已经包含可播放的 `tos_audio.outer_url`：

```text
tables/ctc_verification_train_balanced_first100.jsonl
tables/ctc_verification_train_balanced_800.jsonl
```

app 的取音频逻辑是：

```text
优先使用 source_tasks 中的 audio_url
如果没有 source_tasks，则使用 candidate 自带的 tos_audio.outer_url / audio_url
```

因此当前 launch 脚本建议保持 `SOURCE_TASKS=` 为空。只有在换回旧数据、或 candidate 文件本身没有音频 URL 时，才需要显式传入 `SOURCE_TASKS`。

之前使用过的内部测试 / calibration 数据：

```text
tables/ctc_verification_internal_test_2.jsonl
tables/ctc_verification_internal_test_50.jsonl
tables/ctc_verification_internal_train_100.jsonl
```

当前 internal train 100 脚本使用的是：

```text
tables/ctc_verification_internal_train_100.jsonl
```

对应启动脚本：

```text
prolific/run_ctc_verification_internal_train_100.sh
```

这个脚本默认不传 `--source-tasks`，因为 `ctc_verification_internal_train_100.jsonl` 本身已经包含可播放的 `tos_audio.outer_url` / `audio_url` 信息。

## 3. 重要配置参数

Verification server 通过命令行参数配置：

```text
--source-tasks      包含可播放音频 URL 或 upload mapping 的 JSON/JSONL 文件
--auto-labels       包含预标注 CTC candidates 的 JSONL 文件或 glob
--data-dir          runtime 输出目录，用于存 assignments、drafts、submissions
--bundle-size       每个 Prolific submission 分配多少条 candidate
--redundancy        每条 candidate 最多收集多少个 submitted labels
--completion-url    Prolific completion URL，包含 completion code
--host              server 绑定的 host
--port              server 端口
```

当前 train first100 / balanced 800 的 `--auto-labels` 文件已经带音频 URL，所以 `--source-tasks` 可以不传。`prolific/run_ctc_verification_first100_nohup.sh` 默认 `SOURCE_TASKS=`，只有手动设置了非空 `SOURCE_TASKS` 才会传给 app。

推荐的正式 Prolific 配置：

```text
BUNDLE_SIZE=1
REDUNDANCY=3
```

原因：

```text
每个 Prolific submission 只标 1 条 candidate
每条 candidate 最多收集 3 个 submitted labels
如果 Prolific 允许同一个 participant 多次提交，同一个熟练标注者可以连续完成多条 one-candidate submissions
App 会避免同一个 Prolific PID 重复拿到同一条 candidate
```

Assignment 逻辑：

```text
同一个 SESSION_ID 会返回同一组 assigned candidates
同一个 PROLIFIC_PID 在不同 SESSION_ID 中不会重复拿到同一条 candidate
每条 candidate 达到 REDUNDANCY 个 submitted labels 后停止分配
已经分配但尚未提交的 assignment 会暂时占用名额，直到提交或手动清理 assignments.json
```

Internal train 100 脚本的默认配置：

```text
HOST=0.0.0.0
PORT=8002
SOURCE_TASKS=
AUTO_LABELS=tables/ctc_verification_internal_train_100.jsonl
DATA_DIR=prolific/ctc_verification_app/data_internal_train_100
BUNDLE_SIZE=100
REDUNDANCY=1
ASSIGNMENT_TIMEOUT_MINUTES=0
COMPLETION_URL=http://127.0.0.1:8002/verify
```

这些默认值表示：一个本地 annotator 打开一次任务会拿到 100 条 candidate，适合内部完整 trial；`REDUNDANCY=1` 是因为三个人通常在三台电脑/三个 session 上各自跑一份，而不是让 server 在同一个 Prolific study 里自动收三份。

## 4. 在 Server 上启动任务

正式/生产式启动推荐使用 nohup 脚本：

```bash
COMPLETION_CODE='YOUR_PROLIFIC_COMPLETION_CODE' \
BUNDLE_SIZE=1 \
REDUNDANCY=3 \
HOST=127.0.0.1 \
PORT=8002 \
AUTO_LABELS='tables/ctc_verification_train_balanced_800.jsonl' \
SOURCE_TASKS='' \
DATA_DIR='prolific/ctc_verification_app/data' \
prolific/run_ctc_verification_nohup.sh
```

Internal train 100 本地运行：

```bash
prolific/run_ctc_verification_internal_train_100.sh
```

然后打开：

```text
http://127.0.0.1:8002/verify?PROLIFIC_PID=internal_a&STUDY_ID=train100&SESSION_ID=internal_a_train100
```

三个人内部标注时，建议每个人使用不同的 `PROLIFIC_PID` 和 `SESSION_ID`，例如：

```text
internal_a / internal_a_train100
internal_b / internal_b_train100
internal_c / internal_c_train100
```

脚本会写入：

```text
logs/prolific_ctc_verification.log
logs/prolific_ctc_verification.pid
```

在 server 本机检查：

```bash
curl http://127.0.0.1:8002/healthz
```

如果通过 Nginx reverse proxy 暴露到公网，也检查：

```bash
curl http://YOUR_EXTERNAL_IP/healthz
```

Prolific 上填写的 public study URL 应该是：

```text
http://YOUR_EXTERNAL_IP/verify
```

Prolific 会自动在 URL 后面追加 participant metadata，例如：

```text
PROLIFIC_PID
STUDY_ID
SESSION_ID
```

手动测试可以使用：

```text
http://127.0.0.1:8002/verify?PROLIFIC_PID=test_worker&STUDY_ID=test_study&SESSION_ID=test_session_001
```

停止 nohup 启动的 server：

```bash
kill "$(cat logs/prolific_ctc_verification.pid)"
```

然后重新运行上面的启动命令。

## 5. Nginx Reverse Proxy

App 通常在 server 本地运行在：

```text
127.0.0.1:8002
```

Nginx 负责把它暴露到公网。最小配置示例：

```nginx
server {
    listen 80;
    server_name YOUR_EXTERNAL_IP_OR_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8002;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

修改 Nginx 配置后：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

同时确认云服务器防火墙允许公网访问 HTTP 端口 80。

## 6. Prolific Study 设置

Prolific study 类型：

```text
Data collection type: External Study Link
Study URL: http://YOUR_EXTERNAL_IP/verify?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
Completion method: Redirect URL / completion code
Completion code: 使用启动 app 时填入 COMPLETION_CODE 的那个 code
```

推荐 participant / submission 设置：

```text
Submissions > Total times a participant can complete your study: Multiple
Bundle size in app: 1
Redundancy in app: 3
```

Prolific places 数量应该按照“需要多少条 labels”设置，而不是按照“有多少 unique candidates”设置。

例子：

```text
800 candidates x 3 labels each = 2400 total submissions/places
100 candidates x 3 labels each = 300 total submissions/places
```

如果要邀请熟练工，可以使用 Prolific 的 Custom Allowlist，或者在新 study 中 include previous approved participants。

## 7. Runtime 输出

正式脚本默认输出到：

```text
prolific/ctc_verification_app/data/
```

Internal train 100 脚本默认输出到：

```text
prolific/ctc_verification_app/data_internal_train_100/
```

目录结构：

```text
assignments.json              assignment 状态
drafts/SESSION_ID.json        自动保存的 draft labels
submissions/SESSION_ID.json   最终提交的 labels
```

注意：

```text
SESSION_ID 决定 draft/submission 文件名
Drafts 用于 reload / resume
只有标注者点击 Save and submit 并通过 validation 后，才会写入 final submission
不要 commit 真实 runtime submissions 或 participant data
```

## 8. Static Examples

音频例子：

```text
prolific/ctc_verification_app/static/examples/audio/
```

视频 demo：

```text
prolific/ctc_verification_app/static/examples/video/
```

Instruction 页面里只放视频链接，不直接嵌入视频。Server 已经支持 HTTP Range requests，因此 MP4 视频可以拖动进度条。

如果视频没有 commit 到 git，需要手动把视频文件复制到 server 上相同路径。

## 9. Validation 规则

App 同时做 client-side 和 server-side validation。

硬规则包括：

```text
Relevant interruption 问题必须回答
如果 relevant = No，不要求 timestamp 和 transcript
如果 relevant = Yes，speaker_stuck 必须回答
如果 stuck = Yes，interruption_type 必须选择
如果 interruption_type 不是 guiding_question，intention fit 必须回答
End of last word timestamp 必须在 audio clip 内
Start of interrupting utterance timestamp 必须在 audio clip 内
End of last word 必须早于 start of interrupting utterance
Relevant = Yes 时，interrupted transcript 必填
Relevant = Yes 时，transcript check checkbox 必须勾选
Relevant = Yes 时，interrupter start check checkbox 必须勾选
Relevant = Yes 时，interrupter becomes main speaker 必须回答
```

软提醒包括：

```text
红线在 auto-generated interrupted range 之前或等于其开始
红线在 auto-generated interrupted range 之后
橙线在 auto-generated interrupted range 之前
橙线在 auto-generated interrupting range 之前
橙线在 auto-generated interrupting range 之后或等于其结束
Interrupted transcript 看起来没变，但 auto range 在 interruption start 之后仍有内容
Interrupting transcript 为空
```

软提醒会要求标注者 double-check，但确认后仍然可以提交。

## 10. 发布前 Checklist

发布 Prolific study 前检查：

```text
1. 确认 auto-label 文件存在，且 candidate 数量正确
2. 确认 audio URLs 可以从 server 访问
3. 用正式 DATA_DIR、BUNDLE_SIZE、REDUNDANCY、COMPLETION_CODE 启动 app
4. 本机和公网都检查 /healthz
5. 用测试 URL 参数打开 /verify 并提交一条测试 assignment
6. 确认测试 submission 出现在 DATA_DIR/submissions/
7. 清理测试 assignment/submission 文件，或正式任务使用新的 DATA_DIR
8. 确认 Prolific Study URL 是 http://YOUR_EXTERNAL_IP_OR_DOMAIN/verify
9. 如果 bundle size = 1，确认 Prolific places = candidates x redundancy
10. 如果需要熟练标注者重复提交，确认 Prolific 开启 Multiple submissions
```
