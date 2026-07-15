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

  const phenomenonLabels = {
    ctc: 'Collaborative Turn Completion (CTC)',
    pragmatic_pair: 'Pragmatic Pair',
    not_target: 'CTC or Pragmatic Pair not found',
  };

  const ctcStateLabels = {
    stalled: 'Speaker is stuck',
    not_stalled_projection: 'Speaker is not stuck',
  };

  const ctcTypeLabels = {
    word_phrase_confident: 'Word/phrase (confident)',
    word_phrase_unsure: 'Word/phrase (guess/unsure)',
    guiding_question: 'Guiding question',
    buzz_in: 'Buzz-in',
  };

  function primaryHumanLabel(item) {
    const types = (item.human.phenomena || []).map((phenomenon) => phenomenon.phenomenon_type);
    if (types.includes('ctc')) return 'ctc';
    if (types.includes('pragmatic_pair')) return 'pragmatic_pair';
    if (types.includes('not_target')) return 'not_target';
    return types[0] || '';
  }

  function humanHasCtc(item) {
    return (item.human.phenomena || []).some((phenomenon) => phenomenon.phenomenon_type === 'ctc');
  }

  function llmIsCtc(item) {
    return (item.llm_candidates || []).some((candidate) => candidate.pred_is_ctc === true);
  }

  function badge(text, kind = '') {
    return `<span class="review-badge ${kind}">${escapeText(text)}</span>`;
  }

  function channelLabel(channel) {
    return Number(channel) === 0 ? 'Left' : 'Right';
  }

  function segmentById(item) {
    return new Map((item.human.segments || []).map((segment) => [segment.segment_id, segment]));
  }

  function segmentLine(segment) {
    if (!segment) return '<span class="muted">No segment selected</span>';
    return `
      <span class="${Number(segment.channel) === 0 ? 'left' : 'right'}">${channelLabel(segment.channel)}</span>
      ${fmt(segment.start)}-${fmt(segment.end)}
      <span class="muted">${escapeText(segment.transcript)}</span>`;
  }

  function humanPhenomenonHtml(item, phenomenon, index) {
    const segments = segmentById(item);
    const type = phenomenon.phenomenon_type;
    if (type === 'ctc') {
      const ctc = phenomenon.ctc || {};
      const fit = ctc.word_phrase_fits === true
        ? 'Yes'
        : ctc.word_phrase_fits === false
          ? 'No'
          : 'Not applicable';
      return `
        <article class="review-label-card">
          <h3>${index + 1}. ${escapeText(phenomenonLabels[type] || type)}</h3>
          <div class="review-kv">
            <strong>Speaker state</strong><span>${escapeText(ctcStateLabels[ctc.speaker_state] || ctc.speaker_state)}</span>
            <strong>Interruption type</strong><span>${escapeText(ctcTypeLabels[ctc.interruption_type] || ctc.interruption_type)}</span>
            <strong>Word/phrase fits</strong><span>${escapeText(fit)}</span>
            <strong>Interrupter becomes main</strong><span>${ctc.interrupter_becomes_main_speaker === true ? 'Yes' : ctc.interrupter_becomes_main_speaker === false ? 'No' : 'Unanswered'}</span>
          </div>
          <p><b>Interrupted:</b><br>${segmentLine(segments.get(ctc.interrupted_segment_id))}</p>
          <p><b>Interrupting:</b><br>${segmentLine(segments.get(ctc.interrupting_segment_id))}</p>
        </article>`;
    }
    if (type === 'pragmatic_pair') {
      const pair = phenomenon.pragmatic_pair || {};
      return `
        <article class="review-label-card">
          <h3>${index + 1}. ${escapeText(phenomenonLabels[type] || type)}</h3>
          <p><b>Prompt / question:</b><br>${segmentLine(segments.get(pair.question_segment_id))}</p>
          <p><b>Response:</b><br>${segmentLine(segments.get(pair.response_segment_id))}</p>
        </article>`;
    }
    return `
      <article class="review-label-card">
        <h3>${index + 1}. ${escapeText(phenomenonLabels[type] || type || 'Unlabeled')}</h3>
      </article>`;
  }

  function llmCandidateHtml(candidate, index) {
    const verdict = candidate.pred_is_ctc ? badge('LLM: CTC', 'good') : badge('LLM: non-CTC', 'neutral');
    const textVerdict = candidate.text_pred_is_ctc === true
      ? badge('Text: CTC', 'good')
      : candidate.text_pred_is_ctc === false
        ? badge('Text: non-CTC', 'neutral')
        : '';
    const audioVerify = candidate.audio_verify
      ? badge(`Audio verify: ${candidate.audio_verify.verify_confidence || 'available'}`, 'neutral')
      : '';
    return `
      <article class="review-label-card">
        <h3>${index + 1}. ${verdict} ${textVerdict} ${audioVerify}</h3>
        <div class="review-kv">
          <strong>Confidence</strong><span>${escapeText(candidate.pred_confidence || '')}</span>
          <strong>Completion target</strong><span>${escapeText(candidate.pred_completion_target || '')}</span>
          <strong>Error type if non-CTC</strong><span>${escapeText(candidate.pred_error_type_if_not_ctc || '')}</span>
          <strong>Speakers</strong><span>${escapeText(candidate.victim_id)} -> ${escapeText(candidate.interrupter_id)}</span>
        </div>
        <p><b>Main speaker before interruption:</b><br>${escapeText(candidate.main_speaker_pre_interrupt_transcript || candidate.victim_text || '')}</p>
        <p><b>Interrupter after start:</b><br>${escapeText(candidate.interrupter_post_start_utterance || candidate.interrupter_text || '')}</p>
        <p><b>Reasoning:</b><br>${escapeText(candidate.pred_reasoning || '')}</p>
        <p class="muted">${escapeText(candidate.source_file)}:${escapeText(candidate.line_number)} · ${escapeText(candidate.candidate_key)}</p>
      </article>`;
  }

  function renderLabels(item) {
    const humanCtc = humanHasCtc(item);
    const llmCtc = llmIsCtc(item);
    const agreement = humanCtc === llmCtc
      ? badge('Binary CTC agreement', 'good')
      : badge('Binary CTC disagreement', 'bad');
    byId('human-labels').innerHTML = `
      <p>${badge(`Primary: ${phenomenonLabels[primaryHumanLabel(item)] || primaryHumanLabel(item) || 'Unlabeled'}`, 'neutral')} ${agreement}</p>
      ${(item.human.phenomena || []).map(humanPhenomenonHtml.bind(null, item)).join('') || '<p class="muted">No human phenomena found.</p>'}`;
    byId('llm-labels').innerHTML = (item.llm_candidates || []).length
      ? item.llm_candidates.map(llmCandidateHtml).join('')
      : '<p class="muted">No exact LLM auto-label candidate found for this clip.</p>';
  }

  function renderSegments(item) {
    byId('review-segments-list').innerHTML = (item.human.segments || []).map((segment) => `
      <div class="review-segment-row">
        <strong class="${Number(segment.channel) === 0 ? 'left' : 'right'}">${channelLabel(segment.channel)}</strong>
        <span>${fmt(segment.start)}-${fmt(segment.end)}</span>
        <span>${escapeText(segment.transcript)}</span>
      </div>`).join('');
  }

  function destroyWave() {
    if (state.wave) state.wave.destroy();
    state.wave = null;
    state.regions = null;
    byId('review-waveform').innerHTML = '';
  }

  function addRegion(id, start, end, channelIdx, color, content) {
    if (!state.regions || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
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

  function addHumanRegions(item) {
    const segments = segmentById(item);
    (item.human.phenomena || []).forEach((phenomenon, index) => {
      if (phenomenon.phenomenon_type === 'ctc') {
        const ctc = phenomenon.ctc || {};
        const interrupted = segments.get(ctc.interrupted_segment_id);
        const interrupting = segments.get(ctc.interrupting_segment_id);
        if (interrupted) addRegion(
          `human-${index}-interrupted`,
          Number(interrupted.start),
          Number(interrupted.end),
          Number(interrupted.channel),
          'rgba(31, 119, 180, 0.28)',
          `H${index + 1} interrupted`,
        );
        if (interrupting) addRegion(
          `human-${index}-interrupting`,
          Number(interrupting.start),
          Number(interrupting.end),
          Number(interrupting.channel),
          'rgba(255, 127, 14, 0.28)',
          `H${index + 1} interrupting`,
        );
      }
      if (phenomenon.phenomenon_type === 'pragmatic_pair') {
        const pair = phenomenon.pragmatic_pair || {};
        const question = segments.get(pair.question_segment_id);
        const response = segments.get(pair.response_segment_id);
        if (question) addRegion(
          `human-${index}-question`,
          Number(question.start),
          Number(question.end),
          Number(question.channel),
          'rgba(31, 119, 180, 0.24)',
          `H${index + 1} prompt`,
        );
        if (response) addRegion(
          `human-${index}-response`,
          Number(response.start),
          Number(response.end),
          Number(response.channel),
          'rgba(255, 127, 14, 0.24)',
          `H${index + 1} response`,
        );
      }
    });
  }

  function addLlmRegions(item) {
    (item.llm_candidates || []).forEach((candidate, index) => {
      const interrupted = candidate.regions && candidate.regions.interrupted;
      const interrupting = candidate.regions && candidate.regions.interrupting;
      if (interrupted) addRegion(
        `llm-${index}-interrupted`,
        Number(interrupted.start),
        Number(interrupted.end),
        0,
        'rgba(20, 184, 166, 0.24)',
        `L${index + 1} main`,
      );
      if (interrupting) addRegion(
        `llm-${index}-interrupting`,
        Number(interrupting.start),
        Number(interrupting.end),
        1,
        'rgba(132, 204, 22, 0.24)',
        `L${index + 1} intr`,
      );
    });
  }

  function wireWave(item) {
    destroyWave();
    if (!window.WaveSurfer || !WaveSurfer.Regions) {
      byId('review-wave-status').textContent = 'Waveform status: WaveSurfer library is unavailable.';
      return;
    }
    byId('review-wave-status').textContent = 'Waveform status: loading WAV data...';
    const regions = WaveSurfer.Regions.create();
    const wave = WaveSurfer.create({
      container: '#review-waveform',
      media: byId('review-audio'),
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
      byId('review-wave-status').textContent = 'Waveform status: ready.';
      addHumanRegions(item);
      addLlmRegions(item);
    });
    wave.on('error', (error) => {
      byId('review-wave-status').textContent = `Waveform status: audio decode/render error: ${error}`;
    });
  }

  function renderItem(index) {
    if (!state.filtered.length) return;
    state.index = Math.max(0, Math.min(index, state.filtered.length - 1));
    const item = state.filtered[state.index];
    byId('review-task-title').textContent = item.task_id;
    byId('review-task-meta').textContent =
      `Clip ${fmt(item.clip_start)}-${fmt(item.clip_end)} original timeline · ` +
      `submission ${item.submission_file} · duplicate submissions for this audio: ${item.duplicate_submission_count}`;
    byId('item-position').textContent = `${state.index + 1} of ${state.filtered.length}`;
    byId('prev-item').disabled = state.index === 0;
    byId('next-item').disabled = state.index === state.filtered.length - 1;
    byId('item-select').value = item.task_id;
    byId('review-audio').src = item.audio_url;
    renderLabels(item);
    renderSegments(item);
    wireWave(item);
  }

  function applyFilter() {
    const filter = byId('review-filter').value;
    state.filtered = state.items.filter((item) => {
      const primary = primaryHumanLabel(item);
      const humanCtc = humanHasCtc(item);
      const llmCtc = llmIsCtc(item);
      if (filter === 'disagree') return humanCtc !== llmCtc;
      if (filter === 'human_ctc') return primary === 'ctc';
      if (filter === 'human_pp') return primary === 'pragmatic_pair';
      if (filter === 'human_not_target') return primary === 'not_target';
      if (filter === 'llm_ctc') return llmCtc;
      if (filter === 'llm_non_ctc') return !llmCtc;
      return true;
    });
    renderItemSelect();
    renderItem(0);
  }

  function renderItemSelect() {
    const select = byId('item-select');
    select.replaceChildren();
    state.filtered.forEach((item, index) => {
      const human = primaryHumanLabel(item) || 'unlabeled';
      const llm = llmIsCtc(item) ? 'LLM CTC' : 'LLM non-CTC';
      select.append(new Option(`${index + 1}. ${item.task_id} | ${human} | ${llm}`, item.task_id));
    });
    if (!state.filtered.length) {
      select.append(new Option('No clips match this filter', ''));
    }
  }

  async function init() {
    const response = await fetch('/api/review');
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error((payload.errors || ['Unable to load review data.']).join(' '));
    }
    state.items = payload.items || [];
    state.filtered = state.items;
    byId('review-summary').textContent =
      `${payload.summary.items} unique submitted clips · ` +
      `${payload.summary.submission_files} submission files · ` +
      `${payload.summary.auto_candidates} LLM candidates`;
    byId('review-loading').hidden = true;
    byId('review-app').hidden = false;
    renderItemSelect();
    renderItem(0);
  }

  byId('prev-item').addEventListener('click', () => renderItem(state.index - 1));
  byId('next-item').addEventListener('click', () => renderItem(state.index + 1));
  byId('review-filter').addEventListener('change', applyFilter);
  byId('item-select').addEventListener('change', () => {
    const index = state.filtered.findIndex((item) => item.task_id === byId('item-select').value);
    if (index >= 0) renderItem(index);
  });

  init().catch((error) => {
    byId('review-message').textContent = error.message;
    byId('review-loading').classList.add('errors');
  });
})();
