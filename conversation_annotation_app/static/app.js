(() => {
  const state = {
    assignment: null,
    worker: null,
    tasks: [],
    index: 0,
    taskState: [],
    wave: null,
    regions: null,
    regionById: new Map(),
    selectedId: null,
    disableDragSelection: null,
    playbackMode: 'full',
    startedAt: new Date().toISOString(),
  };

  const byId = (id) => document.getElementById(id);
  const fmt = (seconds) => `${Number(seconds || 0).toFixed(2)}s`;
  const round = (seconds) => Math.round(Number(seconds) * 100) / 100;
  const channelLabel = (channel) => Number(channel) === 0 ? 'Left' : 'Right';
  const channelColor = (channel) => Number(channel) === 0
    ? 'rgba(31, 119, 180, 0.28)'
    : 'rgba(255, 127, 14, 0.28)';
  const escapeText = (text) => String(text).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function checkedValues(name) {
    return [...document.querySelectorAll(`input[name="${name}"]:checked`)]
      .map((input) => input.value);
  }

  function taskState() {
    return state.taskState[state.index];
  }

  function segments() {
    return taskState().segments;
  }

  function sortedSegments() {
    return [...segments().values()].sort((a, b) =>
      a.start - b.start || a.end - b.end || a.channel - b.channel || a.id.localeCompare(b.id));
  }

  function selectedSegment() {
    return state.selectedId ? segments().get(state.selectedId) : null;
  }

  function makeChecks(container, choices, name, checked) {
    container.innerHTML = choices.map((choice) => `
      <label class="choice">
        <input type="checkbox" name="${name}" value="${escapeText(choice)}"
          ${checked.includes(choice) ? 'checked' : ''}>
        ${escapeText(choice)}
      </label>`).join('');
  }

  function makeOptions(select, choices, value) {
    select.innerHTML = choices.map((choice) =>
      `<option value="${escapeText(choice)}" ${choice === value ? 'selected' : ''}>${escapeText(choice)}</option>`
    ).join('');
  }

  async function init() {
    const query = params();
    const required = ['PROLIFIC_PID', 'STUDY_ID', 'SESSION_ID'];
    const missing = required.filter((key) => !query.get(key));
    if (missing.length) {
      showFatal(`Missing required Prolific URL parameters: ${missing.join(', ')}.`);
      return;
    }
    byId('worker-line').textContent =
      `Participant ${query.get('PROLIFIC_PID')} · Session ${query.get('SESSION_ID')}`;
    const response = await fetch(`/api/assign?${query.toString()}`);
    const assignment = await response.json();
    if (!response.ok || assignment.status !== 'ok') {
      showFatal((assignment.errors || ['Unable to assign tasks.']).join(' '));
      return;
    }
    state.assignment = assignment.assignment;
    state.worker = assignment.worker;
    state.completionUrl = assignment.completion_url;
    state.tasks = assignment.tasks;
    state.taskState = state.tasks.map(normalizeTask);
    byId('loading-card').hidden = true;
    byId('annotation-form').hidden = false;
    renderTask(0);
  }

  function showFatal(message) {
    byId('loading-message').textContent = message;
    byId('loading-card').classList.add('errors');
  }

  function normalizeTask(task) {
    return {
      task,
      fileLevel: {
        target_status: [...(task.ctc_status || [])],
        audio_quality: 'usable',
        transcript_quality: 'needs_minor_correction',
      },
      segments: new Map(task.segments.map((segment) => [
        segment.id,
        {
          ...segment,
          flags: [...(segment.flags || [])],
          note: segment.note || '',
        },
      ])),
      started_at: new Date().toISOString(),
    };
  }

  function renderTask(index) {
    saveEditor();
    state.index = index;
    state.selectedId = null;
    destroyWave();

    const current = taskState();
    const task = current.task;
    byId('task-title').textContent =
      `${task.task.task_id} (${index + 1} of ${state.tasks.length})`;
    byId('task-audio').textContent = task.task.audio_url;
    byId('progress-line').textContent = `Bundle ${state.assignment.bundle_id}`;
    byId('prev-task').disabled = index === 0;
    byId('next-task').disabled = index === state.tasks.length - 1;

    makeChecks(byId('target-status'), task.choices.ctc_status, 'target_status', current.fileLevel.target_status);
    makeChecks(byId('segment-flags'), task.choices.segment_flags, 'segment_flags', []);
    makeOptions(byId('audio-quality'), task.choices.audio_quality, current.fileLevel.audio_quality);
    makeOptions(byId('transcript-quality'), task.choices.transcript_quality, current.fileLevel.transcript_quality);
    byId('fallback-audio').src = task.task.audio_url;

    renderList();
    wireWave(task.task.audio_url);
    selectSegment(sortedSegments().length ? sortedSegments()[0].id : null);
    syncOutput();
  }

  function destroyWave() {
    if (state.disableDragSelection) state.disableDragSelection();
    state.disableDragSelection = null;
    state.regionById.clear();
    if (state.wave) state.wave.destroy();
    state.wave = null;
    state.regions = null;
    byId('waveform').innerHTML = '';
  }

  function renderList() {
    const list = byId('segments-list');
    list.innerHTML = sortedSegments().map((segment) => `
      <button type="button" class="segment-button ${segment.id === state.selectedId ? 'selected' : ''}"
              data-segment-id="${escapeText(segment.id)}">
        <strong class="${segment.channel === 0 ? 'left' : 'right'}">${channelLabel(segment.channel)}</strong>
        ${fmt(segment.start)} - ${fmt(segment.end)}
        <span class="snippet">${escapeText(segment.transcript || '(transcript required)')}</span>
      </button>`).join('');
    list.querySelectorAll('[data-segment-id]').forEach((button) => {
      button.addEventListener('click', () => selectSegment(button.dataset.segmentId));
    });
  }

  function selectSegment(id) {
    state.selectedId = id;
    const segment = selectedSegment();
    if (!segment) {
      byId('segment-fields').hidden = true;
      byId('segment-fields').disabled = true;
      byId('empty-editor').hidden = false;
      renderList();
      return;
    }
    byId('segment-fields').hidden = false;
    byId('segment-fields').disabled = false;
    byId('empty-editor').hidden = true;
    byId('start-time').value = fmt(segment.start);
    byId('end-time').value = fmt(segment.end);
    byId('channel').value = String(segment.channel);
    byId('transcript').value = segment.transcript;
    byId('note').value = segment.note;
    byId('segment-flags').querySelectorAll('input').forEach((input) => {
      input.checked = segment.flags.includes(input.value);
    });
    renderList();
  }

  function saveEditor(shouldSync = true) {
    const segment = selectedSegment();
    if (!segment) return;
    segment.transcript = byId('transcript').value;
    segment.note = byId('note').value;
    segment.flags = checkedValues('segment_flags');
    segment.channel = Number(byId('channel').value);
    segment.label = channelLabel(segment.channel);
    const region = state.regionById.get(segment.id);
    if (region) {
      region.setOptions({channelIdx: segment.channel, color: channelColor(segment.channel)});
      region.setContent(`${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}`);
    }
    renderList();
    if (shouldSync) syncOutput();
  }

  function wireWave(audioUrl) {
    if (!window.WaveSurfer || !WaveSurfer.Regions) {
      byId('wave-status').textContent = 'Waveform status: WaveSurfer library is unavailable.';
      return;
    }
    byId('wave-status').textContent = 'Waveform status: loading WAV data...';
    const regions = WaveSurfer.Regions.create();
    const wave = WaveSurfer.create({
      container: '#waveform',
      url: audioUrl,
      height: 105,
      minPxPerSec: 50,
      autoScroll: true,
      cursorColor: '#111827',
      cursorWidth: 2,
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
      sortedSegments().forEach(addVisualRegion);
      configureDragSelection();
      byId('time-display').textContent = `${fmt(0)} / ${fmt(wave.getDuration())}`;
    });
    wave.on('timeupdate', (time) => {
      byId('time-display').textContent = `${fmt(time)} / ${fmt(wave.getDuration())}`;
      const segment = selectedSegment();
      if (state.playbackMode === 'segment' && segment && time >= segment.end) {
        if (byId('loop-selected').checked) wave.setTime(segment.start);
        else wave.pause();
      }
    });
    wave.on('error', (error) => {
      byId('wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
    });
    regions.on('region-created', onRegionCreated);
    regions.on('region-updated', onRegionUpdated);
    regions.on('region-clicked', (region, event) => {
      event.stopPropagation();
      selectSegment(region.id);
    });
    regions.on('region-removed', (region) => {
      state.regionById.delete(region.id);
      segments().delete(region.id);
      if (state.selectedId === region.id) {
        state.selectedId = sortedSegments().length ? sortedSegments()[0].id : null;
      }
      selectSegment(state.selectedId);
      syncOutput();
    });
  }

  function addVisualRegion(segment) {
    const region = state.regions.addRegion({
      id: segment.id,
      start: segment.start,
      end: segment.end,
      channelIdx: segment.channel,
      color: channelColor(segment.channel),
      content: `${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}`,
      drag: true,
      resize: true,
      minLength: 0.05,
    });
    state.regionById.set(region.id, region);
  }

  function activeNewChannel() {
    return Number(document.querySelector('input[name="new_channel"]:checked').value);
  }

  function configureDragSelection() {
    if (!state.regions) return;
    if (state.disableDragSelection) state.disableDragSelection();
    const channel = activeNewChannel();
    state.disableDragSelection = state.regions.enableDragSelection({
      channelIdx: channel,
      color: channelColor(channel),
      drag: true,
      resize: true,
      minLength: 0.05,
    });
  }

  function onRegionCreated(region) {
    if (segments().has(region.id)) return;
    const channel = activeNewChannel();
    const segment = {
      id: region.id,
      channel,
      label: channelLabel(channel),
      start: round(region.start),
      end: round(region.end),
      transcript: '',
      flags: [],
      note: '',
    };
    segments().set(region.id, segment);
    state.regionById.set(region.id, region);
    region.setOptions({channelIdx: channel, color: channelColor(channel)});
    region.setContent(`${channelLabel(channel)} ${fmt(segment.start)}-${fmt(segment.end)}`);
    selectSegment(segment.id);
    syncOutput();
  }

  function onRegionUpdated(region) {
    const segment = segments().get(region.id);
    if (!segment) return;
    segment.start = round(region.start);
    segment.end = round(region.end);
    region.setContent(`${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)}`);
    selectSegment(region.id);
    syncOutput();
  }

  function saveFileLevel(shouldSync = true) {
    const current = taskState();
    current.fileLevel.target_status = checkedValues('target_status');
    current.fileLevel.audio_quality = byId('audio-quality').value;
    current.fileLevel.transcript_quality = byId('transcript-quality').value;
    if (shouldSync) syncOutput();
  }

  function taskPayload(current) {
    return {
      task_id: current.task.task.task_id,
      audio_url: current.task.task.audio_url,
      dataset: current.task.task.dataset,
      bundle_id: state.assignment.bundle_id,
      file_level: current.fileLevel,
      segments: [...current.segments.values()].map((segment) => ({
        segment_id: segment.id,
        channel: segment.channel,
        speaker: channelLabel(segment.channel),
        start: round(segment.start),
        end: round(segment.end),
        transcript: segment.transcript.trim(),
        flags: segment.flags,
        note: segment.note.trim(),
      })),
      ui_metadata: {
        started_at: current.started_at,
        submitted_at: new Date().toISOString(),
      },
    };
  }

  function submissionPayload() {
    saveEditor(false);
    saveFileLevel(false);
    return {
      schema_version: 'conversation-annotation-v2',
      worker: state.worker,
      assignment: state.assignment,
      tasks: state.taskState.map(taskPayload),
      ui_metadata: {
        started_at: state.startedAt,
        submitted_at: new Date().toISOString(),
      },
    };
  }

  function syncOutput() {
    if (!state.assignment) return;
    byId('json-output').textContent = JSON.stringify(submissionPayload(), null, 2);
  }

  function validationErrors() {
    const payload = submissionPayload();
    const errors = [];
    let firstInvalidTask = null;
    payload.tasks.forEach((task, taskIndex) => {
      if (!task.file_level.target_status.length) {
        errors.push(`Task ${taskIndex + 1}: select at least one target status in File-level labels.`);
        if (firstInvalidTask === null) firstInvalidTask = taskIndex;
      }
      task.segments.forEach((segment, segmentIndex) => {
        if (!segment.transcript) {
          errors.push(`Task ${taskIndex + 1}, segment ${segmentIndex + 1}: transcript is required.`);
          if (firstInvalidTask === null) firstInvalidTask = taskIndex;
        }
        if (segment.end <= segment.start) {
          errors.push(`Task ${taskIndex + 1}, segment ${segmentIndex + 1}: start must be before end.`);
          if (firstInvalidTask === null) firstInvalidTask = taskIndex;
        }
      });
    });
    return {errors, firstInvalidTask};
  }

  async function submit(event) {
    event.preventDefault();
    const {errors, firstInvalidTask} = validationErrors();
    if (errors.length) {
      if (firstInvalidTask !== null && firstInvalidTask !== state.index) {
        renderTask(firstInvalidTask);
      }
      byId('errors').style.display = 'block';
      byId('errors').innerHTML = errors.map(escapeText).join('<br>');
      return;
    }
    byId('errors').style.display = 'none';
    byId('submit').disabled = true;
    byId('save-status').textContent = 'Saving...';
    const response = await fetch('/api/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(submissionPayload()),
    });
    const result = await response.json();
    if (!response.ok || result.status !== 'ok') {
      byId('submit').disabled = false;
      byId('save-status').textContent = 'Save failed.';
      byId('errors').style.display = 'block';
      byId('errors').innerHTML = (result.errors || ['Server rejected submission.']).map(escapeText).join('<br>');
      return;
    }
    byId('save-status').textContent = 'Saved. Redirecting to Prolific...';
    window.location.href = result.completion_url;
  }

  function downloadJson() {
    const blob = new Blob([`${JSON.stringify(submissionPayload(), null, 2)}\n`], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `annotation_${state.worker.session_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  byId('prev-task').addEventListener('click', () => renderTask(Math.max(0, state.index - 1)));
  byId('next-task').addEventListener('click', () => renderTask(Math.min(state.tasks.length - 1, state.index + 1)));
  byId('target-status').addEventListener('change', saveFileLevel);
  byId('audio-quality').addEventListener('change', saveFileLevel);
  byId('transcript-quality').addEventListener('change', saveFileLevel);
  byId('transcript').addEventListener('input', saveEditor);
  byId('note').addEventListener('input', saveEditor);
  byId('channel').addEventListener('change', saveEditor);
  byId('segment-flags').addEventListener('change', saveEditor);
  byId('delete-segment').addEventListener('click', () => {
    const region = state.regionById.get(state.selectedId);
    if (region) region.remove();
  });
  document.querySelectorAll('input[name="new_channel"]').forEach((input) => {
    input.addEventListener('change', configureDragSelection);
  });
  byId('play').addEventListener('click', () => {
    state.playbackMode = 'full';
    if (state.wave) state.wave.playPause();
  });
  byId('play-selected').addEventListener('click', () => {
    const segment = selectedSegment();
    if (!segment || !state.wave) return;
    state.playbackMode = 'segment';
    state.wave.setTime(segment.start);
    state.wave.play();
  });
  byId('zoom').addEventListener('input', (event) => {
    if (state.wave) state.wave.zoom(Number(event.target.value));
  });
  byId('annotation-form').addEventListener('submit', submit);
  byId('download-json').addEventListener('click', downloadJson);

  init().catch((error) => showFatal(error.message));
})();
