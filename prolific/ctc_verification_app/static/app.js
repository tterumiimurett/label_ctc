(() => {
  const state = {
    assignment: null,
    worker: null,
    completionUrl: '',
    tasks: [],
    taskState: [],
    index: 0,
    wave: null,
    regions: null,
    regionById: new Map(),
    playbackMode: 'full',
    startedAt: new Date().toISOString(),
  };

  const byId = (id) => document.getElementById(id);
  const fmt = (seconds) => `${Number(seconds || 0).toFixed(2)}s`;
  const round = (seconds) => Math.round(Number(seconds) * 100) / 100;
  const escapeText = (text) => String(text ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function current() {
    return state.taskState[state.index];
  }

  function currentTask() {
    return current().task;
  }

  function boolValue(id) {
    const value = byId(id).value;
    if (value === 'yes') return true;
    if (value === 'no') return false;
    return null;
  }

  function setBoolValue(id, value) {
    byId(id).value = value === true ? 'yes' : value === false ? 'no' : '';
  }

  function regionColor(kind) {
    return {
      interrupted: 'rgba(31, 119, 180, 0.28)',
      interrupting: 'rgba(255, 127, 14, 0.28)',
      stall: 'rgba(220, 38, 38, 0.75)',
    }[kind];
  }

  function regionLabel(kind) {
    return {
      interrupted: 'Interrupted utterance',
      interrupting: 'Interrupting utterance',
      stall: 'Stuck',
    }[kind];
  }

  async function init() {
    const query = params();
    const required = ['PROLIFIC_PID', 'STUDY_ID', 'SESSION_ID'];
    const localDebugHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
    for (const key of required) {
      if (!query.get(key) && localDebugHost) query.set(key, `local_${key.toLowerCase()}`);
    }
    const missing = required.filter((key) => !query.get(key));
    if (missing.length) {
      showFatal(
        `Missing required Prolific URL parameters: ${missing.join(', ')}. ` +
        'For manual testing, add PROLIFIC_PID, STUDY_ID, and SESSION_ID to the URL.'
      );
      return;
    }
    byId('worker-line').textContent =
      `Participant ${query.get('PROLIFIC_PID')} · Session ${query.get('SESSION_ID')}`;
    const response = await fetch(`/api/assign?${query.toString()}`);
    const assignment = await response.json();
    if (!response.ok || assignment.status !== 'ok') {
      showFatal((assignment.errors || ['Unable to assign pre-labelled candidates.']).join(' '));
      return;
    }
    state.assignment = assignment.assignment;
    state.worker = assignment.worker;
    state.completionUrl = assignment.completion_url;
    state.tasks = assignment.tasks;
    state.taskState = state.tasks.map(normalizeTask);
    byId('loading-card').hidden = true;
    byId('verification-form').hidden = false;
    renderTask(0);
  }

  function showFatal(message) {
    byId('loading-message').textContent = message;
    byId('loading-card').classList.add('errors');
  }

  function normalizeTask(task) {
    const interrupted = task.regions && task.regions.interrupted;
    const interrupting = task.regions && task.regions.interrupting;
    return {
      task,
      started_at: new Date().toISOString(),
      speaker_stuck: null,
      interruption_type: '',
      stall_time: task.prelabels ? task.prelabels.stall_time : null,
      interrupter_becomes_main_speaker: null,
      corrected_interrupted_transcript: interrupted ? interrupted.transcript : '',
      corrected_interrupting_transcript: interrupting ? interrupting.transcript : '',
      note: '',
    };
  }

  function renderTask(index) {
    persistCurrentTask();
    destroyWave();
    state.index = index;
    const task = currentTask();
    const item = current();
    byId('task-title').textContent = `Candidate ${index + 1} of ${state.tasks.length}`;
    byId('progress-line').textContent = `Bundle ${state.assignment.bundle_id}`;
    byId('task-meta').textContent =
      `${task.task_id} · original timeline ${fmt(task.clip_start)}-${fmt(task.clip_end)}`;
    byId('task-nav').hidden = state.tasks.length === 1;
    byId('prev-task').disabled = index === 0;
    byId('next-task').disabled = index === state.tasks.length - 1;

    const interrupted = task.regions && task.regions.interrupted;
    const interrupting = task.regions && task.regions.interrupting;
    byId('interrupted-speaker').textContent = task.speakers.interrupted || 'Unknown';
    byId('interrupting-speaker').textContent = task.speakers.interrupting || 'Unknown';
    byId('interrupted-context').textContent =
      task.prelabel.main_speaker_pre_interrupt_transcript ||
      (interrupted && interrupted.transcript) ||
      task.prelabel.victim_text ||
      '';
    byId('interrupting-context').textContent =
      task.prelabel.interrupter_post_start_utterance ||
      (interrupting && interrupting.transcript) ||
      task.prelabel.interrupter_text ||
      '';
    byId('prelabel-explanation').textContent = task.prelabel.pred_reasoning || '';

    setBoolValue('speaker-stuck', item.speaker_stuck);
    byId('interruption-type').value = item.interruption_type || '';
    byId('stall-time').value = item.stall_time ?? '';
    setBoolValue('speaker-shift', item.interrupter_becomes_main_speaker);
    byId('interrupted-transcript').value = item.corrected_interrupted_transcript;
    byId('interrupting-transcript').value = item.corrected_interrupting_transcript;
    byId('note').value = item.note;
    syncFieldState();

    byId('audio').src = task.audio_url;
    byId('audio-url').innerHTML = `Audio URL: <a href="${escapeText(task.audio_url)}" target="_blank" rel="noopener">${escapeText(task.audio_url)}</a>`;
    wireWave(task);
    syncOutput();
  }

  function syncFieldState() {
    const stuck = byId('speaker-stuck').value === 'yes';
    byId('interruption-type').disabled = !stuck;
    byId('stall-time').disabled = !stuck;
    byId('speaker-shift').disabled = !stuck;
    if (!stuck) {
      byId('interruption-type').value = '';
      byId('stall-time').value = '';
      byId('speaker-shift').value = '';
    }
  }

  function destroyWave() {
    state.regionById.clear();
    if (state.wave) state.wave.destroy();
    state.wave = null;
    state.regions = null;
    byId('waveform').innerHTML = '';
  }

  function wireWave(task) {
    if (!window.WaveSurfer || !WaveSurfer.Regions) {
      byId('wave-status').textContent = 'Waveform status: WaveSurfer library is unavailable.';
      return;
    }
    byId('wave-status').textContent = 'Waveform status: loading WAV data...';
    const regions = WaveSurfer.Regions.create();
    const wave = WaveSurfer.create({
      container: '#waveform',
      media: byId('audio'),
      url: task.audio_url,
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
      addStaticRegion('interrupted', task.regions && task.regions.interrupted, 0);
      addStaticRegion('interrupting', task.regions && task.regions.interrupting, 1);
      addStallMarker();
      byId('time-display').textContent = `${fmt(0)} / ${fmt(wave.getDuration())}`;
    });
    wave.on('timeupdate', (time) => {
      byId('time-display').textContent = `${fmt(time)} / ${fmt(wave.getDuration())}`;
      const region = activePlaybackRegion();
      if (region && time >= region.end) {
        wave.pause();
        state.playbackMode = 'full';
      }
    });
    wave.on('error', (error) => {
      byId('wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
    });
    regions.on('region-updated', (region) => {
      if (region.id !== 'stall-marker') return;
      const time = round(region.start);
      current().stall_time = time;
      byId('stall-time').value = time;
      syncOutput();
    });
  }

  function addStaticRegion(kind, region, channelIdx) {
    if (!region || !state.regions) return;
    const start = Number(region.start);
    const end = Number(region.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    const waveRegion = state.regions.addRegion({
      id: kind,
      start,
      end,
      channelIdx,
      color: regionColor(kind),
      content: regionLabel(kind),
      drag: false,
      resize: false,
    });
    state.regionById.set(kind, waveRegion);
  }

  function addStallMarker() {
    if (!state.regions) return;
    const duration = state.wave.getDuration() || currentTask().duration || 0;
    const start = Math.min(Math.max(Number(current().stall_time || 0), 0), duration);
    const markerWidth = 0.08;
    const marker = state.regions.addRegion({
      id: 'stall-marker',
      start,
      end: Math.min(start + markerWidth, duration || start + markerWidth),
      color: regionColor('stall'),
      content: 'Stuck',
      drag: true,
      resize: false,
      minLength: 0.03,
    });
    state.regionById.set('stall-marker', marker);
  }

  function updateStallMarkerFromInput() {
    const marker = state.regionById.get('stall-marker');
    if (!marker) return;
    const duration = state.wave ? state.wave.getDuration() : currentTask().duration;
    const time = Math.min(Math.max(Number(byId('stall-time').value || 0), 0), duration || Infinity);
    const markerWidth = 0.08;
    marker.setOptions({
      start: time,
      end: Math.min(time + markerWidth, duration || time + markerWidth),
    });
  }

  function activePlaybackRegion() {
    if (state.playbackMode === 'interrupted') return state.regionById.get('interrupted');
    if (state.playbackMode === 'interrupting') return state.regionById.get('interrupting');
    return null;
  }

  function playRegion(kind) {
    const region = state.regionById.get(kind);
    if (!region || !state.wave) return;
    state.playbackMode = kind;
    state.wave.setTime(region.start);
    state.wave.play();
  }

  function persistCurrentTask() {
    if (!state.assignment || !current()) return;
    const item = current();
    item.speaker_stuck = boolValue('speaker-stuck');
    item.candidate_valid = item.speaker_stuck === true;
    item.interruption_type = byId('interruption-type').value;
    item.stall_time = byId('stall-time').value === '' ? null : round(Number(byId('stall-time').value));
    item.interrupter_becomes_main_speaker = boolValue('speaker-shift');
    item.corrected_interrupted_transcript = byId('interrupted-transcript').value;
    item.corrected_interrupting_transcript = byId('interrupting-transcript').value;
    item.note = byId('note').value;
    if (item.speaker_stuck !== true) {
      item.interruption_type = '';
      item.stall_time = null;
      item.interrupter_becomes_main_speaker = null;
    }
  }

  function taskPayload(item) {
    const task = item.task;
    return {
      candidate_id: task.candidate_id,
      task_id: task.task_id,
      audio_url: task.audio_url,
      duration: task.duration,
      prelabel_candidate_key: task.prelabel.candidate_key,
      regions: task.regions || {},
      candidate_valid: item.candidate_valid,
      speaker_stuck: item.speaker_stuck,
      interruption_type: item.interruption_type,
      stall_time: item.stall_time,
      interrupter_becomes_main_speaker: item.interrupter_becomes_main_speaker,
      corrected_interrupted_transcript: item.corrected_interrupted_transcript.trim(),
      corrected_interrupting_transcript: item.corrected_interrupting_transcript.trim(),
      note: item.note.trim(),
      ui_metadata: {
        started_at: item.started_at,
        submitted_at: new Date().toISOString(),
      },
    };
  }

  function submissionPayload() {
    persistCurrentTask();
    return {
      schema_version: 'ctc-verification-v1',
      worker: state.worker,
      assignment: state.assignment,
      tasks: state.taskState.map(taskPayload),
      ui_metadata: {
        started_at: state.startedAt,
        submitted_at: new Date().toISOString(),
      },
    };
  }

  function validationErrors() {
    const payload = submissionPayload();
    const errors = [];
    let firstInvalidTask = null;
    payload.tasks.forEach((task, index) => {
      const add = (message) => {
        errors.push(message);
        if (firstInvalidTask === null) firstInvalidTask = index;
      };
      const prefix = `Candidate ${index + 1}`;
      if (task.speaker_stuck !== true && task.speaker_stuck !== false) {
        add(`${prefix}: answer whether the interrupted speaker is stuck before the other speaker steps in.`);
        return;
      }
      if (task.speaker_stuck === false) return;
      if (task.speaker_stuck === true) {
        if (!task.interruption_type) add(`${prefix}: select the interruption type.`);
        if (task.stall_time === null || Number.isNaN(task.stall_time)) {
          add(`${prefix}: mark the last stuck word timestamp.`);
        } else if (task.duration !== null && (task.stall_time < 0 || task.stall_time > task.duration)) {
          add(`${prefix}: last stuck word timestamp must be inside the audio clip.`);
        } else {
          const interrupted = task.regions && task.regions.interrupted;
          const start = interrupted && Number(interrupted.start);
          const end = interrupted && Number(interrupted.end);
          if (Number.isFinite(start) && task.stall_time <= start) {
            add(`${prefix}: last stuck word timestamp must be after the start of the interrupted utterance.`);
          }
          if (Number.isFinite(end) && task.stall_time > end) {
            add(`${prefix}: last stuck word timestamp must be within the interrupted utterance.`);
          }
        }
      }
      if (task.interrupter_becomes_main_speaker !== true &&
          task.interrupter_becomes_main_speaker !== false) {
        add(`${prefix}: answer whether the interrupter becomes the main speaker.`);
      }
    });
    return {errors, firstInvalidTask};
  }

  function syncOutput() {
    if (!state.assignment) return;
    byId('json-output').textContent = JSON.stringify(submissionPayload(), null, 2);
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

  byId('prev-task').addEventListener('click', () => renderTask(Math.max(0, state.index - 1)));
  byId('next-task').addEventListener('click', () => renderTask(Math.min(state.tasks.length - 1, state.index + 1)));
  ['speaker-stuck'].forEach((id) => {
    byId(id).addEventListener('change', () => {
      syncFieldState();
      persistCurrentTask();
      syncOutput();
    });
  });
  ['interruption-type', 'speaker-shift', 'interrupted-transcript', 'interrupting-transcript', 'note'].forEach((id) => {
    byId(id).addEventListener('input', () => {
      persistCurrentTask();
      syncOutput();
    });
    byId(id).addEventListener('change', () => {
      persistCurrentTask();
      syncOutput();
    });
  });
  byId('stall-time').addEventListener('input', () => {
    persistCurrentTask();
    updateStallMarkerFromInput();
    syncOutput();
  });
  byId('play').addEventListener('click', () => {
    state.playbackMode = 'full';
    if (state.wave) state.wave.playPause();
  });
  byId('play-interrupted').addEventListener('click', () => playRegion('interrupted'));
  byId('play-interrupting').addEventListener('click', () => playRegion('interrupting'));
  byId('zoom').addEventListener('input', (event) => {
    if (state.wave) state.wave.zoom(Number(event.target.value));
  });
  byId('audio').addEventListener('error', () => {
    const media = byId('audio');
    const code = media.error ? media.error.code : 'unknown';
    byId('wave-status').textContent = `Waveform status: audio failed to load. Error code: ${code}.`;
  });
  byId('verification-form').addEventListener('submit', submit);

  init().catch((error) => showFatal(error.message));
})();
