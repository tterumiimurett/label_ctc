(() => {
  const state = {
    items: [],
    filtered: [],
    index: 0,
    wave: null,
    regions: null,
  };

  const byId = (id) => document.getElementById(id);
  const fmt = (seconds) => `${Number(seconds || 0).toFixed(2)}s`;
  const escapeText = (text) => String(text ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  const typeLabels = {
    word_phrase_confident: 'Word/phrase (confident)',
    word_phrase_unsure: 'Word/phrase (guess/unsure)',
    guiding_question: 'Guiding question',
  };

  function badge(text, kind = '') {
    return `<span class="badge ${kind}">${escapeText(text)}</span>`;
  }

  function yesNo(value) {
    if (value === true) return badge('Yes', 'good');
    if (value === false) return badge('No', 'neutral');
    return badge('Unanswered', 'bad');
  }

  function hasTranscriptEdits(item) {
    return Boolean(
      (item.corrected_interrupted_transcript || '').trim() ||
      (item.corrected_interrupting_transcript || '').trim()
    );
  }

  function itemLabel(item) {
    const worker = item.worker && item.worker.prolific_pid ? item.worker.prolific_pid : 'unknown worker';
    return `${item.task_id || item.candidate_id} · ${worker} · ${item.summary_label}`;
  }

  function applyFilter() {
    const filter = byId('filter').value;
    state.filtered = state.items.filter((item) => {
      if (filter === 'agree') return item.speaker_stuck === true;
      if (filter === 'disagree') return item.speaker_stuck === false;
      if (filter === 'stuck') return item.speaker_stuck === true;
      if (filter === 'not_stuck') return item.speaker_stuck === false;
      if (filter === 'unanswered') return item.speaker_stuck !== true && item.speaker_stuck !== false;
      if (filter === 'speaker_shift') return item.interrupter_becomes_main_speaker === true;
      if (filter === 'notes') return Boolean((item.note || '').trim());
      if (filter === 'transcript_edits') return hasTranscriptEdits(item);
      if (filter in typeLabels) return item.interruption_type === filter;
      return true;
    });
    renderSelect();
    renderItem(0);
  }

  function renderSelect() {
    byId('item-select').innerHTML = state.filtered.map((item, index) => (
      `<option value="${index}">${escapeText(itemLabel(item))}</option>`
    )).join('');
  }

  function renderLabelDetails(item) {
    const type = item.interruption_type ? typeLabels[item.interruption_type] || item.interruption_type : 'Not applicable';
    byId('label-details').innerHTML = `
      <div class="kv">
        <strong>Interrupted speaker stuck</strong><span>${yesNo(item.speaker_stuck)}</span>
        <strong>Interruption type</strong><span>${escapeText(type)}</span>
        <strong>Last stuck word timestamp</strong><span>${item.stall_time === null || item.stall_time === undefined ? 'Not applicable' : fmt(item.stall_time)}</span>
        <strong>Interrupter becomes main speaker</strong><span>${yesNo(item.interrupter_becomes_main_speaker)}</span>
      </div>
      <h3>Transcript corrections</h3>
      <p><b>Interrupted:</b><br>${escapeText(item.corrected_interrupted_transcript || 'No correction submitted.')}</p>
      <p><b>Interrupting:</b><br>${escapeText(item.corrected_interrupting_transcript || 'No correction submitted.')}</p>
      <h3>Note</h3>
      <p>${escapeText(item.note || 'No note submitted.')}</p>`;
  }

  function regionLine(region) {
    if (!region || region.start === undefined || region.end === undefined) {
      return '<span class="muted">Not available</span>';
    }
    return `${fmt(region.start)}-${fmt(region.end)}<br><span class="muted">${escapeText(region.transcript || '')}</span>`;
  }

  function renderUtteranceDetails(item) {
    const interrupted = item.regions && item.regions.interrupted;
    const interrupting = item.regions && item.regions.interrupting;
    byId('utterance-details').innerHTML = `
      <article class="panel">
        <h3>Interrupted utterance</h3>
        <p>${regionLine(interrupted)}</p>
      </article>
      <article class="panel">
        <h3>Interrupting utterance</h3>
        <p>${regionLine(interrupting)}</p>
      </article>
      <article class="panel">
        <h3>Candidate key</h3>
        <p class="muted">${escapeText(item.prelabel_candidate_key || '')}</p>
      </article>`;
  }

  function renderMetadata(item) {
    byId('metadata').innerHTML = `
      <strong>Submission file</strong><span>${escapeText(item.submission_file)}</span>
      <strong>Submitted at</strong><span>${escapeText(item.submitted_at || '')}</span>
      <strong>Worker</strong><span>${escapeText((item.worker || {}).prolific_pid || '')}</span>
      <strong>Study</strong><span>${escapeText((item.worker || {}).study_id || '')}</span>
      <strong>Session</strong><span>${escapeText((item.worker || {}).session_id || '')}</span>
      <strong>Bundle</strong><span>${escapeText((item.assignment || {}).bundle_id || '')}</span>
      <strong>Schema</strong><span>${escapeText(item.schema_version || '')}</span>`;
  }

  function destroyWave() {
    if (state.wave) state.wave.destroy();
    state.wave = null;
    state.regions = null;
    byId('waveform').innerHTML = '';
  }

  function addRegion(id, region, channelIdx, color, content) {
    if (!state.regions || !region) return;
    const start = Number(region.start);
    const end = Number(region.end);
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

  function addStallMarker(item) {
    if (!state.regions || item.stall_time === null || item.stall_time === undefined) return;
    const start = Number(item.stall_time);
    const duration = state.wave ? state.wave.getDuration() : item.duration;
    if (!Number.isFinite(start)) return;
    const width = 0.08;
    state.regions.addRegion({
      id: 'submitted-stall-marker',
      start,
      end: Math.min(start + width, duration || start + width),
      color: 'rgba(220, 38, 38, 0.75)',
      content: 'Stuck',
      drag: false,
      resize: false,
    });
  }

  function wireWave(item) {
    destroyWave();
    if (!window.WaveSurfer || !WaveSurfer.Regions) {
      byId('wave-status').textContent = 'Waveform status: WaveSurfer library is unavailable.';
      return;
    }
    byId('wave-status').textContent = 'Waveform status: loading WAV data...';
    const regions = WaveSurfer.Regions.create();
    const wave = WaveSurfer.create({
      container: '#waveform',
      media: byId('audio'),
      url: item.audio_url,
      height: 105,
      minPxPerSec: 50,
      autoScroll: true,
      cursorWidth: 1,
      normalize: true,
      splitChannels: [
        {waveColor: '#93c5e6', progressColor: '#1f77b4'},
        {waveColor: '#fdc18d', progressColor: '#ff7f0e'},
      ],
      plugins: [regions],
    });
    state.wave = wave;
    state.regions = regions;
    wave.on('ready', () => {
      byId('wave-status').textContent = 'Waveform status: ready.';
      addRegion(
        'interrupted',
        item.regions && item.regions.interrupted,
        0,
        'rgba(31, 119, 180, 0.28)',
        'Interrupted',
      );
      addRegion(
        'interrupting',
        item.regions && item.regions.interrupting,
        1,
        'rgba(255, 127, 14, 0.28)',
        'Interrupting',
      );
      addStallMarker(item);
    });
    wave.on('error', (error) => {
      byId('wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
    });
  }

  function renderItem(index) {
    if (!state.filtered.length) {
      destroyWave();
      byId('task-title').textContent = 'No matching submissions';
      byId('task-meta').textContent = '';
      byId('position').textContent = '0 of 0';
      byId('label-details').innerHTML = '<p class="muted">No annotations match this filter.</p>';
      byId('utterance-details').innerHTML = '';
      byId('metadata').innerHTML = '';
      return;
    }
    state.index = Math.max(0, Math.min(index, state.filtered.length - 1));
    const item = state.filtered[state.index];
    byId('task-title').textContent = item.task_id || item.candidate_id || 'Submission';
    byId('task-meta').textContent =
      `${item.summary_label} · ${item.submission_file} · task ${item.task_index}`;
    byId('position').textContent = `${state.index + 1} of ${state.filtered.length}`;
    byId('prev').disabled = state.index === 0;
    byId('next').disabled = state.index === state.filtered.length - 1;
    byId('item-select').value = String(state.index);
    byId('audio').src = item.audio_url || '';
    byId('audio-url').innerHTML = item.audio_url
      ? `Audio URL: <a href="${escapeText(item.audio_url)}" target="_blank" rel="noopener">${escapeText(item.audio_url)}</a>`
      : 'Audio URL: not available';
    renderLabelDetails(item);
    renderUtteranceDetails(item);
    renderMetadata(item);
    wireWave(item);
  }

  async function init() {
    const response = await fetch('/api/review');
    const data = await response.json();
    if (!response.ok || data.status !== 'ok') {
      byId('message').textContent = 'Unable to load submitted annotations.';
      byId('loading').classList.add('errors');
      return;
    }
    state.items = data.items || [];
    state.filtered = state.items;
    byId('summary').textContent =
      `${data.summary.items} submitted task annotations from ${data.summary.submission_files} submission files`;
    byId('loading').hidden = true;
    byId('app').hidden = false;
    renderSelect();
    renderItem(0);
  }

  byId('prev').addEventListener('click', () => renderItem(state.index - 1));
  byId('next').addEventListener('click', () => renderItem(state.index + 1));
  byId('filter').addEventListener('change', applyFilter);
  byId('item-select').addEventListener('change', (event) => {
    renderItem(Number(event.target.value));
  });

  init().catch((error) => {
    byId('message').textContent = `Unable to load review app: ${error}`;
    byId('loading').classList.add('errors');
  });
})();
