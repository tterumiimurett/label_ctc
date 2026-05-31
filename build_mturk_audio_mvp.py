#!/usr/bin/env python3
"""Build a single-task MTurk HTMLQuestion audio annotation MVP."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any


FILE_FLAGS = [
    "is_CTC",
    "in_the_Middle",
    "not_CTC",
    "Pragmatic_Pairs",
    "Buzz_in",
]
SEGMENT_FLAGS = ["incorrect_guess", "is_assure", "is_prompt"]


def _first_result_list(task: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("annotations", "predictions"):
        records = task.get(key) or []
        if records:
            return records[0].get("result", [])
    return []


def _existing_choices(results: list[dict[str, Any]], name: str) -> list[str]:
    for result in results:
        if result.get("from_name") == name:
            return list(result.get("value", {}).get("choices", []))
    return []


def build_payload(task: dict[str, Any], dataset: str, task_index: int) -> dict[str, Any]:
    """Normalize one Label Studio task into the browser-side MVP model."""
    results = _first_result_list(task)
    transcript_by_id: dict[str, str] = {}
    flags_by_id: dict[str, list[str]] = {}
    notes_by_id: dict[str, str] = {}

    for result in results:
        region_id = str(result.get("id", ""))
        value = result.get("value", {})
        name = result.get("from_name")
        if name == "transcript":
            transcript_by_id[region_id] = str((value.get("text") or [""])[0])
        elif name == "segment_flags":
            flags_by_id[region_id] = list(value.get("choices", []))
        elif name == "segment_note":
            notes_by_id[region_id] = str((value.get("text") or [""])[0])

    segments: list[dict[str, Any]] = []
    for result in results:
        if result.get("from_name") != "channel":
            continue
        value = result.get("value", {})
        region_id = str(result.get("id", ""))
        channel = int(value.get("channel", 0))
        labels = value.get("labels") or []
        segments.append(
            {
                "id": region_id,
                "channel": channel,
                "label": str(labels[0] if labels else ("Left" if channel == 0 else "Right")),
                "start": float(value["start"]),
                "end": float(value["end"]),
                "transcript": transcript_by_id.get(region_id, ""),
                "flags": flags_by_id.get(region_id, []),
                "note": notes_by_id.get(region_id, ""),
            }
        )

    return {
        "schema_version": "mturk-audio-annotation-v1",
        "source": {
            "dataset": dataset,
            "task_index": task_index,
            "audio": str(task.get("data", {}).get("audio", "")),
            "path_seg": str(task.get("data", {}).get("path_seg", "")),
        },
        "ctc_status": _existing_choices(results, "ctc_status"),
        "segments": segments,
        "choices": {
            "ctc_status": FILE_FLAGS,
            "segment_flags": SEGMENT_FLAGS,
        },
    }


def _script_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def render_html(payload: dict[str, Any]) -> str:
    task_name = Path(payload["source"]["audio"]).name or "audio task"
    data_json = _script_json(payload)
    return (
        HTML_TEMPLATE.replace("__TASK_NAME__", html_lib.escape(task_name))
        .replace("__AUDIO_URL__", html_lib.escape(payload["source"]["audio"], quote=True))
        .replace("__TASK_JSON__", data_json)
    )


def render_html_question(html: str) -> str:
    safe_html = html.replace("]]>", "]]]]><![CDATA[>")
    return f"""<HTMLQuestion xmlns="http://mechanicalturk.amazonaws.com/AWSMechanicalTurkDataSchemas/2011-11-11/HTMLQuestion.xsd">
  <HTMLContent><![CDATA[
{safe_html}
  ]]></HTMLContent>
  <FrameHeight>1160</FrameHeight>
</HTMLQuestion>
"""


def render_design_layout(html: str) -> str:
    """Render the HTML fragment expected by Requester UI Design Layout source mode."""
    style = re.search(r"<style>.*?</style>", html, flags=re.DOTALL)
    body = re.search(r"<body>\n(.*)\n</body>", html, flags=re.DOTALL)
    if not style or not body:
        raise ValueError("Standalone HTML template is missing style or body content")
    content = body.group(1)
    form_open = re.compile(
        r'  <form name="mturk_form" method="post" id="mturk_form"\n'
        r'        action="https://www\.mturk\.com/mturk/externalSubmit">'
    )
    content, replacements = form_open.subn(
        '  <crowd-form id="mturk_form" answer-format="flatten-objects">', content, count=1
    )
    if replacements != 1:
        raise ValueError("Standalone HTML template is missing the MTurk form wrapper")
    content = content.replace("  </form>", "  </crowd-form>", 1)
    content = content.replace(
        '    <input type="hidden" name="assignmentId" id="assignmentId" value="">\n', "", 1
    )
    vendor_dir = Path(__file__).with_name("mturk_vendor")
    wavesurfer = (vendor_dir / "wavesurfer.min.js").read_text(encoding="utf-8")
    regions = (vendor_dir / "regions.min.js").read_text(encoding="utf-8")
    wavesurfer = wavesurfer.replace("</script", "<\\/script")
    regions = regions.replace("</script", "<\\/script")
    return f"""<!-- Paste this entire fragment into Requester UI Design Layout in source mode. -->
