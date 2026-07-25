(() => {
  const state = {
    items: [],
    summary: null,
    filtered: [],
    index: 0,
    wave: null,
    regions: null,
  };

  const byId = (id) => document.getElementById(id);
  const escapeText = (text) => String(text ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function fmt(value, digits = 3) {
    if (value === null || value === undefined || value === '') {
      return 'Not available';
    }
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(digits)}s` : 'Not available';
  }

  function boolText(value) {
    if (value === true) return 'Yes';
    if (value === false) return 'No';
    return 'Not available';
  }

  function current() {
    return state.filtered[state.index];
  }

  function itemLabel(item) {
    return `line ${item.line_number} · ${item.category_label} · ${item.interaction_id}`;
  }

  function setFilterLabels() {
    const counts = state.summary.category_counts;
    for (const option of byId('filter').options) {
      const base = option.textContent.replace(/\s+\(\d+\)$/, '');
      let count = state.summary.rows;
      if (option.value === 'subclassed') count = state.summary.subclassed_ctc_rows;
      else if (option.value !== 'all') count = counts[option.value] || 0;
      option.textContent = `${base} (${count})`;
    }
  }

  function applyFilter() {
    const category = byId('filter').value;
    const query = byId('search').value.trim().toLowerCase();
    state.filtered = state.items.filter((item) => {
      const categoryMatch = category === 'all'
        || (category === 'subclassed'
          && ['stuck_word', 'stuck_guide', 'not_stuck'].includes(item.category))
        || item.category === category;
      if (!categoryMatch) return false;
      if (!query) return true;
      const context = item.context || {};
      return [
        item.interaction_id,
        item.candidate_key,
        context.main_before_interrupt,
        context.interrupter_after_start,
        context.pred_completion_target,
      ].join('\n').toLowerCase().includes(query);
    });
    renderSelect();
    renderItem(0);
  }

  function renderSelect() {
    byId('item-select').innerHTML = state.filtered.map((item, index) => (
      `<option value="${index}">${escapeText(itemLabel(item))}</option>`
    )).join('');
  }

  function renderDatasetNote() {
    const counts = state.summary.category_counts;
    const note = byId('dataset-note');
    const noGuide = counts.stuck_guide === 0;
    const missingAudio = state.summary.audio_matched < state.summary.rows;
    note.classList.toggle('warning', noGuide || missingAudio);
    note.innerHTML = `
      <strong>Actual labels in this file:</strong>
      Stuck word ${counts.stuck_word},
      Stuck guide ${counts.stuck_guide},
      Not stuck ${counts.not_stuck} (raw label: <code>unstuck</code>),
      and Not CTC ${counts.not_ctc}.
      ${noGuide ? '<br><strong>Note:</strong> this JSONL currently contains no Stuck guide row.' : ''}
      ${missingAudio ? `<br><strong>Audio:</strong> matched ${state.summary.audio_matched}/${state.summary.rows} rows. Unmatched rows still expose classifications, timestamps, context, and raw JSON.` : ''}
      <div class="muted">${escapeText(state.summary.jsonl_path)}</div>`;
  }

  function renderClassification(item) {
    const value = item.classification || {};
    byId('classification').innerHTML = `
      <strong>Displayed category</strong><span>${escapeText(item.category_label)}</span>
      <strong>Raw subclass</strong><span>${escapeText(value.subclass ?? 'null')}</span>
      <strong>Subclass status</strong><span>${escapeText(value.subclass_status ?? 'null')}</span>
      <strong>Speaker stuck</strong><span>${escapeText(boolText(value.subclass_is_stuck))}</span>
      <strong>Gap</strong><span>${fmt(value.gap_seconds)} / ${value.gap_ms ?? 'N/A'} ms</span>
      <strong>Threshold</strong><span>${value.threshold_ms ?? 'N/A'} ms</span>
      <strong>LLM kind</strong><span>${escapeText(value.llm_kind ?? 'null')}</span>
      <strong>LLM confidence</strong><span>${escapeText(value.llm_confidence ?? 'null')}</span>
      <strong>LLM backend/model</strong><span>${escapeText(value.llm_backend ?? 'N/A')} / ${escapeText(value.llm_model ?? 'N/A')}</span>
      <strong>Subclass error</strong><span>${escapeText(boolText(value.error))}${value.error_message ? ` · ${escapeText(value.error_message)}` : ''}</span>`;
    byId('classifier-reasoning').textContent =
      value.llm_reasoning || 'No subclass LLM reasoning (typically threshold-classified Not stuck or a non-CTC row).';
  }

  function renderTimestamps(item) {
    const timeline = item.timeline || {};
    const mainWord = timeline.main_last_word;
    const firstWord = timeline.interrupter_first_word;
    byId('timestamps').innerHTML = `
      <strong>Audio clip</strong><span>${fmt(item.clip.absolute_start)}–${fmt(item.clip.absolute_end)} absolute · 0–${fmt(item.clip.duration)} relative</span>
      <strong>Main last word</strong><span>${mainWord ? `${escapeText(mainWord.text)} · ${fmt(mainWord.absolute_start)}–${fmt(mainWord.absolute_end)} absolute · ${fmt(mainWord.relative_start)}–${fmt(mainWord.relative_end)} relative` : 'Not available'}</span>
      <strong>Main last word end</strong><span>${fmt(timeline.main_last_word_end_absolute)} absolute · ${fmt(timeline.main_last_word_end_relative)} relative</span>
      <strong>Interrupter first word</strong><span>${firstWord ? `${escapeText(firstWord.text)} · ${fmt(firstWord.absolute_start)}–${fmt(firstWord.absolute_end)} absolute · ${fmt(firstWord.relative_start)}–${fmt(firstWord.relative_end)} relative` : 'Not available'}</span>
      <strong>Interrupter first word start</strong><span>${fmt(timeline.interrupter_first_word_start_absolute)} absolute · ${fmt(timeline.interrupter_first_word_start_relative)} relative</span>
      <strong>Interrupter start</strong><span>${fmt(timeline.interrupter_start_absolute)} absolute · ${fmt(timeline.interrupter_start_relative)} relative</span>
      <strong>Computed gap</strong><span>${fmt(item.classification.gap_seconds)}</span>`;
  }

  function contextBlock(title, text) {
    return `<h3>${escapeText(title)}</h3><p>${escapeText(text || 'Not available')}</p>`;
  }

  function renderContext(item) {
    const context = item.context || {};
    byId('context').innerHTML = [
      contextBlock('Main speaker before interruption', context.main_before_interrupt),
      contextBlock('Interrupter after start', context.interrupter_after_start),
      contextBlock('Predicted completion target', context.pred_completion_target),
      contextBlock('CTC prediction reasoning', context.pred_reasoning),
      contextBlock('Audio verification evidence', context.audio_evidence),
      contextBlock('Text verification evidence', context.text_evidence),
    ].join('');
  }

  function renderSourceMapping(item) {
    const match = item.audio_match;
    byId('source-mapping').innerHTML = match ? `
      <strong>Matched task</strong><span>${escapeText(match.task_id)}</span>
      <strong>Channel 0 / left</strong><span>${escapeText(match.left_speaker)}${match.left_speaker === item.speakers.main ? ' · main speaker' : ''}</span>
      <strong>Channel 1 / right</strong><span>${escapeText(match.right_speaker)}${match.right_speaker === item.speakers.interrupter ? ' · interrupter' : ''}</span>
      <strong>Main speaker</strong><span>${escapeText(item.speakers.main)}</span>
      <strong>Interrupter</strong><span>${escapeText(item.speakers.interrupter)}</span>
      <strong>Centisecond match delta</strong><span>start ${match.match_start_delta_centiseconds}, end ${match.match_end_delta_centiseconds}</span>
      <strong>Source path</strong><span class="muted">${escapeText(match.path_seg)}</span>` :
      '<span class="errors">No matching audio task was found.</span>';
  }

  function renderDialogue(item) {
    const rows = (item.context.dialogue || []).map((turn) => `
      <div class="dialogue-row">
        <span class="speaker">${escapeText(turn.speaker)}</span>
        <span class="time">${fmt(turn.relative_start)}–${fmt(turn.relative_end)}</span>
        <span>${escapeText(turn.utterance)}</span>
      </div>`).join('');
    byId('dialogue').innerHTML = rows || '<p class="muted">No dialogue turns in this row.</p>';
  }

  function destroyWave() {
    if (state.wave) state.wave.destroy();
    state.wave = null;
    state.regions = null;
    byId('waveform').innerHTML = '';
  }

  function addRegion(id, region, channelIdx, color, content) {
    if (!state.regions || !region) return;
    const start = Number(region.relative_start);
    const end = Number(region.relative_end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    state.regions.addRegion({
      id,
      start,
      end,
      channelIdx,
      color,
      content,
      drag: false,
      resize: false,
    });
  }

  function addMarker(id, timestamp, color, content) {
    if (!state.regions) return;
    if (timestamp === null || timestamp === undefined || timestamp === '') return;
    const start = Number(timestamp);
    const duration = state.wave ? state.wave.getDuration() : 0;
    if (!Number.isFinite(start) || start < 0 || (duration && start > duration)) return;
    const width = 0.06;
    state.regions.addRegion({
      id,
      start,
      end: Math.min(start + width, duration || start + width),
      color,
      content,
      drag: false,
      resize: false,
    });
  }

  function wireWave(item) {
    destroyWave();
    if (!item.audio_url) {
      byId('wave-status').textContent = 'Waveform status: no matched audio URL.';
      return;
    }
    if (!window.WaveSurfer || !WaveSurfer.Regions) {
      byId('wave-status').textContent = 'Waveform status: vendored WaveSurfer library is unavailable.';
      return;
    }
    byId('wave-status').textContent = 'Waveform status: loading WAV data...';
    const regions = WaveSurfer.Regions.create();
    const wave = WaveSurfer.create({
      container: '#waveform',
      media: byId('audio'),
      url: item.audio_url,
      height: 105,
      minPxPerSec: 45,
      autoScroll: true,
      cursorWidth: 1,
      normalize: true,
      splitChannels: [
        {waveColor: '#93c5e6', progressColor: '#1f77b4'},
        {waveColor: '#fdba74', progressColor: '#f97316'},
      ],
      plugins: [regions],
    });
    state.wave = wave;
    state.regions = regions;
    wave.on('ready', () => {
      byId('wave-status').textContent = 'Waveform status: ready.';
      addRegion(
        'interrupted',
        item.timeline.interrupted_region,
        0,
        'rgba(31, 119, 180, 0.24)',
        'Interrupted',
      );
      addRegion(
        'interrupting',
        item.timeline.interrupting_region,
        1,
        'rgba(249, 115, 22, 0.24)',
        'Interrupter',
      );
      addRegion(
        'main-last-word',
        item.timeline.main_last_word,
        0,
        'rgba(220, 38, 38, 0.38)',
        `Last: ${(item.timeline.main_last_word || {}).text || ''}`,
      );
      addRegion(
        'interrupter-first-word',
        item.timeline.interrupter_first_word,
        1,
        'rgba(124, 58, 237, 0.35)',
        `First: ${(item.timeline.interrupter_first_word || {}).text || ''}`,
      );
      addMarker(
        'main-last-word-end',
        item.timeline.main_last_word_end_relative,
        'rgba(220, 38, 38, 0.85)',
        'Last word end',
      );
      addMarker(
        'interrupter-first-word-start',
        item.timeline.interrupter_first_word_start_relative,
        'rgba(124, 58, 237, 0.85)',
        'First word start',
      );
    });
    wave.on('error', (error) => {
      byId('wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
    });
  }

  function renderItem(index) {
    if (!state.filtered.length) {
      destroyWave();
      byId('task-title').textContent = 'No matching JSONL rows';
      byId('task-meta').textContent = '';
      byId('position').textContent = '0 of 0';
      byId('category-badge').textContent = '';
      byId('classification').innerHTML = '<span class="muted">Change the filter or search.</span>';
      byId('timestamps').innerHTML = '';
      byId('context').innerHTML = '';
      byId('source-mapping').innerHTML = '';
      byId('dialogue').innerHTML = '';
      byId('raw-json').textContent = '';
      byId('audio').removeAttribute('src');
      byId('audio-url').textContent = '';
      return;
    }
    state.index = Math.max(0, Math.min(index, state.filtered.length - 1));
    const item = current();
    byId('task-title').textContent = item.interaction_id || 'Candidate';
    byId('task-meta').textContent =
      `JSONL line ${item.line_number} · ${item.candidate_key}`;
    byId('position').textContent = `${state.index + 1} of ${state.filtered.length}`;
    byId('prev').disabled = state.index === 0;
    byId('next').disabled = state.index === state.filtered.length - 1;
    byId('item-select').value = String(state.index);
    byId('category-badge').textContent = item.category_label;
    byId('category-badge').className = `badge ${item.category}`;
    byId('audio').src = item.audio_url || '';
    byId('audio-url').innerHTML = item.audio_url
      ? `Audio URL: <a href="${escapeText(item.audio_url)}" target="_blank" rel="noopener">${escapeText(item.audio_url)}</a>`
      : 'Audio URL: not available';
    renderClassification(item);
    renderTimestamps(item);
    renderContext(item);
    renderSourceMapping(item);
    renderDialogue(item);
    byId('raw-json').textContent = JSON.stringify(item.raw, null, 2);
    wireWave(item);
  }

  async function init() {
    const response = await fetch('/api/preview');
    const data = await response.json();
    if (!response.ok || data.status !== 'ok') {
      byId('message').textContent = 'Unable to load JSONL preview data.';
      byId('loading').classList.add('errors');
      return;
    }
    state.items = data.items || [];
    state.summary = data.summary;
    state.filtered = state.items.filter((item) => (
      ['stuck_word', 'stuck_guide', 'not_stuck'].includes(item.category)
    ));
    byId('summary').textContent =
      `${data.summary.rows} JSONL rows · ${data.summary.subclassed_ctc_rows} subclassed CTC rows · ${data.summary.audio_matched} audio matches`;
    byId('loading').hidden = true;
    byId('app').hidden = false;
    setFilterLabels();
    renderDatasetNote();
    renderSelect();
    renderItem(0);
  }

  byId('prev').addEventListener('click', () => renderItem(state.index - 1));
  byId('next').addEventListener('click', () => renderItem(state.index + 1));
  byId('filter').addEventListener('change', applyFilter);
  byId('search').addEventListener('input', applyFilter);
  byId('item-select').addEventListener('change', (event) => {
    renderItem(Number(event.target.value));
  });

  init().catch((error) => {
    byId('message').textContent = `Unable to load preview app: ${error}`;
    byId('loading').classList.add('errors');
  });
})();
