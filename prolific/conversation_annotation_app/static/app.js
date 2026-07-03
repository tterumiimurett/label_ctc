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

  function taskState() {
    return state.taskState[state.index];
  }

  function currentPhenomenon() {
    const current = taskState();
    return current.phenomena[current.phenomenonIndex];
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

  function numberValue(id) {
    const value = byId(id).value.trim();
    return value === '' ? null : round(Number(value));
  }

  function setValue(id, value) {
    byId(id).value = value ?? '';
  }

  function setNumberValue(id, value) {
    byId(id).value = value === null || value === undefined ? '' : String(value);
  }

  function booleanSelectValue(id) {
    const value = byId(id).value;
    if (value === 'yes') return true;
    if (value === 'no') return false;
    return null;
  }

  function setBooleanSelectValue(id, value) {
    byId(id).value = value === true ? 'yes' : value === false ? 'no' : '';
  }

  function wordPhraseFitValue() {
    const value = byId('ctc-word-phrase-fit').value;
    if (value === 'not_applicable') return 'not_applicable';
    return booleanSelectValue('ctc-word-phrase-fit');
  }

  function setWordPhraseFitValue(value) {
    byId('ctc-word-phrase-fit').value = value === 'not_applicable'
      ? 'not_applicable'
      : value === true
        ? 'yes'
        : value === false
          ? 'no'
          : '';
  }

  const ctcInterruptionTypes = {
    stalled: [
      ['word_phrase_confident', 'Word/phrase (confident)'],
      ['word_phrase_unsure', 'Word/phrase (guess/unsure)'],
      ['guiding_question', 'Guiding question'],
      ['unspecified', 'Unspecified'],
    ],
    not_stalled_projection: [
      ['buzz_in', 'Buzz-in'],
      ['unspecified', 'Unspecified'],
    ],
  };

  function isWordPhraseInterruption(type) {
    return type === 'word_phrase_confident' || type === 'word_phrase_unsure';
  }

  function renderCtcInterruptionOptions(speakerState, selectedValue = '') {
    const select = byId('ctc-interruption-type');
    const choices = ctcInterruptionTypes[speakerState] || [];
    const placeholder = choices.length ? 'Select...' : 'Select speaker state first...';
    select.replaceChildren(new Option(placeholder, ''));
    choices.forEach(([value, label]) => select.append(new Option(label, value)));
    select.value = choices.some(([value]) => value === selectedValue) ? selectedValue : '';
    select.disabled = choices.length === 0;
  }

  function syncWordPhraseFitVisibility(resetAutomaticValue = true) {
    const visible = isWordPhraseInterruption(byId('ctc-interruption-type').value);
    byId('ctc-word-phrase-fit-field').hidden = !visible;
    if (!visible) {
      setValue('ctc-word-phrase-fit', 'not_applicable');
    } else if (resetAutomaticValue && byId('ctc-word-phrase-fit').value === 'not_applicable') {
      setValue('ctc-word-phrase-fit', '');
    }
  }

  function segmentOptionLabel(segment) {
    const transcript = String(segment.transcript || '(transcript required)').replace(/\s+/g, ' ').trim();
    const snippet = transcript.length > 88 ? `${transcript.slice(0, 85)}...` : transcript;
    return `${channelLabel(segment.channel)} ${fmt(segment.start)}-${fmt(segment.end)} | ${snippet}`;
  }

  function populateSegmentSelect(select, selectedId) {
    const empty = new Option('Select a preloaded segment...', '');
    select.replaceChildren(empty);
    sortedSegments().forEach((segment) => {
      select.append(new Option(segmentOptionLabel(segment), segment.id));
    });
    select.value = selectedId && segments().has(selectedId) ? selectedId : '';
  }

  function refreshSegmentSelectors() {
    if (!state.assignment || !taskState()) return;
    const phenomenon = currentPhenomenon();
    populateSegmentSelect(byId('ctc-interrupted-segment'), phenomenon.ctc.interrupted_segment_id);
    populateSegmentSelect(byId('ctc-interrupting-segment'), phenomenon.ctc.interrupting_segment_id);
    populateSegmentSelect(byId('pp-question-segment'), phenomenon.pragmatic_pair.question_segment_id);
    populateSegmentSelect(byId('pp-response-segment'), phenomenon.pragmatic_pair.response_segment_id);
  }

  function fillCtcInterruptedFromSegment(segmentId) {
    const segment = segments().get(segmentId);
    if (!segment) return;
    setValue('ctc-interrupted-speaker', channelLabel(segment.channel));
    setNumberValue('ctc-utterance-start', segment.start);
    setNumberValue('ctc-stall-time', segment.end);
  }

  function fillCtcInterruptingFromSegment(segmentId) {
    const segment = segments().get(segmentId);
    if (!segment) return;
    setValue('ctc-interrupter-speaker', channelLabel(segment.channel));
    setNumberValue('ctc-interruption-start', segment.start);
    setNumberValue('ctc-interruption-end', segment.end);
  }

  function ctcMetadataFromSegmentMap(segmentMap, interruptedSegmentId, interruptingSegmentId) {
    const interrupted = segmentMap.get(interruptedSegmentId);
    const interrupting = segmentMap.get(interruptingSegmentId);
    return {
      interrupted_speaker: interrupted ? channelLabel(interrupted.channel) : '',
      interrupter_speaker: interrupting ? channelLabel(interrupting.channel) : '',
      utterance_start: interrupted ? round(interrupted.start) : null,
      stall_time: interrupted ? round(interrupted.end) : null,
      interruption_start: interrupting ? round(interrupting.start) : null,
      interruption_end: interrupting ? round(interrupting.end) : null,
    };
  }

  function ctcMetadataFromSelections(interruptedSegmentId, interruptingSegmentId) {
    return ctcMetadataFromSegmentMap(segments(), interruptedSegmentId, interruptingSegmentId);
  }

  function fillPragmaticPairSegment(role, segmentId) {
    const segment = segments().get(segmentId);
    if (!segment) return;
    if (role === 'question') {
      setValue('pp-question-speaker', channelLabel(segment.channel));
      setNumberValue('pp-question-start', segment.start);
      setNumberValue('pp-question-end', segment.end);
    } else {
      setValue('pp-response-speaker', channelLabel(segment.channel));
      setNumberValue('pp-response-start', segment.start);
      setNumberValue('pp-response-end', segment.end);
    }
  }

  function clearDeletedSegmentReference(segmentId) {
    taskState().phenomena.forEach((phenomenon) => {
      if (phenomenon.ctc.interrupted_segment_id === segmentId) phenomenon.ctc.interrupted_segment_id = '';
      if (phenomenon.ctc.interrupting_segment_id === segmentId) phenomenon.ctc.interrupting_segment_id = '';
      if (phenomenon.pragmatic_pair.question_segment_id === segmentId) phenomenon.pragmatic_pair.question_segment_id = '';
      if (phenomenon.pragmatic_pair.response_segment_id === segmentId) phenomenon.pragmatic_pair.response_segment_id = '';
    });
  }

  function initialPhenomenonType(task) {
    const choices = task.ctc_status || [];
    if (choices.includes('Pragmatic_Pairs')) return 'pragmatic_pair';
    if (choices.some((choice) => ['is_CTC', 'Buzz_in', 'in_the_Middle'].includes(choice))) return 'ctc';
    if (choices.includes('not_CTC')) return 'not_target';
    return '';
  }

  function defaultPhenomenon(task) {
    const choices = task.ctc_status || [];
    return {
      phenomenon_type: initialPhenomenonType(task),
      ctc: {
        interrupted_segment_id: '',
        interrupting_segment_id: '',
        speaker_state: choices.includes('Buzz_in') ? 'not_stalled_projection' : '',
        interruption_type: choices.includes('Buzz_in') ? 'buzz_in' : '',
        interrupted_speaker: '',
        interrupter_speaker: '',
        utterance_start: null,
        stall_time: null,
        interruption_start: null,
        interruption_end: null,
        word_phrase_fits: 'not_applicable',
        interrupter_becomes_main_speaker: null,
      },
      pragmatic_pair: {
        question_segment_id: '',
        response_segment_id: '',
        question_speaker: '',
        response_speaker: '',
        question_start: null,
        question_end: null,
        response_start: null,
        response_end: null,
      },
    };
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
      phenomena: [defaultPhenomenon(task)],
      phenomenonIndex: 0,
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
    persistCurrentTask();
    state.index = index;
    state.selectedId = null;
    destroyWave();

    const current = taskState();
    const task = current.task;
    byId('task-title').textContent = `Audio ${index + 1} of ${state.tasks.length}`;
    byId('progress-line').textContent = `Bundle ${state.assignment.bundle_id}`;
    byId('task-nav').hidden = state.tasks.length === 1;
    byId('prev-task').disabled = index === 0;
    byId('next-task').disabled = index === state.tasks.length - 1;

    renderPhenomenon();
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
    refreshSegmentSelectors();
  }

  function scrollSelectedSegmentIntoView() {
    const selected = byId('segments-list').querySelector('.segment-button.selected');
    if (selected) selected.scrollIntoView({block: 'nearest', inline: 'nearest'});
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
    byId('transcript').value = segment.transcript;
    renderList();
    scrollSelectedSegmentIntoView();
  }

  function saveEditor(shouldSync = true) {
    const segment = selectedSegment();
    if (!segment) return;
    segment.transcript = byId('transcript').value;
    renderList();
    if (shouldSync) syncOutput();
  }

  function phenomenonTypeLabel(type) {
    return {
      ctc: 'CTC',
      pragmatic_pair: 'Pragmatic Pair',
      not_target: 'Not found',
      unclear: 'Unspecified Interruption',
    }[type] || 'Unlabeled';
  }

  function renderPhenomenonList() {
    const current = taskState();
    const list = byId('phenomenon-list');
    list.innerHTML = current.phenomena.map((phenomenon, index) => `
      <button type="button" class="phenomenon-tab ${index === current.phenomenonIndex ? 'selected' : ''}"
              data-phenomenon-index="${index}">
        ${index + 1}. ${escapeText(phenomenonTypeLabel(phenomenon.phenomenon_type))}
      </button>`).join('');
    list.querySelectorAll('[data-phenomenon-index]').forEach((button) => {
      button.addEventListener('click', () => selectPhenomenon(Number(button.dataset.phenomenonIndex)));
    });
    byId('delete-phenomenon').disabled = current.phenomena.length === 1;
  }

  function renderPhenomenon() {
    const phenomenon = currentPhenomenon();
    renderPhenomenonList();
    refreshSegmentSelectors();
    setValue('phenomenon-type', phenomenon.phenomenon_type);
    setValue('ctc-interrupted-segment', phenomenon.ctc.interrupted_segment_id);
    setValue('ctc-interrupting-segment', phenomenon.ctc.interrupting_segment_id);
    setValue('ctc-speaker-state', phenomenon.ctc.speaker_state);
    renderCtcInterruptionOptions(phenomenon.ctc.speaker_state, phenomenon.ctc.interruption_type);
    setWordPhraseFitValue(phenomenon.ctc.word_phrase_fits);
    syncWordPhraseFitVisibility(false);
    setValue('ctc-interrupted-speaker', phenomenon.ctc.interrupted_speaker);
    setValue('ctc-interrupter-speaker', phenomenon.ctc.interrupter_speaker);
    setNumberValue('ctc-utterance-start', phenomenon.ctc.utterance_start);
    setNumberValue('ctc-stall-time', phenomenon.ctc.stall_time);
    setNumberValue('ctc-interruption-start', phenomenon.ctc.interruption_start);
    setNumberValue('ctc-interruption-end', phenomenon.ctc.interruption_end);
    setBooleanSelectValue('ctc-speaker-shift', phenomenon.ctc.interrupter_becomes_main_speaker);
    setValue('pp-question-segment', phenomenon.pragmatic_pair.question_segment_id);
    setValue('pp-response-segment', phenomenon.pragmatic_pair.response_segment_id);
    setValue('pp-question-speaker', phenomenon.pragmatic_pair.question_speaker);
    setValue('pp-response-speaker', phenomenon.pragmatic_pair.response_speaker);
    setNumberValue('pp-question-start', phenomenon.pragmatic_pair.question_start);
    setNumberValue('pp-question-end', phenomenon.pragmatic_pair.question_end);
    setNumberValue('pp-response-start', phenomenon.pragmatic_pair.response_start);
    setNumberValue('pp-response-end', phenomenon.pragmatic_pair.response_end);
    syncPhenomenonVisibility();
  }

  function syncPhenomenonVisibility() {
    const type = byId('phenomenon-type').value;
    byId('ctc-fields').hidden = type !== 'ctc';
    byId('pp-fields').hidden = type !== 'pragmatic_pair';
  }

  function savePhenomenon(shouldSync = true) {
    const phenomenon = currentPhenomenon();
    const interruptedSegmentId = byId('ctc-interrupted-segment').value;
    const interruptingSegmentId = byId('ctc-interrupting-segment').value;
    const ctcMetadata = ctcMetadataFromSelections(interruptedSegmentId, interruptingSegmentId);
    phenomenon.phenomenon_type = byId('phenomenon-type').value;
    phenomenon.ctc = {
      interrupted_segment_id: interruptedSegmentId,
      interrupting_segment_id: interruptingSegmentId,
      speaker_state: byId('ctc-speaker-state').value,
      interruption_type: byId('ctc-interruption-type').value,
      interrupted_speaker: ctcMetadata.interrupted_speaker,
      interrupter_speaker: ctcMetadata.interrupter_speaker,
      utterance_start: ctcMetadata.utterance_start,
      stall_time: ctcMetadata.stall_time,
      interruption_start: ctcMetadata.interruption_start,
      interruption_end: ctcMetadata.interruption_end,
      word_phrase_fits: isWordPhraseInterruption(byId('ctc-interruption-type').value)
        ? wordPhraseFitValue()
        : 'not_applicable',
      interrupter_becomes_main_speaker: booleanSelectValue('ctc-speaker-shift'),
    };
    phenomenon.pragmatic_pair = {
      question_segment_id: byId('pp-question-segment').value,
      response_segment_id: byId('pp-response-segment').value,
      question_speaker: byId('pp-question-speaker').value,
      response_speaker: byId('pp-response-speaker').value,
      question_start: numberValue('pp-question-start'),
      question_end: numberValue('pp-question-end'),
      response_start: numberValue('pp-response-start'),
      response_end: numberValue('pp-response-end'),
    };
    syncPhenomenonVisibility();
    renderPhenomenonList();
    if (shouldSync) syncOutput();
  }

  function selectPhenomenon(index) {
    if (index === taskState().phenomenonIndex) return;
    savePhenomenon(false);
    taskState().phenomenonIndex = index;
    renderPhenomenon();
    syncOutput();
  }

  function addPhenomenon() {
    savePhenomenon(false);
    const current = taskState();
    current.phenomena.push(defaultPhenomenon({ctc_status: []}));
    current.phenomenonIndex = current.phenomena.length - 1;
    renderPhenomenon();
    syncOutput();
  }

  function deletePhenomenon() {
    const current = taskState();
    if (current.phenomena.length === 1) return;
    current.phenomena.splice(current.phenomenonIndex, 1);
    current.phenomenonIndex = Math.min(current.phenomenonIndex, current.phenomena.length - 1);
    renderPhenomenon();
    syncOutput();
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
      clearDeletedSegmentReference(region.id);
      if (state.selectedId === region.id) {
        state.selectedId = sortedSegments().length ? sortedSegments()[0].id : null;
      }
      selectSegment(state.selectedId);
      refreshSegmentSelectors();
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

  function persistCurrentTask() {
    if (!state.assignment || !taskState()) return;
    saveEditor(false);
    savePhenomenon(false);
  }

  function phenomenonPayload(current, phenomenon, index) {
    const ctcMetadata = ctcMetadataFromSegmentMap(
      current.segments,
      phenomenon.ctc.interrupted_segment_id,
      phenomenon.ctc.interrupting_segment_id,
    );
    return {
      phenomenon_id: index + 1,
      phenomenon_type: phenomenon.phenomenon_type,
      ctc: {
        ...phenomenon.ctc,
        ...ctcMetadata,
      },
      pragmatic_pair: {...phenomenon.pragmatic_pair},
    };
  }

  function taskPayload(current) {
    return {
      task_id: current.task.task.task_id,
      audio_url: current.task.task.audio_url,
      dataset: current.task.task.dataset,
      bundle_id: state.assignment.bundle_id,
      phenomena: current.phenomena.map((phenomenon, index) =>
        phenomenonPayload(current, phenomenon, index)),
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
    persistCurrentTask();
    return {
      schema_version: 'conversation-annotation-v3',
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
      const addTaskError = (message) => {
        errors.push(message);
        if (firstInvalidTask === null) firstInvalidTask = taskIndex;
      };
      const phenomena = task.phenomena || [];
      const segmentIds = new Set(task.segments.map((segment) => segment.segment_id));
      if (!phenomena.length) addTaskError(`Task ${taskIndex + 1}: add at least one phenomenon annotation.`);
      phenomena.forEach((phenomenon, phenomenonIndex) => {
        const prefix = `Task ${taskIndex + 1}, phenomenon ${phenomenonIndex + 1}`;
        if (!phenomenon.phenomenon_type) addTaskError(`${prefix}: select a phenomenon type.`);
        if (phenomenon.phenomenon_type === 'ctc') {
          const ctc = phenomenon.ctc || {};
          if (!ctc.interrupted_segment_id || !ctc.interrupting_segment_id) {
            addTaskError(`${prefix}: select the interrupted and interrupting utterance segments.`);
          } else if (!segmentIds.has(ctc.interrupted_segment_id) || !segmentIds.has(ctc.interrupting_segment_id)) {
            addTaskError(`${prefix}: selected CTC utterance segment no longer exists.`);
          } else if (ctc.interrupted_segment_id === ctc.interrupting_segment_id) {
            addTaskError(`${prefix}: interrupted and interrupting utterances should be different segments.`);
          }
          if (!ctc.speaker_state) addTaskError(`${prefix}: select the CTC speaker state.`);
          if (!ctc.interruption_type) addTaskError(`${prefix}: select the CTC interruption type.`);
          const validInterruptionTypes = (ctcInterruptionTypes[ctc.speaker_state] || [])
            .map(([value]) => value);
          if (ctc.interruption_type && !validInterruptionTypes.includes(ctc.interruption_type)) {
            addTaskError(`${prefix}: interruption type does not match the selected speaker state.`);
          }
          if (isWordPhraseInterruption(ctc.interruption_type) &&
              ctc.word_phrase_fits !== true && ctc.word_phrase_fits !== false &&
              ctc.word_phrase_fits !== 'not_applicable') {
            addTaskError(`${prefix}: answer whether the word/phrase correctly fits the stuck sentence.`);
          }
          if (!ctc.interrupted_speaker || !ctc.interrupter_speaker) {
            addTaskError(`${prefix}: selected segments need valid speakers.`);
          }
          if (ctc.interruption_start === null || ctc.interruption_end === null ||
              ctc.utterance_start === null || ctc.stall_time === null) {
            addTaskError(`${prefix}: selected CTC segments need valid timestamps.`);
          }
          if (ctc.interrupter_becomes_main_speaker === null || ctc.interrupter_becomes_main_speaker === undefined) {
            addTaskError(`${prefix}: answer whether the interrupter becomes the main speaker.`);
          }
          if (ctc.interruption_end !== null && ctc.interruption_start !== null && ctc.interruption_end <= ctc.interruption_start) {
            addTaskError(`${prefix}: CTC interruption end must be after start.`);
          }
          if (ctc.stall_time !== null && ctc.utterance_start !== null && ctc.stall_time <= ctc.utterance_start) {
            addTaskError(`${prefix}: CTC utterance end must be after start.`);
          }
        }
        if (phenomenon.phenomenon_type === 'pragmatic_pair') {
          const pair = phenomenon.pragmatic_pair || {};
          if (!pair.question_segment_id || !pair.response_segment_id) {
            addTaskError(`${prefix}: select the Pragmatic Pair question and response segments.`);
          } else if (!segmentIds.has(pair.question_segment_id) || !segmentIds.has(pair.response_segment_id)) {
            addTaskError(`${prefix}: selected Pragmatic Pair segment no longer exists.`);
          } else if (pair.question_segment_id === pair.response_segment_id) {
            addTaskError(`${prefix}: question and response should be different segments.`);
          }
          if (!pair.question_speaker || !pair.response_speaker) {
            addTaskError(`${prefix}: select Pragmatic Pair question and response speakers.`);
          }
          [
            ['question start', pair.question_start],
            ['question end', pair.question_end],
            ['response start', pair.response_start],
            ['response end', pair.response_end],
          ].forEach(([name, value]) => {
            if (value === null) addTaskError(`${prefix}: enter Pragmatic Pair ${name}.`);
          });
          if (pair.question_start !== null && pair.question_end !== null && pair.question_end <= pair.question_start) {
            addTaskError(`${prefix}: Pragmatic Pair question end must be after start.`);
          }
          if (pair.response_start !== null && pair.response_end !== null && pair.response_end <= pair.response_start) {
            addTaskError(`${prefix}: Pragmatic Pair response end must be after start.`);
          }
        }
      });
      task.segments.forEach((segment, segmentIndex) => {
        if (!segment.transcript) {
          addTaskError(`Task ${taskIndex + 1}, segment ${segmentIndex + 1}: transcript is required.`);
        }
        if (segment.end <= segment.start) {
          addTaskError(`Task ${taskIndex + 1}, segment ${segmentIndex + 1}: start must be before end.`);
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
  [
    'phenomenon-type',
    'ctc-word-phrase-fit',
    'ctc-interrupted-speaker',
    'ctc-interrupter-speaker',
    'ctc-utterance-start',
    'ctc-stall-time',
    'ctc-interruption-start',
    'ctc-interruption-end',
    'ctc-speaker-shift',
    'pp-question-speaker',
    'pp-response-speaker',
    'pp-question-start',
    'pp-question-end',
    'pp-response-start',
    'pp-response-end',
  ].forEach((id) => {
    byId(id).addEventListener('input', savePhenomenon);
    byId(id).addEventListener('change', savePhenomenon);
  });
  byId('add-phenomenon').addEventListener('click', addPhenomenon);
  byId('delete-phenomenon').addEventListener('click', deletePhenomenon);
  byId('ctc-speaker-state').addEventListener('change', () => {
    renderCtcInterruptionOptions(byId('ctc-speaker-state').value);
    syncWordPhraseFitVisibility();
    savePhenomenon();
  });
  byId('ctc-interruption-type').addEventListener('change', () => {
    syncWordPhraseFitVisibility();
    savePhenomenon();
  });
  byId('ctc-interrupted-segment').addEventListener('change', () => {
    const segmentId = byId('ctc-interrupted-segment').value;
    fillCtcInterruptedFromSegment(segmentId);
    savePhenomenon();
    if (segmentId) selectSegment(segmentId);
  });
  byId('ctc-interrupting-segment').addEventListener('change', () => {
    const segmentId = byId('ctc-interrupting-segment').value;
    fillCtcInterruptingFromSegment(segmentId);
    savePhenomenon();
    if (segmentId) selectSegment(segmentId);
  });
  byId('pp-question-segment').addEventListener('change', () => {
    const segmentId = byId('pp-question-segment').value;
    fillPragmaticPairSegment('question', segmentId);
    savePhenomenon();
    if (segmentId) selectSegment(segmentId);
  });
  byId('pp-response-segment').addEventListener('change', () => {
    const segmentId = byId('pp-response-segment').value;
    fillPragmaticPairSegment('response', segmentId);
    savePhenomenon();
    if (segmentId) selectSegment(segmentId);
  });
  byId('transcript').addEventListener('input', saveEditor);
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