<script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
<!-- WaveSurfer is embedded because MTurk Preview can block third-party CDN script loading. -->
<script>{wavesurfer}</script>
<script>{regions}</script>
{style.group(0)}
{content}
"""


def render_design_layout_probe(payload: dict[str, Any]) -> str:
    """Create a minimal Requester UI layout that tests inline JavaScript execution."""
    audio_url = html_lib.escape(payload["source"]["audio"], quote=True)
    return f"""<!-- Diagnostic layout: paste into Design Layout source mode. -->
<script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
<crowd-form answer-format="flatten-objects">
  <h2>MTurk custom JavaScript diagnostic</h2>
  <p id="static-check" style="color: #166534"><strong>STATIC HTML: visible.</strong></p>
  <p id="js-check" style="color: #b91c1c"><strong>INLINE JAVASCRIPT: not executed.</strong></p>
  <p>Native audio check:</p>
  <audio controls preload="metadata" style="width: 100%">
    <source src="{audio_url}" type="audio/wav">
  </audio>
  <label style="display: block; margin-top: 16px">
    Diagnostic response
    <input name="diagnostic_response" value="probe-visible" style="display: block">
  </label>
</crowd-form>
<script>
  document.getElementById('js-check').innerHTML =
    '<strong>INLINE JAVASCRIPT: executed successfully.</strong>';
  document.getElementById('js-check').style.color = '#166534';
