# Prolific 会话音频标注系统计划文档

目标：构建一个面向 **Collaborative Turn Completion（CTC）** 与 **Pragmatic Pairs（PP）** 的会话音频标注系统。 Worker 通过 Prolific 进入一个统一 HTML 标注页面，页面展示双声道波形、转写片段和可拖拽时间戳区域； 标注结果以 JSON 自动提交到你的服务器，并与 **PROLIFIC_PID / STUDY_ID / SESSION_ID** 绑定。

- 🎧 双声道会话音频
- 🧩 CTC / PP taxonomy
- ⏱️ 可拖拽时间戳 region
- 🧾 JSON 自动提交
- 🧪 Gold check + 质量控制

## 0. 一句话总览

**最省心的系统形态：** 不给 worker 创建 Label Studio 账号，也不为每条音频生成单独页面。 只部署一个统一入口 `/annotate`，由后端根据 Prolific 的 participant/session ID 自动分配若干会话音频任务。 Worker 完成标注后，前端把结构化 JSON 发给服务器，保存成功后再跳回 Prolific completion URL。

- **1. Prolific 招募**：筛选参与者，发放 study link，自动注入参与者 ID。

- **2. 进入统一 HTML**：URL 带有 PROLIFIC_PID、STUDY_ID、SESSION_ID。

- **3. 后端分配任务**：给该 session 分配 N 段会话音频，避免重复与超额。

- **4. 音频标注**：听波形、拖 region、修 transcript、选 CTC/PP/BC 标签。

- **5. JSON 保存**：POST 到 /api/submit，服务器写入 JSON/SQLite。

- **6. 回到 Prolific**：保存成功后 redirect completion URL，之后 approve/reject。

## 4. 系统架构：一个 HTML，不是一万个 HTML

不建议为每个音频文件生成一个独立页面。更好的方式是：只有一个前端页面 `/annotate`， 后端根据 `SESSION_ID` 分配任务。这样才能统一控制 worker 身份、重复标注次数、gold check 和提交记录。

Prolific

Study link→ 自动注入 PROLIFIC_PID / STUDY_ID / SESSION_ID→ Completion URL

前端 HTML

读取 URL 参数→ 请求 /api/assign→ 显示 WaveSurfer 标注器→ POST /api/submit

后端 API

分配任务→ 锁定 session→ 保存 JSON→ 返回 success

数据层

tasks.json / SQLite→ assignment table→ submissions→ QC / export

### Prolific 里只需要填一个入口链接

```
https://your-domain.com/annotate?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

### 服务器目录结构建议

```
conversation_annotation_app/
  app.py                       # Flask/FastAPI 后端
  static/
    annotate.html              # 唯一入口页面
    app.js                     # 前端逻辑：WaveSurfer + 表单 + fetch submit
    style.css
  data/
    tasks.json                 # 所有会话任务清单
    gold.json                  # gold check 标准答案
    assignments.sqlite         # 可选：任务分配/提交状态
    submissions/
      SESSION_ID_001.json
      SESSION_ID_002.json
  audios/
    task_000001.wav
    task_000002.wav
```

## 5. 数据流：worker 是谁，系统自动知道

Worker 不需要手写自己是谁。前端从 URL 读取 Prolific 注入的 ID，然后每次请求任务和提交标注都带上这些 ID。

### 前端读取身份

```
const params = new URLSearchParams(window.location.search);

const prolificPid = params.get("PROLIFIC_PID");
const studyId = params.get("STUDY_ID");
const sessionId = params.get("SESSION_ID");
```

### 提交时绑定身份

```
const payload = {
  prolific_pid: prolificPid,
  study_id: studyId,
  session_id: sessionId,
  task_bundle_id: currentBundleId,
  annotations: annotations,
  started_at: startedAt,
  submitted_at: new Date().toISOString()
};

