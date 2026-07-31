(() => {
  const DRAFT_SCHEMA_VERSION = 2;

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
    hasRenderedTask: false,
  };

  const byId = (id) => document.getElementById(id);
  const fmt = (seconds) => `${Number(seconds || 0).toFixed(2)}s`;
  const round = (seconds) => Math.round(Number(seconds) * 100) / 100;
  const escapeText = (text) => String(text ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const fillerWords = new Set(['ah', 'eh', 'er', 'hm', 'hmm', 'mhm', 'mm', 'oh', 'ok', 'okay', 'uh', 'uhh', 'um', 'umm', 'yeah', 'yep']);
  const fillerPhrases = new Set(['uh huh', 'uh-huh', 'mhm', 'mm hmm', 'you know']);

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function current() {
    return state.taskState[state.index];
  }

  function currentTask() {
    return current().task;
  }

  function fieldValue(id) {
    const element = byId(id);
    const checked = document.querySelector(`input[name="${id}"]:checked`);
    if (checked) return checked.value;
    return element && 'value' in element ? element.value : '';
  }

  function setFieldValue(id, value) {
    const radios = document.querySelectorAll(`input[name="${id}"]`);
    if (radios.length) {
      radios.forEach((radio) => {
        radio.checked = radio.value === value;
      });
      return;
    }
    byId(id).value = value;
  }

  function setFieldDisabled(id, disabled) {
    const radios = document.querySelectorAll(`input[name="${id}"]`);
    if (radios.length) {
      radios.forEach((radio) => {
        radio.disabled = disabled;
      });
      return;
    }
    byId(id).disabled = disabled;
  }

  function boolValue(id) {
    const value = fieldValue(id);
    if (value === 'yes') return true;
    if (value === 'no') return false;
    return null;
  }

  function setBoolValue(id, value) {
    setFieldValue(id, value === true ? 'yes' : value === false ? 'no' : '');
  }

  function draftKey() {
    if (!state.worker || !state.assignment) return '';
    return [
      'ctcVerificationDraft',
      state.worker.study_id,
      state.worker.prolific_pid,
      state.worker.session_id,
      state.assignment.bundle_id,
    ].join(':');
  }

  function normalizeTranscript(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/[^\w\s'-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function hasNonFillerWord(text) {
    const normalized = normalizeTranscript(text);
    if (!normalized || fillerPhrases.has(normalized)) return false;
    return normalized
      .split(/\s+/)
      .some((word) => word && !fillerWords.has(word.replace(/^'+|'+$/g, '')));
  }

  function regionColor(kind) {
    return {
      interrupted: 'rgba(31, 119, 180, 0.28)',
      interrupting: 'rgba(255, 127, 14, 0.28)',
      interruptingStart: 'rgba(255, 127, 14, 0.78)',
      stall: 'rgba(220, 38, 38, 0.75)',
    }[kind];
  }

  function regionLabel(kind) {
    return {
      interrupted: 'Interrupted utterance',
      interrupting: 'Interrupting utterance',
      interruptingStart: 'Start',
      stall: 'Word end',
    }[kind];
  }

  function regionLabelElement(text, kind) {
    const label = document.createElement('span');
    label.textContent = text;
    label.className = `wave-region-label ${kind}-label`;
    Object.assign(label.style, {
      background: 'rgba(255, 255, 255, 0.88)',
      borderRadius: '3px',
      boxShadow: '0 1px 2px rgba(15, 23, 42, 0.12)',
      fontSize: '11px',
      fontWeight: '700',
      left: '4px',
      lineHeight: '1',
      maxWidth: 'none',
      padding: '2px 4px',
      pointerEvents: 'none',
      position: 'absolute',
      top: '4px',
      whiteSpace: 'nowrap',
      zIndex: '10',
    });
    if (kind === 'interrupting-start-marker') {
      label.style.color = '#c2410c';
      label.style.top = '176px';
    } else if (kind === 'stall-marker') {
      label.style.color = '#dc2626';
      label.style.top = '70px';
    } else if (kind === 'interrupted') {
      label.style.color = '#1f77b4';
    } else if (kind === 'interrupting') {
      label.style.color = '#c2410c';
    }
    return label;
  }

  function keepRegionLabelVisible(region) {
    if (!region || !region.element) return;
    region.element.style.overflow = 'visible';
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
    restoreDraft();
    byId('loading-card').hidden = true;
    byId('verification-form').hidden = false;
    renderTask(state.index);
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
      relevant_interruption: null,
      speaker_stuck: null,
      interruption_type: '',
      word_phrase_fits: null,
      stall_time: task.prelabels ? task.prelabels.stall_time : null,
      interrupting_start_time: defaultInterruptingStartTime(task, interrupting),
      interrupting_start_checked: false,
      interrupter_becomes_main_speaker: null,
      corrected_interrupted_transcript: prefilledInterruptedTranscript(task, interrupted),
      corrected_interrupting_transcript: prefilledInterruptingTranscript(task, interrupting),
      transcript_checked: false,
      note: '',
    };
  }

  function defaultInterruptingStartTime(task, interrupting) {
    const regionStart = interrupting && Number(interrupting.start);
    if (Number.isFinite(regionStart)) {
      return regionStart;
    }
    const prelabelStart = task.prelabels && Number(task.prelabels.interrupting_start_time);
    if (Number.isFinite(prelabelStart)) {
      return prelabelStart;
    }
    return null;
  }

  function prefilledInterruptedTranscript(task, interrupted) {
    return (
      task.prelabel.main_speaker_pre_interrupt_transcript ||
      (interrupted && interrupted.transcript) ||
      task.prelabel.victim_text ||
      ''
    );
  }

  function prefilledInterruptingTranscript(task, interrupting) {
    return (
      task.prelabel.interrupter_post_start_utterance ||
      (interrupting && interrupting.transcript) ||
      task.prelabel.interrupter_text ||
      ''
    );
  }

  function restoreDraft() {
    const key = draftKey();
    if (!key) return;
    try {
      const draft = JSON.parse(window.localStorage.getItem(key) || 'null');
      if (!draft || !Array.isArray(draft.taskState)) return;
      if (draft.version !== DRAFT_SCHEMA_VERSION) {
        window.localStorage.removeItem(key);
        return;
      }
      const currentIds = state.taskState.map((item) => item.task.candidate_id).join('|');
      const draftIds = draft.taskState.map((item) => item.task && item.task.candidate_id).join('|');
      if (currentIds !== draftIds) return;
      state.taskState = state.taskState.map((item, index) => {
        const defaultInterruptingStart = item.interrupting_start_time;
        const restored = {
          ...item,
          ...draft.taskState[index],
          task: item.task,
        };
        if (restored.interrupting_start_checked !== true) {
          restored.interrupting_start_time = defaultInterruptingStart;
        } else if (restored.interrupting_start_time === null || restored.interrupting_start_time === undefined) {
          restored.interrupting_start_time = defaultInterruptingStart;
        }
        if (restored.stall_time === null || restored.stall_time === undefined) {
          restored.stall_time = item.stall_time;
        }
        return restored;
      });
      state.index = Math.min(Math.max(Number(draft.index) || 0, 0), state.taskState.length - 1);
      byId('save-status').textContent = 'Draft restored from this browser.';
    } catch (error) {
      console.warn('Unable to restore local draft', error);
    }
  }

  function saveDraft() {
    const key = draftKey();
    if (!key) return;
    try {
      const taskState = state.taskState.map((item) => {
        const {task, ...draftItem} = item;
        return {
          ...draftItem,
          task: {candidate_id: task.candidate_id},
        };
      });
      window.localStorage.setItem(key, JSON.stringify({
        version: DRAFT_SCHEMA_VERSION,
        index: state.index,
        taskState,
        updated_at: new Date().toISOString(),
      }));
      byId('save-status').textContent = 'Draft saved in this browser.';
    } catch (error) {
      console.warn('Unable to save local draft', error);
    }
  }

  function clearDraft() {
    const key = draftKey();
    if (key) window.localStorage.removeItem(key);
  }

  function renderTask(index) {
    if (state.hasRenderedTask) persistCurrentTask();
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

    setBoolValue('relevant-interruption', item.relevant_interruption);
    setBoolValue('speaker-stuck', item.speaker_stuck);
    setFieldValue('interruption-type', normalizeInterruptionType(item.interruption_type));
    setBoolValue('word-phrase-fits', item.word_phrase_fits);
    byId('stall-time').value = item.stall_time ?? '';
    byId('interrupting-start-time').value = item.interrupting_start_time ?? '';
    byId('interrupting-start-checked').checked = item.interrupting_start_checked === true;
    setBoolValue('speaker-shift', item.interrupter_becomes_main_speaker);
    byId('interrupted-transcript').value = item.corrected_interrupted_transcript;
    byId('interrupting-transcript').value = item.corrected_interrupting_transcript;
    byId('transcript-checked').checked = item.transcript_checked === true;
    byId('note').value = item.note;
    syncFieldState();

    byId('audio').src = task.audio_url;
    byId('audio-url').innerHTML = `Audio URL: <a href="${escapeText(task.audio_url)}" target="_blank" rel="noopener">${escapeText(task.audio_url)}</a>`;
    wireWave(task);
    syncOutput();
    state.hasRenderedTask = true;
  }

  function syncFieldState() {
    const relevant = fieldValue('relevant-interruption') === 'yes';
    const nonCtc = fieldValue('relevant-interruption') === 'no';
    const stuck = fieldValue('speaker-stuck') === 'yes';
    const stuckAnswered = fieldValue('speaker-stuck') === 'yes' || fieldValue('speaker-stuck') === 'no';
    const intentionRequired = relevant && stuckAnswered;
    setFieldDisabled('speaker-stuck', !relevant);
    setFieldDisabled('interruption-type', !relevant || !stuck);
    setFieldDisabled('word-phrase-fits', !intentionRequired);
    byId('stall-time').disabled = !relevant;
    byId('interrupting-start-time').disabled = !relevant;
    byId('interrupting-start-checked').disabled = !relevant;
    setFieldDisabled('speaker-shift', !relevant);
    byId('interrupted-transcript').disabled = nonCtc;
    byId('interrupting-transcript').disabled = nonCtc;
    byId('transcript-checked').disabled = !relevant;
    if (!relevant) {
      setFieldValue('speaker-stuck', '');
      setFieldValue('interruption-type', '');
      setFieldValue('word-phrase-fits', '');
      byId('interrupting-start-checked').checked = false;
      byId('transcript-checked').checked = false;
      setFieldValue('speaker-shift', '');
    } else if (!stuck) {
      setFieldValue('interruption-type', '');
    } else if (!stuckAnswered) {
      setFieldValue('word-phrase-fits', '');
    }
  }

  function normalizeInterruptionType(value) {
    if (value === 'word_phrase_confident' || value === 'word_phrase_unsure') return 'word_phrase';
    return value || '';
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
      addInterruptingStartMarker();
      addStallMarker();
    });
    wave.on('timeupdate', (time) => {
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
      const time = round(region.start);
      if (region.id === 'stall-marker') {
        current().stall_time = time;
        byId('stall-time').value = time;
      } else if (region.id === 'interrupting-start-marker') {
        current().interrupting_start_time = time;
        byId('interrupting-start-time').value = time;
      } else {
        return;
      }
      syncOutput();
    });
  }

  function reloadCurrentAudio() {
    if (!current()) return;
    persistCurrentTask();
    destroyWave();
    const task = currentTask();
    byId('audio').src = task.audio_url;
    wireWave(task);
    syncOutput();
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
      content: regionLabelElement(regionLabel(kind), kind),
      drag: false,
      resize: false,
    });
    keepRegionLabelVisible(waveRegion);
    state.regionById.set(kind, waveRegion);
  }

  function addInterruptingStartMarker() {
    if (!state.regions) return;
    const duration = state.wave.getDuration() || currentTask().duration || 0;
    const fallbackStart = defaultInterruptingStartTime(currentTask(), currentTask().regions && currentTask().regions.interrupting);
    const markerStart = Number.isFinite(Number(current().interrupting_start_time)) ?
      Number(current().interrupting_start_time) :
      Number(fallbackStart || 0);
    const start = Math.min(Math.max(markerStart, 0), duration);
    const markerWidth = 0.08;
    const marker = state.regions.addRegion({
      id: 'interrupting-start-marker',
      start,
      end: Math.min(start + markerWidth, duration || start + markerWidth),
      color: regionColor('interruptingStart'),
      content: regionLabelElement(regionLabel('interruptingStart'), 'interrupting-start-marker'),
      drag: true,
      resize: false,
      minLength: 0.03,
    });
    keepRegionLabelVisible(marker);
    state.regionById.set('interrupting-start-marker', marker);
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
      content: regionLabelElement(regionLabel('stall'), 'stall-marker'),
      drag: true,
      resize: false,
      minLength: 0.03,
    });
    keepRegionLabelVisible(marker);
    state.regionById.set('stall-marker', marker);
  }

  function updateInterruptingStartMarkerFromInput() {
    const marker = state.regionById.get('interrupting-start-marker');
    if (!marker) return;
    const duration = state.wave ? state.wave.getDuration() : currentTask().duration;
    const time = Math.min(Math.max(Number(byId('interrupting-start-time').value || 0), 0), duration || Infinity);
    const markerWidth = 0.08;
    marker.setOptions({
      start: time,
      end: Math.min(time + markerWidth, duration || time + markerWidth),
    });
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
    item.relevant_interruption = boolValue('relevant-interruption');
    item.speaker_stuck = boolValue('speaker-stuck');
    item.candidate_valid = item.relevant_interruption === true && item.speaker_stuck === true;
    item.interruption_type = normalizeInterruptionType(fieldValue('interruption-type'));
    item.word_phrase_fits = boolValue('word-phrase-fits');
    item.stall_time = byId('stall-time').value === '' ? null : round(Number(byId('stall-time').value));
    item.interrupting_start_time = byId('interrupting-start-time').value === '' ? null : round(Number(byId('interrupting-start-time').value));
    item.interrupting_start_checked = byId('interrupting-start-checked').checked;
    item.interrupter_becomes_main_speaker = boolValue('speaker-shift');
    item.corrected_interrupted_transcript = byId('interrupted-transcript').value;
    item.corrected_interrupting_transcript = byId('interrupting-transcript').value;
    item.transcript_checked = byId('transcript-checked').checked;
    item.note = byId('note').value;
    if (item.relevant_interruption !== true) {
      item.speaker_stuck = null;
      item.interruption_type = '';
      item.word_phrase_fits = null;
      item.interrupting_start_checked = false;
      item.transcript_checked = false;
      item.interrupter_becomes_main_speaker = null;
    } else if (item.speaker_stuck !== true) {
      item.interruption_type = '';
    } else if (item.interruption_type !== 'word_phrase') {
      item.word_phrase_fits = null;
    }
    saveDraft();
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
      relevant_interruption: item.relevant_interruption,
      speaker_stuck: item.speaker_stuck,
      interruption_type: item.interruption_type,
      word_phrase_fits: item.word_phrase_fits,
      stall_time: item.stall_time,
      last_word_before_interruption_end_time: item.stall_time,
      interrupting_start_time: item.interrupting_start_time,
      interrupting_start_checked: item.interrupting_start_checked,
      interrupter_becomes_main_speaker: item.interrupter_becomes_main_speaker,
      corrected_interrupted_transcript: item.corrected_interrupted_transcript.trim(),
      corrected_interrupting_transcript: item.corrected_interrupting_transcript.trim(),
      transcript_checked: item.transcript_checked,
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
      const prefix = `Item ${index + 1}`;
      if (task.relevant_interruption !== true && task.relevant_interruption !== false) {
        add(`${prefix}: answer whether the second speaker's utterance completes the first speaker's unfinished sentence.`);
        return;
      }
      if (task.relevant_interruption === false) return;
      if (task.speaker_stuck !== true && task.speaker_stuck !== false) {
        add(`${prefix}: answer whether the interrupted speaker is stuck before the other speaker steps in.`);
        return;
      }
      if (task.speaker_stuck === true && !task.interruption_type) {
        add(`${prefix}: select the interruption type.`);
      }
      if (task.word_phrase_fits !== true && task.word_phrase_fits !== false) {
        add(`${prefix}: answer whether the interrupting utterance correctly fits the speaker's intention.`);
      }
      if (task.speaker_stuck === false) {
        if (task.interruption_type) {
          add(`${prefix}: interruption type should be blank when the speaker is not stuck.`);
        }
      }
      if (task.speaker_stuck === true &&
          task.interruption_type === 'word_phrase' &&
          !hasNonFillerWord(task.corrected_interrupting_transcript)) {
        add(`${prefix}: word/phrase interruptions should include at least one non-filler word in the interrupting transcript.`);
      }
      if (task.stall_time === null || Number.isNaN(task.stall_time)) {
        add(`${prefix}: mark the end timestamp of the last word before the interruption.`);
      } else if (task.duration !== null && (task.stall_time < 0 || task.stall_time > task.duration)) {
        add(`${prefix}: end timestamp of the last word before the interruption must be inside the audio clip.`);
      } else {
        const interrupted = task.regions && task.regions.interrupted;
        const start = interrupted && Number(interrupted.start);
        const end = interrupted && Number(interrupted.end);
        const interruptionStart = Number(task.interrupting_start_time);
        if (Number.isFinite(start) && task.stall_time <= start) {
          add(`${prefix}: end timestamp of the last word before the interruption must be after the start of the interrupted utterance.`);
        }
        if (Number.isFinite(end) && task.stall_time > end) {
          add(`${prefix}: end timestamp of the last word before the interruption must be within the interrupted utterance.`);
        }
        if (Number.isFinite(interruptionStart) && task.stall_time >= interruptionStart) {
          add(`${prefix}: end timestamp of the last word before the interruption must be before the interrupting utterance starts.`);
        }
      }
      if (task.transcript_checked !== true) {
        add(`${prefix}: confirm that you checked the transcript and removed words after interruption.`);
      }
      if (!task.corrected_interrupted_transcript) {
        add(`${prefix}: enter the interrupted utterance transcript and remove words after the interruption.`);
      }
      if (!task.corrected_interrupting_transcript) {
        add(`${prefix}: enter the interrupting utterance transcript.`);
      }
      const interruptedRegion = task.regions && task.regions.interrupted;
      if (interruptedRegion &&
          Number.isFinite(Number(interruptedRegion.end)) &&
          Number.isFinite(Number(task.interrupting_start_time)) &&
          Number(interruptedRegion.end) > Number(task.interrupting_start_time) &&
          normalizeTranscript(task.corrected_interrupted_transcript) &&
          normalizeTranscript(task.corrected_interrupted_transcript) === normalizeTranscript(interruptedRegion.transcript)) {
        add(`${prefix}: interrupted transcript appears unchanged; remove words after the interruption.`);
      }
      if (typeof task.interrupting_start_time !== 'number' || Number.isNaN(task.interrupting_start_time)) {
        add(`${prefix}: mark the start timestamp of the interrupting utterance.`);
      } else if (task.duration !== null &&
          (task.interrupting_start_time < 0 || task.interrupting_start_time > task.duration)) {
        add(`${prefix}: start timestamp of the interrupting utterance must be inside the audio clip.`);
      } else {
        const interrupting = task.regions && task.regions.interrupting;
        const interrupted = task.regions && task.regions.interrupted;
        const interruptedStart = interrupted && Number(interrupted.start);
        const interruptingEnd = interrupting && Number(interrupting.end);
        if (Number.isFinite(interruptedStart) && task.interrupting_start_time < interruptedStart) {
          add(`${prefix}: start timestamp of the interrupting utterance must not be before the interrupted utterance starts.`);
        }
        if (Number.isFinite(interruptingEnd) && task.interrupting_start_time >= interruptingEnd) {
          add(`${prefix}: start timestamp of the interrupting utterance must be before the end of that utterance.`);
        }
      }
      if (task.interrupting_start_checked !== true) {
        add(`${prefix}: confirm that you checked the start of the interrupting utterance.`);
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
    clearDraft();
    window.location.href = result.completion_url;
  }

  byId('prev-task').addEventListener('click', () => renderTask(Math.max(0, state.index - 1)));
  byId('next-task').addEventListener('click', () => renderTask(Math.min(state.tasks.length - 1, state.index + 1)));
  ['relevant-interruption', 'speaker-stuck'].forEach((id) => {
    byId(id).addEventListener('change', () => {
      syncFieldState();
      persistCurrentTask();
      syncOutput();
    });
  });
  ['interruption-type', 'word-phrase-fits', 'speaker-shift', 'interrupted-transcript', 'interrupting-transcript', 'note'].forEach((id) => {
    byId(id).addEventListener('input', () => {
      persistCurrentTask();
      syncOutput();
    });
    byId(id).addEventListener('change', () => {
      syncFieldState();
      persistCurrentTask();
      syncOutput();
    });
  });
  byId('stall-time').addEventListener('input', () => {
    persistCurrentTask();
    updateStallMarkerFromInput();
    syncOutput();
  });
  byId('interrupting-start-time').addEventListener('input', () => {
    persistCurrentTask();
    updateInterruptingStartMarkerFromInput();
    syncOutput();
  });
  byId('interrupting-start-checked').addEventListener('change', () => {
    persistCurrentTask();
    syncOutput();
  });
  byId('transcript-checked').addEventListener('change', () => {
    persistCurrentTask();
    syncOutput();
  });
  byId('reload-audio').addEventListener('click', reloadCurrentAudio);
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