</script>
"""


def render_canvas_design_layout(payload: dict[str, Any]) -> str:
    """Create a compact Crowd Elements layout with a native canvas waveform editor."""
    audio_url = html_lib.escape(payload["source"]["audio"], quote=True)
    task_name = html_lib.escape(Path(payload["source"]["audio"]).name or "audio task")
    data_json = _script_json(payload)
    file_checks = "".join(
        f'<label><input type="checkbox" name="ctc_status" value="{html_lib.escape(choice)}">'
        f" {html_lib.escape(choice)}</label>"
        for choice in payload["choices"]["ctc_status"]
    )
    segment_checks = "".join(
        f'<label><input type="checkbox" name="ui_segment_flags" value="{html_lib.escape(choice)}">'
        f" {html_lib.escape(choice)}</label>"
        for choice in payload["choices"]["segment_flags"]
    )
    initial = payload["segments"][0] if payload["segments"] else {
        "start": 0,
        "end": 0,
        "channel": 0,
        "transcript": "",
        "note": "",
    }
    list_html = "".join(
        f'<button type="button" class="segment{" selected" if index == 0 else ""}" '
        f'data-i="{index}"><b class="c{segment["channel"]}">'
        f'{html_lib.escape(segment["label"])}</b> {segment["start"]:.2f}s - '
        f'{segment["end"]:.2f}s<br><small>{html_lib.escape(segment["transcript"])}</small></button>'
        for index, segment in enumerate(payload["segments"])
    )
    return CANVAS_LAYOUT_TEMPLATE.replace("__AUDIO_URL__", audio_url).replace(
        "__TASK_NAME__", task_name
    ).replace("__FILE_CHECKS__", file_checks).replace(
        "__SEGMENT_CHECKS__", segment_checks
    ).replace("__SEGMENT_LIST__", list_html).replace(
        "__START__", f"{initial['start']:.2f}s"
    ).replace("__END__", f"{initial['end']:.2f}s").replace(
        "__LEFT_SELECTED__", " selected" if initial["channel"] == 0 else ""
    ).replace("__RIGHT_SELECTED__", " selected" if initial["channel"] == 1 else "").replace(
        "__TRANSCRIPT__", html_lib.escape(initial["transcript"])
    ).replace("__NOTE__", html_lib.escape(initial["note"])).replace("__TASK_JSON__", data_json)


def _dataset_name(input_path: Path) -> str:
    stem = input_path.stem.lower()
    if "_test_" in stem:
        return "test"
    if "_dev_" in stem:
        return "dev"
    return input_path.stem


def generate(input_path: Path, output_dir: Path, task_index: int) -> tuple[Path, Path, Path, Path]:
    tasks = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"No tasks found in {input_path}")
    if task_index < 0 or task_index >= len(tasks):
        raise IndexError(f"task-index {task_index} is outside 0..{len(tasks) - 1}")

    dataset = _dataset_name(input_path)
    payload = build_payload(tasks[task_index], dataset, task_index)
    html = render_html(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{dataset}_task_{task_index:05d}"
    html_path = output_dir / f"{prefix}_preview.html"
    xml_path = output_dir / f"{prefix}_html_question.xml"
    layout_path = output_dir / f"{prefix}_design_layout.html"
    probe_path = output_dir / f"{prefix}_design_layout_probe.html"
    html_path.write_text(html, encoding="utf-8")
    xml_path.write_text(render_html_question(html), encoding="utf-8")
    layout_path.write_text(render_canvas_design_layout(payload), encoding="utf-8")
    probe_path.write_text(render_design_layout_probe(payload), encoding="utf-8")
    return html_path, xml_path, layout_path, probe_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single interactive MTurk audio annotation HTMLQuestion."
    )
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--task-index", type=int, default=0, help="Zero-based task index.")
    parser.add_argument("--output-dir", type=Path, default=Path("mturk_mvp"))
    args = parser.parse_args()

    html_path, xml_path, layout_path, probe_path = generate(
        args.input_json, args.output_dir, args.task_index
    )
    print(f"Preview HTML: {html_path}")
    print(f"MTurk HTMLQuestion: {xml_path}")
    print(f"Requester UI Design Layout: {layout_path}")
    print(f"Requester UI JavaScript probe: {probe_path}")


CANVAS_LAYOUT_TEMPLATE = """<!-- Compact MTurk Design Layout: Crowd Elements + native canvas waveform. -->
<script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
<style>
  .ctc { font: 14px Arial,sans-serif; color:#1f2937; max-width:1000px }
  .ctc h2 { font-size:16px; margin:0 0 10px } .card { border:1px solid #dbe2ea; border-radius:7px; padding:13px; margin:12px 0 }
  .checks { display:flex; gap:15px; flex-wrap:wrap } .controls { display:flex; align-items:center; flex-wrap:wrap; gap:10px; margin:9px 0 }
  button { padding:6px 10px; border:1px solid #94a3b8; border-radius:4px; background:#fff; cursor:pointer }
  button.primary { background:#0f766e; border-color:#0f766e; color:white; padding:9px 18px }
  #wave { width:100%; height:220px; display:block; border:1px solid #dbe2ea; border-radius:5px; touch-action:none }
  .c0 { color:#1f77b4 } .c1 { color:#ff7f0e } .muted { font-size:12px; color:#64748b }
  .columns { display:grid; grid-template-columns:34% 1fr; gap:14px } #list { max-height:310px; overflow:auto; border:1px solid #dbe2ea }
  .segment { text-align:left; width:100%; border:0; border-bottom:1px solid #e5e7eb; border-radius:0 }
  .segment.selected { background:#e2e8f0 } .segment small { color:#64748b }
  .times { display:grid; grid-template-columns:1fr 1fr 105px; gap:8px } .field { margin-bottom:10px }
  .field>label:first-child { font-weight:bold; display:block; margin-bottom:4px }
  input[type=text],select,textarea { width:100%; box-sizing:border-box; padding:6px; border:1px solid #cbd5e1; border-radius:4px }
  #status { margin-top:7px; color:#64748b } #error { display:none; color:#b91c1c; margin:10px 0 }
  @media(max-width:700px){.columns{grid-template-columns:1fr}}
</style>
<crowd-form answer-format="flatten-objects">
<div class="ctc">
  <h1>CTC Audio Annotation</h1><p class="muted">Audio: __TASK_NAME__</p>
  <div class="card"><h2>File-level flags (select at least one)</h2><div class="checks" id="file-flags">__FILE_CHECKS__</div></div>
  <div class="card">
    <h2>Stereo playback and timestamp annotation</h2>
    <audio id="audio" controls preload="metadata" style="width:100%"><source src="__AUDIO_URL__" type="audio/wav"></audio>
    <div class="controls">
      <button type="button" id="play-seg">Play selected segment</button>
      <label><input type="checkbox" name="ui_loop" id="loop" checked> Loop selected segment</label>
      <span id="clock">0.00s / 0.00s</span>
    </div>
    <div><b class="c0">Left</b> / <b class="c1">Right</b></div>
    <canvas id="wave"></canvas>
    <div class="controls"><b>Create segment:</b>
      <label><input type="radio" name="ui_new_channel" value="0" checked> Left</label>
      <label><input type="radio" name="ui_new_channel" value="1"> Right</label>
      <span class="muted">Drag an existing region or its edge; drag empty space to add a region.</span>
    </div>
    <div id="status">Waveform status: loading audio data...</div>
  </div>
  <div class="card">
    <h2>Selected segment annotation</h2>
    <div class="columns">
      <div id="list">__SEGMENT_LIST__</div>
      <div>
        <div class="times">
          <div class="field"><label>Start (s)</label><input name="ui_start" id="start" value="__START__" readonly></div>
          <div class="field"><label>End (s)</label><input name="ui_end" id="end" value="__END__" readonly></div>
          <div class="field"><label>Channel</label><select name="ui_channel" id="channel"><option value="0"__LEFT_SELECTED__>Left</option><option value="1"__RIGHT_SELECTED__>Right</option></select></div>
        </div>
        <div class="field"><label>Transcript (required)</label><textarea name="ui_transcript" id="transcript" rows="3">__TRANSCRIPT__</textarea></div>
        <div class="field"><label>Segment-level flags</label><div class="checks" id="segment-flags">__SEGMENT_CHECKS__</div></div>
        <div class="field"><label>Optional segment note</label><textarea name="ui_note" id="note" rows="2">__NOTE__</textarea></div>
        <button type="button" id="delete">Delete selected segment</button>
      </div>
    </div>
  </div>
  <input type="hidden" name="annotation_json" id="answer">
  <div id="error"></div><button class="primary" type="submit">Submit annotation</button>
</div>
</crowd-form>
<script type="application/json" id="seed">__TASK_JSON__</script>
<script>
(() => {
  const seed=JSON.parse(document.getElementById('seed').textContent), seg=seed.segments.map(s=>({...s,flags:[...s.flags]}));
  let pick=seg.length?0:-1, drag=null, duration=0, decoded=null, raf=0;
  const $=id=>document.getElementById(id), audio=$('audio'), canvas=$('wave'), ctx=canvas.getContext('2d');
  const fmt=n=>Number(n||0).toFixed(2)+'s', round=n=>Math.round(n*100)/100, chan=n=>n===0?'Left':'Right';
  function selected(){return pick>=0?seg[pick]:null}
  function resize(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=220*devicePixelRatio;ctx.scale(devicePixelRatio,devicePixelRatio);draw()}
  function x(t){return duration?t/duration*canvas.clientWidth:0} function time(px){return Math.max(0,Math.min(duration,px/canvas.clientWidth*duration))}
  function draw(){
    const w=canvas.clientWidth,h=220,mid=h/2; ctx.clearRect(0,0,w,h); ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,w,h);
    ctx.strokeStyle='#cbd5e1';ctx.beginPath();ctx.moveTo(0,mid);ctx.lineTo(w,mid);ctx.stroke();
    if(decoded) for(let ch=0;ch<Math.min(2,decoded.numberOfChannels);ch++){const d=decoded.getChannelData(ch),base=ch?165:55,amp=46;ctx.strokeStyle=ch?'#fdba74':'#93c5fd';ctx.beginPath();for(let px=0;px<w;px+=2){let max=0,start=Math.floor(px/w*d.length),end=Math.floor((px+2)/w*d.length);for(let i=start;i<end;i++)max=Math.max(max,Math.abs(d[i]));ctx.moveTo(px,base-max*amp);ctx.lineTo(px,base+max*amp)}ctx.stroke()}
    seg.forEach((s,i)=>{let top=s.channel?111:1;ctx.fillStyle=s.channel?'rgba(255,127,14,.30)':'rgba(31,119,180,.30)';ctx.fillRect(x(s.start),top,Math.max(2,x(s.end)-x(s.start)),108);if(i===pick){ctx.strokeStyle='#111827';ctx.lineWidth=2;ctx.strokeRect(x(s.start),top,Math.max(2,x(s.end)-x(s.start)),108);ctx.lineWidth=1}});
    if(duration){ctx.strokeStyle='#dc2626';ctx.beginPath();ctx.moveTo(x(audio.currentTime),0);ctx.lineTo(x(audio.currentTime),h);ctx.stroke()}
  }
  function output(){ $('answer').value=JSON.stringify({schema_version:seed.schema_version,source:seed.source,ctc_status:[...document.querySelectorAll('input[name=ctc_status]:checked')].map(e=>e.value),segments:seg.map(s=>({...s,start:round(s.start),end:round(s.end),label:chan(s.channel),transcript:s.transcript.trim(),note:s.note.trim()}))}) }
  function list(){ $('list').innerHTML=seg.map((s,i)=>`<button type="button" class="segment ${i===pick?'selected':''}" data-i="${i}"><b class="c${s.channel}">${chan(s.channel)}</b> ${fmt(s.start)} - ${fmt(s.end)}<br><small>${escapeHtml(s.transcript||'(transcript required)')}</small></button>`).join('');$('list').querySelectorAll('button').forEach(b=>b.onclick=()=>choose(+b.dataset.i)) }
  function escapeHtml(v){let e=document.createElement('div');e.textContent=v;return e.innerHTML}
  function choose(i){pick=i;let s=selected();if(!s)return; $('start').value=fmt(s.start);$('end').value=fmt(s.end);$('channel').value=s.channel;$('transcript').value=s.transcript;$('note').value=s.note;document.querySelectorAll('input[name=ui_segment_flags]').forEach(e=>e.checked=s.flags.includes(e.value));list();draw()}
  function edit(){let s=selected();if(!s)return;s.channel=+$('channel').value;s.transcript=$('transcript').value;s.note=$('note').value;s.flags=[...document.querySelectorAll('input[name=ui_segment_flags]:checked')].map(e=>e.value);list();draw();output()}
  audio.addEventListener('loadedmetadata',()=>{duration=audio.duration;$('clock').textContent=fmt(0)+' / '+fmt(duration);draw()});
  audio.addEventListener('timeupdate',()=>{let s=selected();$('clock').textContent=fmt(audio.currentTime)+' / '+fmt(duration);if(s&&audio.dataset.segment==='1'&&audio.currentTime>=s.end){if($('loop').checked)audio.currentTime=s.start;else audio.pause()}draw()});
  $('play-seg').onclick=()=>{let s=selected();if(s){audio.dataset.segment='1';audio.currentTime=s.start;audio.play()}};
  audio.addEventListener('play',()=>{cancelAnimationFrame(raf);const frame=()=>{draw();if(!audio.paused)raf=requestAnimationFrame(frame)};frame()});
  ['channel','transcript','note'].forEach(id=>$(id).addEventListener(id==='channel'?'change':'input',edit));$('segment-flags').onchange=edit;$('file-flags').onchange=output;
  $('delete').onclick=()=>{if(pick<0)return;seg.splice(pick,1);pick=Math.min(pick,seg.length-1);list();if(pick>=0)choose(pick);draw();output()};
  canvas.onpointerdown=e=>{if(!duration)return;let r=canvas.getBoundingClientRect(),px=e.clientX-r.left,t=time(px),ch=e.clientY-r.top<110?0:1,i=seg.findIndex(s=>s.channel===ch&&t>=s.start-.08&&t<=s.end+.08);if(i>=0){choose(i);let s=selected(),edge=Math.abs(px-x(s.start))<8?'start':Math.abs(px-x(s.end))<8?'end':'move';drag={kind:edge,base:t,start:s.start,end:s.end}}else{ch=+document.querySelector('input[name=ui_new_channel]:checked').value;seg.push({id:'new-'+Date.now(),channel:ch,label:chan(ch),start:t,end:Math.min(duration,t+.05),transcript:'',flags:[],note:''});choose(seg.length-1);drag={kind:'end',base:t,start:t,end:t+.05}}canvas.setPointerCapture(e.pointerId);draw()};
  canvas.onpointermove=e=>{if(!drag)return;let t=time(e.clientX-canvas.getBoundingClientRect().left),s=selected();if(drag.kind==='start')s.start=Math.min(t,s.end-.05);else if(drag.kind==='end')s.end=Math.max(t,s.start+.05);else{let delta=t-drag.base,len=drag.end-drag.start;s.start=Math.max(0,Math.min(duration-len,drag.start+delta));s.end=s.start+len}choose(pick);output()};
  canvas.onpointerup=()=>{drag=null}; window.addEventListener('resize',resize);
  fetch(seed.source.audio).then(r=>r.arrayBuffer()).then(b=>new AudioContext().decodeAudioData(b)).then(b=>{decoded=b;$('status').textContent='Waveform status: ready.';draw()}).catch(e=>{$('status').textContent='Waveform status: decode failed: '+e.message});
  document.querySelector('crowd-form').addEventListener('submit',e=>{output();let errs=[];if(!document.querySelector('input[name=ctc_status]:checked'))errs.push('Select a file-level flag.');seg.forEach((s,i)=>{if(!s.transcript.trim())errs.push('Segment '+(i+1)+' needs a transcript.')});if(errs.length){e.preventDefault();$('error').style.display='block';$('error').textContent=errs.join(' ')}});
  resize(); list(); if(pick>=0)choose(0); output();
})();
</script>
"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CTC Audio Annotation - __TASK_NAME__</title>
  <script src="https://unpkg.com/wavesurfer.js@7.10.1/dist/wavesurfer.min.js"></script>
  <script src="https://unpkg.com/wavesurfer.js@7.10.1/dist/plugins/regions.min.js"></script>
  <script src="https://s3.amazonaws.com/mturk-public/externalHIT_v1.js"></script>
  <style>
    :root {
      --ink: #1f2937;
      --muted: #64748b;
      --line: #dbe2ea;
      --panel: #f8fafc;
      --left: #1f77b4;
      --right: #ff7f0e;
      --accent: #0f766e;
      --danger: #b91c1c;
    }
    * { box-sizing: border-box; }
    body {
      color: var(--ink);
      font: 14px/1.4 Arial, Helvetica, sans-serif;
      margin: 0;
      padding: 18px;
      background: #fff;
    }
    h1 { font-size: 20px; margin: 0 0 4px; }
    h2 {
      font-size: 15px;
      margin: 0 0 12px;
      font-weight: 700;
    }
    .muted { color: var(--muted); font-size: 12px; }
    .card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin: 14px 0;
    }
    .flag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
    }
    label.choice {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .controls {
      align-items: center;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 10px;
    }
    button {
      background: white;
      border: 1px solid #94a3b8;
      border-radius: 5px;
      cursor: pointer;
      padding: 6px 12px;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      font-size: 15px;
      padding: 9px 20px;
    }
    button.danger { color: var(--danger); border-color: #fca5a5; }
    button:disabled { cursor: default; opacity: .48; }
    #time-display {
      font-variant-numeric: tabular-nums;
      font-size: 16px;
      min-width: 130px;
    }
    #waveform {
      border: 1px solid var(--line);
      border-radius: 6px;
      min-height: 222px;
      overflow: hidden;
    }
    #waveform ::part(region) { border-left: 1px solid rgba(15, 23, 42, .55); }
    .channel-key {
      display: flex;
      gap: 20px;
      margin: 9px 0 5px;
      font-weight: 700;
    }
    .dot {
      border-radius: 50%;
      display: inline-block;
      height: 10px;
      margin-right: 5px;
      width: 10px;
    }
    .layout {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(220px, 34%) 1fr;
    }
    #segments-list {
      border: 1px solid var(--line);
      border-radius: 5px;
      max-height: 320px;
      overflow-y: auto;
    }
    .segment-button {
      border: 0;
      border-bottom: 1px solid #eef2f7;
      border-radius: 0;
      display: block;
      padding: 8px 10px;
      text-align: left;
      width: 100%;
    }
    .segment-button.selected { background: #e2e8f0; }
    .segment-button .snippet {
      color: var(--muted);
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .left { color: var(--left); }
    .right { color: var(--right); }
    fieldset {
      border: 0;
      margin: 0 0 10px;
      padding: 0;
    }
    .field { margin-bottom: 10px; }
    .field > label:first-child {
      display: block;
      font-weight: 700;
      margin-bottom: 4px;
    }
    input[type="text"], textarea, select {
      border: 1px solid #cbd5e1;
      border-radius: 4px;
      font: inherit;
      padding: 7px;
      width: 100%;
    }
    textarea { resize: vertical; }
    .time-fields {
      display: grid;
      gap: 8px;
      grid-template-columns: 1fr 1fr 100px;
    }
    .errors {
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 5px;
      color: var(--danger);
      display: none;
      margin: 12px 0;
      padding: 9px;
    }
    .output summary { color: var(--muted); cursor: pointer; margin-bottom: 8px; }
    pre {
      background: #0f172a;
      border-radius: 5px;
      color: #e2e8f0;
      font-size: 11px;
      max-height: 250px;
      overflow: auto;
      padding: 10px;
    }
    @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <form name="mturk_form" method="post" id="mturk_form"
        action="https://www.mturk.com/mturk/externalSubmit">
    <input type="hidden" name="assignmentId" id="assignmentId" value="">
    <input type="hidden" name="annotation_json" id="annotation_json" value="">

    <h1>CTC Audio Annotation</h1>
    <div class="muted">Audio: __TASK_NAME__</div>

    <section class="card">
      <h2>File-level flags <span class="muted">(select at least one)</span></h2>
      <div class="flag-row" id="ctc-status"></div>
    </section>

    <section class="card">
      <h2>Stereo reference playback and timestamp annotation</h2>
      <div class="controls">
        <button id="play" type="button">Play full audio / Pause (Space)</button>
        <button id="play-selected" type="button">Play selected segment</button>
        <label class="choice"><input id="loop-selected" name="ui_loop_selected" type="checkbox" checked> Loop selected segment</label>
        <span id="time-display">0.00s / 0.00s</span>
        <label>Zoom
          <input id="zoom" name="ui_zoom" type="range" min="10" max="200" value="50">
        </label>
      </div>
      <div class="field">
        <label>Fallback audio player <span class="muted">(also confirms that MTurk can load the WAV)</span></label>
        <audio controls preload="metadata" style="width: 100%">
          <source src="__AUDIO_URL__" type="audio/wav">
        </audio>
      </div>
      <div id="wave-status" class="muted">Waveform status: waiting for custom JavaScript to run...</div>
      <div class="channel-key">
        <span class="left"><i class="dot" style="background: var(--left)"></i>Left (channel 0)</span>
        <span class="right"><i class="dot" style="background: var(--right)"></i>Right (channel 1)</span>
      </div>
      <div id="waveform"></div>
      <div class="controls" style="margin-top: 12px; margin-bottom: 0">
        <strong>Create segment:</strong>
        <label class="choice"><input type="radio" name="new_channel" value="0" checked> Left</label>
        <label class="choice"><input type="radio" name="new_channel" value="1"> Right</label>
        <span class="muted">Choose a channel, then drag on the waveform. Drag or resize regions to correct timestamps.</span>
      </div>
    </section>

    <section class="card">
      <h2>Selected segment annotation</h2>
      <div class="layout">
        <div>
          <div id="segments-list"></div>
        </div>
        <div id="editor">
          <div class="muted" id="empty-editor">Select a timestamp region to edit its annotation.</div>
          <fieldset id="segment-fields" disabled hidden>
            <div class="time-fields">
              <div class="field">
                <label for="start-time">Start (s)</label>
                <input type="text" id="start-time" name="ui_start_time" readonly>
              </div>
              <div class="field">
                <label for="end-time">End (s)</label>
                <input type="text" id="end-time" name="ui_end_time" readonly>
              </div>
              <div class="field">
                <label for="channel">Channel</label>
                <select id="channel" name="ui_channel">
                  <option value="0">Left</option>
                  <option value="1">Right</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label for="transcript">Transcript <span class="muted">(required)</span></label>
              <textarea id="transcript" name="ui_transcript" rows="3"></textarea>
            </div>
            <div class="field">
              <label>Segment-level flags</label>
              <div class="flag-row" id="segment-flags"></div>
            </div>
            <div class="field">
              <label for="note">Optional segment note</label>
              <textarea id="note" name="ui_note" rows="2"></textarea>
            </div>
            <button type="button" id="delete-segment" class="danger">Delete selected segment</button>
          </fieldset>
        </div>
      </div>
    </section>

    <div id="errors" class="errors"></div>
    <button id="submit" class="primary" type="submit">Submit annotation</button>
    <button id="download-json" type="button">Download JSON for local review</button>
    <span id="submit-mode" class="muted"></span>

    <details class="card output">
      <summary>Preview submitted annotation JSON</summary>
      <pre id="json-output"></pre>
    </details>
  </form>

  <script type="application/json" id="task-data">__TASK_JSON__</script>
  <script>
    (() => {
      const initial = JSON.parse(document.getElementById('task-data').textContent);
      const segmentById = new Map(initial.segments.map((segment) => [segment.id, {...segment}]));
      const regionById = new Map();
      let selectedId = null;
      let disableDragSelection = null;
      let playbackMode = 'full';

      const byId = (id) => document.getElementById(id);
      const statusElement = byId('ctc-status');
      const segmentFlagsElement = byId('segment-flags');
      const segmentFields = byId('segment-fields');
      const errorsElement = byId('errors');
      const annotationInput = byId('annotation_json');
      const form = byId('mturk_form');

      const fmt = (seconds) => `${Number(seconds || 0).toFixed(2)}s`;
      const round = (seconds) => Math.round(Number(seconds) * 100) / 100;
      const channelLabel = (channel) => Number(channel) === 0 ? 'Left' : 'Right';
      const color = (channel) => Number(channel) === 0
        ? 'rgba(31, 119, 180, 0.28)'
        : 'rgba(255, 127, 14, 0.28)';
      const escapeText = (text) => String(text).replace(/[&<>"']/g, (character) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[character]));

      function makeChecks(container, choices, name, checked) {
        container.innerHTML = choices.map((choice) => `
          <label class="choice">
            <input type="checkbox" name="${name}" value="${escapeText(choice)}"
              ${checked.includes(choice) ? 'checked' : ''}>
            ${escapeText(choice)}
          </label>`).join('');
      }

      makeChecks(statusElement, initial.choices.ctc_status, 'ctc_status', initial.ctc_status);
      makeChecks(segmentFlagsElement, initial.choices.segment_flags, 'segment_flags', []);

      function checkedValues(name) {
        return [...document.querySelectorAll(`input[name="${name}"]:checked`)]
          .map((input) => input.value);
      }

      function currentSegment() {
        return selectedId ? segmentById.get(selectedId) : null;
      }

      function sortedSegments() {
        return [...segmentById.values()].sort((a, b) =>
          a.start - b.start || a.end - b.end || a.channel - b.channel || a.id.localeCompare(b.id));
      }

      function payload() {
        return {
          schema_version: initial.schema_version,
          source: initial.source,
          ctc_status: checkedValues('ctc_status'),
          segments: sortedSegments().map((segment) => ({
            id: segment.id,
            channel: segment.channel,
            label: channelLabel(segment.channel),
            start: round(segment.start),
            end: round(segment.end),
            transcript: segment.transcript.trim(),
            flags: segment.flags,
            note: segment.note.trim()
          }))
        };
      }

      function syncOutput() {
        const serialized = JSON.stringify(payload());
        annotationInput.value = serialized;
        byId('json-output').textContent = JSON.stringify(payload(), null, 2);
      }

      function renderList() {
        const list = byId('segments-list');
        list.innerHTML = sortedSegments().map((segment) => `
          <button type="button" class="segment-button ${segment.id === selectedId ? 'selected' : ''}"
                  data-segment-id="${escapeText(segment.id)}">
            <strong class="${segment.channel === 0 ? 'left' : 'right'}">
              ${channelLabel(segment.channel)}
            </strong>
            ${fmt(segment.start)} - ${fmt(segment.end)}
            <span class="snippet">${escapeText(segment.transcript || '(transcript required)')}</span>
          </button>`).join('');
        list.querySelectorAll('[data-segment-id]').forEach((button) => {
          button.addEventListener('click', () => selectSegment(button.dataset.segmentId));
        });
      }

      function updateRegionContent(segment) {
        const region = regionById.get(segment.id);
        if (region) {
          region.setContent(`${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}`);
        }
      }

      function selectSegment(id) {
        selectedId = id;
        const segment = currentSegment();
        if (!segment) {
          segmentFields.hidden = true;
          segmentFields.disabled = true;
          byId('empty-editor').hidden = false;
          renderList();
          return;
        }
        segmentFields.hidden = false;
        segmentFields.disabled = false;
        byId('empty-editor').hidden = true;
        byId('start-time').value = fmt(segment.start);
        byId('end-time').value = fmt(segment.end);
        byId('channel').value = String(segment.channel);
        byId('transcript').value = segment.transcript;
        byId('note').value = segment.note;
        segmentFlagsElement.querySelectorAll('input').forEach((input) => {
          input.checked = segment.flags.includes(input.value);
        });
        renderList();
      }

      function saveEditor() {
        const segment = currentSegment();
        if (!segment) return;
        segment.transcript = byId('transcript').value;
        segment.note = byId('note').value;
        segment.flags = checkedValues('segment_flags');
        segment.channel = Number(byId('channel').value);
        segment.label = channelLabel(segment.channel);
        const region = regionById.get(segment.id);
        if (region) {
          region.setOptions({channelIdx: segment.channel, color: color(segment.channel)});
          updateRegionContent(segment);
        }
        renderList();
        syncOutput();
      }

      statusElement.addEventListener('change', syncOutput);
      byId('transcript').addEventListener('input', saveEditor);
      byId('note').addEventListener('input', saveEditor);
      byId('channel').addEventListener('change', saveEditor);
      segmentFlagsElement.addEventListener('change', saveEditor);

      byId('wave-status').textContent = 'Waveform status: custom JavaScript is running; checking waveform library...';
      renderList();
      syncOutput();

      if (!window.WaveSurfer || !WaveSurfer.Regions) {
        byId('wave-status').textContent = 'Waveform status: WaveSurfer library is unavailable in this page.';
        errorsElement.style.display = 'block';
        errorsElement.textContent =
          'Waveform library did not load. Check whether this MTurk preview permits the WaveSurfer CDN scripts.';
        return;
      }

      byId('wave-status').textContent = 'Waveform status: WaveSurfer loaded; loading WAV data...';
      const regions = WaveSurfer.Regions.create();
      const wave = WaveSurfer.create({
        container: '#waveform',
        url: initial.source.audio,
        height: 105,
        minPxPerSec: 50,
        autoScroll: true,
        cursorColor: '#111827',
        cursorWidth: 2,
        normalize: true,
        splitChannels: [
          {waveColor: '#93c5e6', progressColor: '#1f77b4'},
          {waveColor: '#fdc18d', progressColor: '#ff7f0e'}
        ],
        plugins: [regions]
      });

      function addVisualRegion(segment) {
        const region = regions.addRegion({
          id: segment.id,
          start: segment.start,
          end: segment.end,
          channelIdx: segment.channel,
          color: color(segment.channel),
          content: `${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}`,
          drag: true,
          resize: true,
          minLength: 0.05
        });
        regionById.set(region.id, region);
      }

      function activeNewChannel() {
        return Number(document.querySelector('input[name="new_channel"]:checked').value);
      }

      function configureDragSelection() {
        if (disableDragSelection) disableDragSelection();
        const channel = activeNewChannel();
        disableDragSelection = regions.enableDragSelection({
          channelIdx: channel,
          color: color(channel),
          drag: true,
          resize: true,
          minLength: 0.05
        });
      }

      document.querySelectorAll('input[name="new_channel"]').forEach((input) => {
        input.addEventListener('change', configureDragSelection);
      });

      wave.on('ready', () => {
        byId('wave-status').textContent = 'Waveform status: ready.';
        sortedSegments().forEach(addVisualRegion);
        configureDragSelection();
        selectSegment(sortedSegments().length ? sortedSegments()[0].id : null);
        byId('time-display').textContent = `${fmt(0)} / ${fmt(wave.getDuration())}`;
        syncOutput();
      });

      wave.on('timeupdate', (time) => {
        byId('time-display').textContent = `${fmt(time)} / ${fmt(wave.getDuration())}`;
        const segment = currentSegment();
        if (playbackMode === 'segment' && segment && time >= segment.end) {
          if (byId('loop-selected').checked) {
            wave.setTime(segment.start);
          } else {
            wave.pause();
          }
        }
      });
      wave.on('error', (error) => {
        byId('wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
        errorsElement.style.display = 'block';
        errorsElement.textContent = `Unable to load audio waveform: ${error}`;
      });
      byId('play').addEventListener('click', () => {
        playbackMode = 'full';
        wave.playPause();
      });
      byId('play-selected').addEventListener('click', () => {
        const segment = currentSegment();
        if (!segment) return;
        playbackMode = 'segment';
        wave.setTime(segment.start);
        wave.play();
      });
      byId('zoom').addEventListener('input', (event) => wave.zoom(Number(event.target.value)));
      document.addEventListener('keydown', (event) => {
        const tag = document.activeElement && document.activeElement.tagName;
        if (event.code === 'Space' && !['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(tag)) {
          event.preventDefault();
          playbackMode = 'full';
          wave.playPause();
        }
      });

      regions.on('region-created', (region) => {
        if (segmentById.has(region.id)) return;
        const channel = activeNewChannel();
        const segment = {
          id: region.id,
          channel,
          label: channelLabel(channel),
          start: round(region.start),
          end: round(region.end),
          transcript: '',
          flags: [],
          note: ''
        };
        segmentById.set(region.id, segment);
        regionById.set(region.id, region);
        region.setOptions({channelIdx: channel, color: color(channel)});
        updateRegionContent(segment);
        selectSegment(segment.id);
        syncOutput();
      });

      regions.on('region-updated', (region) => {
        const segment = segmentById.get(region.id);
        if (!segment) return;
        segment.start = round(region.start);
        segment.end = round(region.end);
        updateRegionContent(segment);
        selectSegment(segment.id);
        syncOutput();
      });

      regions.on('region-clicked', (region, event) => {
        event.stopPropagation();
        selectSegment(region.id);
      });

      regions.on('region-removed', (region) => {
        regionById.delete(region.id);
        segmentById.delete(region.id);
        if (selectedId === region.id) {
          selectedId = sortedSegments().length ? sortedSegments()[0].id : null;
        }
        selectSegment(selectedId);
        syncOutput();
      });

      byId('delete-segment').addEventListener('click', () => {
        const region = regionById.get(selectedId);
        if (region) region.remove();
      });

      function validationErrors() {
        const errors = [];
        if (!checkedValues('ctc_status').length) {
          errors.push('Select at least one file-level flag.');
        }
        if (!segmentById.size) {
          errors.push('Keep or create at least one timestamp segment.');
        }
        sortedSegments().forEach((segment, index) => {
          if (!segment.transcript.trim()) {
            errors.push(`Segment ${index + 1} (${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}) requires a transcript.`);
          }
          if (segment.end <= segment.start) {
            errors.push(`Segment ${index + 1} must have a positive duration.`);
          }
        });
        return errors;
      }

      if (typeof turkSetAssignmentID === 'function') {
        turkSetAssignmentID();
      }
      const query = new URLSearchParams(window.location.search);
      const submitHost = query.get('turkSubmitTo');
      if (submitHost) {
        form.action = `${submitHost}/mturk/externalSubmit`;
      }
      const assignmentId = query.get('assignmentId');
      const isAcceptedHit = assignmentId && assignmentId !== 'ASSIGNMENT_ID_NOT_AVAILABLE';
      if (!isAcceptedHit) {
        byId('submit').textContent = 'Validate annotation JSON';
        byId('submit-mode').textContent = 'Preview mode: submission to MTurk is disabled until the HIT is accepted.';
      }

      form.addEventListener('submit', (event) => {
        syncOutput();
        const errors = validationErrors();
        if (errors.length || !isAcceptedHit) event.preventDefault();
        if (errors.length) {
          errorsElement.style.display = 'block';
          errorsElement.innerHTML = errors.map((error) => escapeText(error)).join('<br>');
          return;
        }
        errorsElement.style.display = 'none';
        if (!isAcceptedHit) {
          byId('submit-mode').textContent = 'Annotation is valid. In an accepted MTurk HIT this button submits annotation_json.';
        }
      });

      byId('download-json').addEventListener('click', () => {
        syncOutput();
        const blob = new Blob([`${JSON.stringify(payload(), null, 2)}\n`], {
          type: 'application/json'
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `annotation_${initial.source.dataset}_${initial.source.task_index}.json`;
        link.click();
        URL.revokeObjectURL(url);
      });

    })();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