await fetch("/api/submit", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify(payload)
});
```

**关键原则：** 页面跳回 Prolific completion URL 之前，必须先确认服务器返回 `{"status": "ok"}`。 否则会出现 Prolific 上显示完成，但你的服务器没有收到标注 JSON 的情况。

## 6. JSON Schema：建议按“文件级 + 事件级 + segment级”保存

你的示例 HTML 已经把标注导出为 `annotation_json`，包含 `source`、`ctc_status`、`segments` 等字段。 新 schema 可以进一步细化为 conversation annotation 专用格式。

```
{
  "schema_version": "conversation-annotation-v2",
  "worker": {
    "prolific_pid": "abc123",
    "study_id": "study456",
    "session_id": "session789"
  },
  "task": {
    "task_id": "seamless_ctc_V00_S0759_I00000936",
    "audio_url": "/audios/task_000001.wav",
    "dataset": "seamless_interaction",
    "bundle_id": "bundle_00042"
  },
  "file_level": {
    "target_status": ["is_CTC"],
    "audio_quality": "usable",
    "transcript_quality": "needs_minor_correction"
  },
  "events": [
    {
      "event_id": "evt_0001",
      "event_type": "Assistive_CTC",
      "speaker_in_trouble": "Left",
      "helper_speaker": "Right",
      "trouble_utterance": {
        "start": 3.82,
        "semantic_word_end_before_stall": 6.68,
        "transcript": "I think I, what..."
      },
      "helper_response": {
        "start": 5.04,
        "end": 10.79,
        "transcript": "That is a Bonds Club card.",
        "response_type": "provide_word",
        "is_question_form": false,
        "is_prompt": false,
        "guess_accuracy": "correct"
      },
      "overlap": {
        "has_overlap": true,
        "start": 5.04,
        "end": 6.68
      },
      "notes": ""
    }
  ],
  "segments": [
    {
      "segment_id": "seg-00001-003",
      "channel": 0,
      "speaker": "Left",
      "start": 3.82,
      "end": 6.68,
      "transcript": "I think I, what?",
      "flags": []
    }
  ],
  "ui_metadata": {
    "started_at": "2026-05-28T12:00:00Z",
    "submitted_at": "2026-05-28T12:09:00Z",
    "lead_time_ms": 540000
  }
}
```

### 字段设计重点

**worker 身份**：用 Prolific 参数，不让 worker 手写。

**task 信息**：保存 audio_id、dataset、bundle_id，方便回溯。

**file_level**：先判断是否目标现象，支持剔除。

**events**：真正的 CTC / PP 事件。

**segments**：底层时间戳片段和 transcript。

**ui_metadata**：记录时长、浏览器行为、是否通过 gold。

## 7. 后端需要做什么？

后端不复杂，但它是系统能否规模化的关键。纯静态 HTML 可以展示页面，但无法可靠保存结果、分配任务、控制重复标注次数。

### /annotate 页面入口

返回统一 HTML。URL 上带 Prolific 三个 ID。

### /api/assign 任务分配

根据 session_id 分配一组音频任务，写入 assignment 记录。

### /api/submit 保存提交

验证 JSON，保存到 submissions，并返回 success。

### 任务分配逻辑

```
目标：每条音频至少被 K 个不同 worker 标注，例如 K = 3。

分配时：
1. 读取 session_id 是否已有 assignment
2. 如果已有，返回同一组任务，避免刷新导致换题
3. 如果没有，从未满 K 次的任务里抽取 N 个
4. 混入少量 gold tasks
5. 写入 assignments 表：
   session_id, prolific_pid, task_ids, assigned_at, submitted=false
```

### 提交保存逻辑

```
POST /api/submit

检查：
- prolific_pid / study_id / session_id 是否存在
- session_id 是否对应已分配任务
- 每个 required event 是否有 transcript
- 时间戳是否 start < end
- gold check 是否明显失败

保存：
- data/submissions/{session_id}.json
- 或 SQLite: submissions table

返回：
{"status": "ok", "completion_url": "https://app.prolific.com/submissions/complete?cc=XXXX"}
```

## 8. 质量控制：不要只靠 worker 自觉

### Gold check

每个 bundle 混入 1–2 个你已知答案的会话片段，检查 worker 是否能正确识别 CTC / PP。

### 时间行为检查

记录每个任务停留时间、播放次数、region 修改次数。如果 30 秒提交 10 段音频，应该人工复查。

### 多数投票 / 复核

每条音频至少 2–3 人标注。高一致性直接采用；低一致性进入 adjudication。

### Transcript 局部校验

要求所有标注时间范围内 transcript 准确；不强迫修完整音频，只修目标区域。

| QC 指标 | 可自动计算吗？ | 用途 |
| --- | --- | --- |
| Gold accuracy | 可以 | 决定 approve、manual review 或 reject。 |
| Lead time | 可以 | 识别明显乱填或挂机。 |
| Inter-annotator agreement | 可以 | 发现定义不清或困难样本。 |
| Transcript correctness | 半自动 | 优先人工抽检；也可用 ASR 对齐辅助。 |
| Timestamp sanity | 可以 | 检查 start/end、overlap、speaker channel 是否合理。 |

## 9. 从你现有示例 HTML 升级的路线

你的现有示例已经能跑：它用 WaveSurfer 加载 WAV，支持双声道、regions、segment 列表、transcript、segment flags，并能生成 JSON。 接下来不是推倒重写，而是逐步升级。

- **Phase 1**：**改 taxonomy 和字段** 把现有 `ctc_status`、`segment_flags` 改成 CTC / PP / Complex 专用字段。

- **Phase 2**：**从 MTurk 表单提交改成 Prolific + fetch JSON** 保留 JSON preview，但提交时 POST 到你的 `/api/submit`，成功后跳转 Prolific completion URL。

- **Phase 3**：**增加 /api/assign 动态分配** 不要为每个任务生成独立 HTML；让后端给每个 session 分配一组任务。

- **Phase 4**：**加入 gold check 和 QC dashboard** 根据 gold、时长、一致性、timestamp sanity 判断 worker 质量。

- **Phase 5**：**正式批量发布** 先 pilot 20–50 人，再扩大到主批次；每批控制任务量和付款预算。

## 10. 最小可行版本 MVP

**第一版不要做复杂后台。** 只做一个 Flask/FastAPI 后端 + 一个 HTML 前端 + JSON 文件保存即可。SQLite 可以第二步再加。

### MVP 必须完成

Prolific URL 参数读取：PROLIFIC_PID / STUDY_ID / SESSION_ID。

WaveSurfer 双声道音频播放和 region 编辑。

CTC / PP 专用标签表单。

所有目标时间段 transcript 必填。

POST /api/submit 保存 JSON。

保存成功后跳转 Prolific completion URL。

### Prolific 上的 study 设置

```
Study URL:
https://your-domain.com/annotate?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}

Estimated time:
先用 pilot 估计，例如 8–12 分钟

Completion:
使用 Prolific completion URL；
不要在前端一开始就暴露，必须等 /api/submit 成功后再 redirect。
```

### 每个 worker 做多少？

| 阶段 | 每人任务量 | 目的 |
| --- | --- | --- |
| Pilot | 3–5 段音频 | 验证说明是否清楚、界面是否顺畅、平均耗时。 |
| Small batch | 8–12 段音频 | 评估一致性、gold 通过率、付款是否合理。 |
| Main batch | 按耗时调整 | 正式收集，每段音频 2–3 人标注。 |

## 11. 最终你要得到什么数据？

最终导出的数据不只是“某个 worker 选了哪个标签”，而应该能支持模型评估： 哪些地方发生了 CTC、是否 assistive、是否 buzz-in、是否 PP、时间戳是否重叠、猜测是否正确。

### 事件检测

该片段是否存在 CTC / PP。

### 事件分类

Assistive CTC / Non-Assistive CTC / Pragmatic Pairs。

### 时间戳

被打断 utterance、打断回应、重叠部分。

### 内容准确性

transcript 修正、猜测是否正确、引导后的片段关系。

## 12. 开发优先级

1. **先改现有 HTML 的标签体系：**把 UI 标签变成你现在定义的 CTC / PP taxonomy。
2. **再接 Prolific ID：**从 URL 读取 `PROLIFIC_PID`、`STUDY_ID`、`SESSION_ID`。
3. **再加后端保存：**把 JSON 从隐藏表单提交改成 `fetch("/api/submit")`。
4. **最后做动态分配：**先可以一个页面一个任务，pilot 跑通后再做 `/api/assign`。

**建议：** 不要一开始就做“完整平台”。你已经有可跑的标注 HTML，应该先用它改出一个 Prolific-compatible pilot。 Pilot 跑通后，再做任务池、自动分配、多 worker 冗余和 dashboard。

Conversation Annotation System Plan · CTC / Pragmatic Pairs · Prolific + HTML + JSON backend
