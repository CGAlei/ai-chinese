/**
 * app.js — MDD Frontend Application
 *
 * Responsibilities:
 *  1. Load next card from backend API
 *  2. Render sentence using <ruby>/<rt> markup
 *  3. Stream native audio for word and sentence
 *  4. Capture microphone audio (16 kHz Mono PCM via AudioContext)
 *  5. Connect to Azure Pronunciation Assessment SDK
 *  6. Process word-level results → color each token green/red, reveal pinyin on failures
 *  7. Log attempt to backend /api/log-attempt
 *  8. Manage state transitions (loading → ready → recording → evaluating → result)
 */

// ─── Constants ──────────────────────────────────────────────────────────────

const API = ''; // same origin

// ─── State ──────────────────────────────────────────────────────────────────

let currentCard   = null;
let isRecording   = false;
let audioStream   = null;
let recognizer    = null;
let azureToken    = null;
let azureRegion   = 'eastus';
let pinyinVisible = false;   // whether pinyin is shown on the sentence
let activeTab     = 'sentence'; // 'sentence' | 'word-drill' | 'analytics'

// Word Drill state
let drillPool      = [];   // array of focused word cards
let drillIndex     = 0;    // current position in drillPool
let drillCard      = null; // currently displayed drill word
let drillFilter    = 'all';

// ─── DOM refs ────────────────────────────────────────────────────────────────

const statusDot        = document.getElementById('status-dot');
const statusText       = document.getElementById('status-text');
const demoBanner       = document.getElementById('demo-banner');
const cardLoading      = document.getElementById('card-loading');
const cardContent      = document.getElementById('card-content');
const targetWord       = document.getElementById('target-word');
const targetPinyin     = document.getElementById('target-pinyin');
const btnWordAudio     = document.getElementById('btn-word-audio');
const wordAudioIcon    = document.getElementById('word-audio-icon');
const sentenceDisplay  = document.getElementById('sentence-display');
const btnSentenceAudio = document.getElementById('btn-sentence-audio');
const sentenceAudioIcon= document.getElementById('sentence-audio-icon');
const resultPanel      = document.getElementById('result-panel');
const resultBadge      = document.getElementById('result-badge');
const scorePct         = document.getElementById('score-pct');
const scoreBar         = document.getElementById('score-bar');
const fluencyPct       = document.getElementById('fluency-pct');
const fluencyBar       = document.getElementById('fluency-bar');
const completenessPct  = document.getElementById('completeness-pct');
const completenessBar  = document.getElementById('completeness-bar');
const phonemeFlags     = document.getElementById('phoneme-flags');
const constructiveFeedback = document.getElementById('constructive-feedback');
const nextReviewInfo   = document.getElementById('next-review-info');
const btnRecord        = document.getElementById('btn-record');
const recordIcon       = document.getElementById('record-icon');
const recordHint       = document.getElementById('record-hint');
const btnSkip          = document.getElementById('btn-skip');
const btnNext          = document.getElementById('btn-next');
const btnPinyinToggle  = document.getElementById('btn-pinyin-toggle');
const btnFavoriteCard  = document.getElementById('btn-favorite-card');
const srsFooter        = document.getElementById('srs-footer');
const statReps         = document.getElementById('stat-reps');
const statLapses       = document.getElementById('stat-lapses');
const statEase         = document.getElementById('stat-ease');
const audioWord        = document.getElementById('audio-word');
const audioSentence    = document.getElementById('audio-sentence');
const audioContrast    = document.getElementById('audio-contrast');
const floatingDock     = document.getElementById('floating-dock');

// Tab views
const viewSentence     = document.getElementById('view-sentence');
const viewWordDrill    = document.getElementById('view-word-drill');
const viewAnalytics    = document.getElementById('view-analytics');

// Drill DOM refs
const drillLoading       = document.getElementById('drill-loading');
const drillContent       = document.getElementById('drill-content');
const drillEmpty         = document.getElementById('drill-empty');
const drillTargetWord    = document.getElementById('drill-target-word');
const drillPinyin        = document.getElementById('drill-pinyin');
const drillMeaning       = document.getElementById('drill-meaning');
const drillCharDisplay   = document.getElementById('drill-char-display');
const drillContrastContainer = document.getElementById('drill-contrast-container');
const contrastTargetChar = document.getElementById('contrast-target-char');
const contrastTargetPinyin = document.getElementById('contrast-target-pinyin');
const btnContrastTargetAudio = document.getElementById('btn-contrast-target-audio');
const contrastChar = document.getElementById('contrast-char');
const contrastPinyin = document.getElementById('contrast-pinyin');
const btnContrastAudio = document.getElementById('btn-contrast-audio');
const contrastWordContext = document.getElementById('contrast-word-context');
const drillResultPanel   = document.getElementById('drill-result-panel');
const drillResultBadge   = document.getElementById('drill-result-badge');
const drillScorePct      = document.getElementById('drill-score-pct');
const drillScoreBar      = document.getElementById('drill-score-bar');
const drillFluencyPct    = document.getElementById('drill-fluency-pct');
const drillFluencyBar    = document.getElementById('drill-fluency-bar');
const drillCompletenessPct = document.getElementById('drill-completeness-pct');
const drillCompletenessBar = document.getElementById('drill-completeness-bar');
const drillPhonemeFlags  = document.getElementById('drill-phoneme-flags');
const drillHint          = document.getElementById('drill-hint');
const btnDrillSkip       = document.getElementById('btn-drill-skip');
const btnDrillNext       = document.getElementById('btn-drill-next');
const drillPoolCounter   = document.getElementById('drill-pool-counter');
const analyticsTableBody = document.getElementById('analytics-table-body');
const analyticsSummary   = document.getElementById('analytics-summary');

// ─── Toast helper ────────────────────────────────────────────────────────────

function showToast(msg, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const colors = {
    info:    'bg-surface-700 border-brand-500/30 text-slate-200',
    success: 'bg-emerald-900/80 border-emerald-500/30 text-emerald-200',
    error:   'bg-red-900/80 border-red-500/30 text-red-200',
    warn:    'bg-amber-900/80 border-amber-500/30 text-amber-200',
  };
  const toast = document.createElement('div');
  toast.className = `toast pointer-events-auto glass rounded-xl px-4 py-3 text-sm border max-w-xs text-center ${colors[type] || colors.info}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ─── Status bar helper ───────────────────────────────────────────────────────

function setStatus(type, text) {
  statusDot.className = `status-dot ${type}`;
  statusText.textContent = text;
}

// ─── Audio helpers ───────────────────────────────────────────────────────────

async function playAudio(audioEl, src, iconEl) {
  // User-gesture compliance: only play via explicit button tap
  audioEl.src = src;
  iconEl.textContent = '⏸';
  try {
    await audioEl.play();
  } catch (e) {
    showToast('Audio playback blocked — tap again.', 'warn');
  }
  audioEl.onended = () => { iconEl.textContent = '▶'; };
}

btnWordAudio.addEventListener('click', () => {
  if (activeTab === 'word-drill') {
    if (!drillCard || !drillCard.chineseAudio) return;
    playAudio(audioWord, drillCard.chineseAudio, wordAudioIcon);
  } else {
    if (!currentCard || !currentCard.chineseAudio) return;
    playAudio(audioWord, currentCard.chineseAudio, wordAudioIcon);
  }
});
btnSentenceAudio.addEventListener('click', () => {
  if (!currentCard || !currentCard.sentenceAudio) return;
  playAudio(audioSentence, currentCard.sentenceAudio, sentenceAudioIcon);
});

// ─── Pinyin toggle helpers ────────────────────────────────────────────

/** Updates the toggle button to reflect current pinyinVisible state. */
function updateToggleBtn() {
  if (!btnPinyinToggle) return;
  btnPinyinToggle.textContent = pinyinVisible ? '拼音 ✓' : '拼音';
  btnPinyinToggle.classList.toggle('active', pinyinVisible);
}

/**
 * Show or hide pinyin on ALL sentence tokens.
 * Called by: toggle button, loadCard (reset), showResultPanel (auto-reveal).
 */
function setPinyinVisibility(visible) {
  pinyinVisible = visible;
  sentenceDisplay.querySelectorAll('ruby.word-token').forEach((r) => {
    r.classList.toggle('show-pinyin', visible);
  });
  updateToggleBtn();
}

btnPinyinToggle?.addEventListener('click', () => setPinyinVisibility(!pinyinVisible));

// ─── Sentence renderer ───────────────────────────────────────────────────────

/**
 * Renders a Chinese sentence as a series of <ruby> elements.
 * Each character (or punctuation cluster) becomes one ruby group.
 * Pinyin is stored as a data attribute and revealed by CSS when the
 * ruby element has class "show-pinyin" or "word-fail".
 *
 * We also support multi-character word tokens from Azure's word array.
 * wordPinyinMap: { [hanzi_token]: pinyin_string } built from card pinyin.
 */
function renderSentence(text) {
  sentenceDisplay.innerHTML = '';
  if (!text) return;

  // Split into individual characters preserving punctuation
  const chars = [...text];
  chars.forEach((ch, i) => {
    if (/[\s，。！？、：；""''「」【】()（）…—\-]/.test(ch)) {
      // Punctuation — render as plain text
      const span = document.createElement('span');
      span.className = 'text-slate-400';
      span.textContent = ch;
      sentenceDisplay.appendChild(span);
    } else {
      // Hanzi character — wrap in <ruby>
      const ruby = document.createElement('ruby');
      ruby.dataset.char = ch;
      ruby.dataset.index = i;
      ruby.className = 'word-token mx-px';

      const charSpan = document.createElement('span');
      charSpan.className = 'hanzi-char';
      charSpan.textContent = ch;

      const rt = document.createElement('rt');
      // Pre-populate with toned pinyin from the server-computed map (e.g. "jīng", "fù")
      rt.textContent = (currentCard?.sentencePinyinMap?.[i] || currentCard?.sentencePinyinMap?.[ch]) ?? '';
      if (pinyinVisible) ruby.classList.add('show-pinyin');

      ruby.appendChild(charSpan);
      ruby.appendChild(rt);
      sentenceDisplay.appendChild(ruby);
    }
  });
}

// ─── Card loader ─────────────────────────────────────────────────────────────

async function loadCard() {
  // Reset UI
  resultPanel.classList.add('hidden');
  if (constructiveFeedback) {
    constructiveFeedback.classList.add('hidden');
    constructiveFeedback.textContent = '';
  }
  btnNext.classList.add('hidden');
  btnSkip.disabled = true;
  btnRecord.disabled = true;
  recordHint.textContent = 'Loading card…';
  srsFooter.classList.add('hidden');
  pinyinVisible = false;
  updateToggleBtn();

  cardLoading.classList.remove('hidden');
  cardContent.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/next-card`);
    if (!res.ok) throw new Error(await res.text());
    currentCard = await res.json();

    // Render word
    targetWord.textContent    = currentCard.hanzi;
    targetPinyin.textContent  = currentCard.pinyin || '';
    updateFavoriteBtnState(currentCard.favorited);

    // Render sentence
    renderSentence(currentCard.sentenceText);

    // Render SRS stats
    const srs = currentCard.srs || {};
    statReps.textContent   = srs.reps   ?? 0;
    statLapses.textContent = srs.lapses ?? 0;
    statEase.textContent   = (srs.ease  ?? 2.5).toFixed(2);
    srsFooter.classList.remove('hidden');

    // Demo mode banner
    if (currentCard.isDemoMode) {
      demoBanner.classList.remove('hidden');
    }

    // Show content
    cardLoading.classList.add('hidden');
    cardContent.classList.remove('hidden');
    cardContent.closest('section').classList.add('card-animate');

    // Shadow card UI: hide audio buttons if media is missing
    if (!currentCard.chineseAudio) {
      btnWordAudio.classList.add('hidden');
      btnWordAudio.classList.remove('flex');
    } else {
      btnWordAudio.classList.remove('hidden');
      btnWordAudio.classList.add('flex');
    }

    if (!currentCard.sentenceAudio) {
      btnSentenceAudio.classList.add('hidden');
      btnSentenceAudio.classList.remove('flex');
    } else {
      btnSentenceAudio.classList.remove('hidden');
      btnSentenceAudio.classList.add('flex');
    }

    // Enable controls
    btnSkip.disabled   = false;
    btnRecord.disabled = false;
    recordHint.textContent = 'Tap 🎙️ to record your reading';

    // Prefetch Azure token silently
    fetchAzureToken();

  } catch (err) {
    console.error(err);
    cardLoading.classList.add('hidden');
    showToast('Failed to load card: ' + err.message, 'error');
    setStatus('offline', 'Error');
  }
}

// ─── Azure token exchange ─────────────────────────────────────────────────────

async function fetchAzureToken() {
  try {
    const res = await fetch(`${API}/api/get-azure-token`);
    if (!res.ok) {
      const err = await res.json();
      console.warn('[Azure token]', err.error);
      setStatus('demo', 'Azure key missing');
      return;
    }
    const data = await res.json();
    azureToken  = data.token;
    azureRegion = data.region || 'eastus';
    setStatus('online', 'Azure connected');
  } catch (e) {
    console.warn('[Azure token fetch]', e);
    setStatus('demo', 'No Azure token');
  }
}

// ─── Microphone recording & Azure evaluation ─────────────────────────────────

btnRecord.addEventListener('click', async () => {
  if (isRecording) {
    stopRecording();
  } else {
    await startRecording();
  }
});

async function startRecording() {
  const activeCard = activeTab === 'word-drill' ? drillCard : currentCard;
  if (!activeCard) return;

  // Request mic permission on first tap (user-gesture)
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
  } catch (e) {
    showToast('Microphone permission denied.', 'error');
    return;
  }

  isRecording = true;
  btnRecord.classList.add('record-pulse');
  recordIcon.textContent = '⏹';
  recordHint.textContent = 'Recording… tap to stop';
  btnSkip.disabled = true;

  if (!azureToken) {
    // No Azure — fall back to mock evaluation for UI testing
    showToast('No Azure token — running UI demo.', 'warn');
    setTimeout(() => stopRecording(true), 2500);
    return;
  }

  // ── Azure Pronunciation Assessment ───────────────────────────────
  try {
    const SpeechSDK = window.SpeechSDK;
    const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(azureToken, azureRegion);
    speechConfig.speechRecognitionLanguage = 'zh-CN';

    // Build pronunciation assessment config
    // In word-drill mode, evaluate the isolated word/chengyu only
    const activeCard = activeTab === 'word-drill' ? drillCard : currentCard;
    const referenceText = activeTab === 'word-drill' ? activeCard.hanzi : activeCard.sentenceText;
    const pronConfig = new SpeechSDK.PronunciationAssessmentConfig(
      referenceText,
      SpeechSDK.PronunciationAssessmentGradingSystem.HundredMark,
      SpeechSDK.PronunciationAssessmentGranularity.Phoneme,
      true  // enable miscue
    );
    pronConfig.enableProsodyAssessment = false;
    pronConfig.textNormalization = SpeechSDK?.TextNormalization?.True || "True";
    pronConfig.phonemeAlphabet = "IPA";

    // AudioConfig from live microphone stream
    const audioConfig = SpeechSDK.AudioConfig.fromStreamInput(audioStream);
    recognizer = new SpeechSDK.SpeechRecognizer(speechConfig, audioConfig);
    pronConfig.applyTo(recognizer);

    recognizer.recognizeOnceAsync(
      (result) => {
        stopRecording();
        if (activeTab === 'word-drill') {
          processDrillAzureResult(result);
        } else {
          processAzureResult(result);
        }
      },
      (err) => {
        stopRecording();
        console.error('[Azure recognize]', err);
        showToast('Recognition error — try again.', 'error');
      }
    );
  } catch (e) {
    stopRecording();
    console.error('[Azure setup]', e);
    showToast('Azure SDK error: ' + e.message, 'error');
  }
}

function stopRecording(mockMode = false) {
  isRecording = false;
  btnRecord.classList.remove('record-pulse');
  recordIcon.textContent = '🎙️';
  recordHint.textContent = 'Evaluating…';
  btnSkip.disabled = false;

  if (audioStream) {
    audioStream.getTracks().forEach((t) => t.stop());
    audioStream = null;
  }
  if (recognizer && !mockMode) {
    recognizer.close();
    recognizer = null;
  }

  if (mockMode) {
    processMockResult();
  }
}

// ─── Result processing ───────────────────────────────────────────────────────

function processAzureResult(result) {
  const SpeechSDK = window.SpeechSDK;
  const pronResult = SpeechSDK.PronunciationAssessmentResult.fromResult(result);
  if (!pronResult) {
    showToast('No pronunciation result received.', 'warn');
    recordHint.textContent = 'Tap 🎙️ to try again';
    return;
  }

  const overallScore = pronResult.pronunciationScore / 100; // 0.0–1.0
  const fluencyScore = pronResult.fluencyScore || 0;
  const completenessScore = pronResult.completenessScore || 0;
  const words        = pronResult.detailResult?.Words || [];

  // Map Azure word results onto the DOM tokens
  applyWordColors(words, overallScore);

  // Extract phoneme errors
  let initialError = false;
  let finalError   = false;
  let toneError    = false;
  let azureRaw     = null;

  try {
    azureRaw = JSON.parse(result.properties.getProperty(
      SpeechSDK.PropertyId.SpeechServiceResponse_JsonResult
    ));
    // Walk the phoneme array for any failed phonemes
    for (const word of (azureRaw?.NBest?.[0]?.Words || [])) {
      for (const phoneme of (word.Phonemes || [])) {
        if (phoneme.PronunciationAssessment?.AccuracyScore < 60) {
          // Classify: initials (consonants at start of syllable) vs finals
          // Azure doesn't label initials/finals directly, so we use position heuristic:
          // - If it's the first phoneme of a word and it's a consonant → initial
          // - Otherwise → final
          const phonemeStr = (phoneme.Phoneme || '').toLowerCase();
          const isConsonant = /^[bpmfdtnlgkhjqxzcsryw]/.test(phonemeStr);
          if (isConsonant && word.Phonemes.indexOf(phoneme) === 0) {
            initialError = true;
          } else {
            finalError = true;
          }
        }
      }
      // Check tone from word-level (Tone field in some regions)
      const toneErrorTypes = word.PronunciationAssessment?.Feedback?.Prosody?.Tone?.ErrorTypes;
      if (Array.isArray(toneErrorTypes) && toneErrorTypes.some(e => e !== 'None')) {
        toneError = true;
      }
    }
  } catch (e) {
    console.warn('[Phoneme parsing]', e);
  }

  showResultPanel(overallScore, initialError, finalError, toneError, fluencyScore, completenessScore);
  logAttempt(overallScore, initialError, finalError, toneError, azureRaw);
}

function processMockResult() {
  // Demo mode: generate random plausible scores for UI testing
  const score = 0.4 + Math.random() * 0.55;
  const words = [];
  const tokens = sentenceDisplay.querySelectorAll('ruby.word-token');
  tokens.forEach((ruby) => {
    const wordScore = Math.random();
    words.push({ word: ruby.dataset.char, score: wordScore });
  });
  applyWordColors(words, score, true);
  const mockFluency = 60 + Math.floor(Math.random() * 35);
  const mockCompleteness = 80 + Math.floor(Math.random() * 20);
  showResultPanel(score, Math.random() > 0.7, Math.random > 0.6, Math.random() > 0.5, mockFluency, mockCompleteness);
  logAttempt(score, false, false, false, null);
}

/**
 * Colorizes each word token in the sentence display.
 * @param {Array}   words     — Azure word result array or mock array
 * @param {number}  overall   — overall accuracy 0-1
 * @param {boolean} isMock    — if true, use simplified mock format
 */
function applyWordColors(words, overall, isMock = false) {
  // Reset all ruby classes
  const rubies = sentenceDisplay.querySelectorAll('ruby.word-token');
  rubies.forEach((r) => {
    r.classList.remove('word-excellent', 'word-good', 'word-warning', 'word-critical', 'word-omit', 'show-pinyin');
  });

  // Build a flat list of (text, accuracyScore) pairs
  const wordResults = words.map((w) => {
    if (isMock) return { text: w.word, score: w.score };
    // Azure format
    const acc = w.PronunciationAssessment?.AccuracyScore ?? 100;
    return {
      text:   w.Word || '',
      score:  acc / 100,
      pinyin: w.Phonemes?.map((p) => p.Phoneme).join('') || '',
    };
  });

  // Match Azure words to DOM ruby elements (character-by-character)
  // Azure returns whole words; DOM has individual characters. Align them.
  let rubyIdx = 0;
  const rubyList = Array.from(rubies);

  for (const wr of wordResults) {
    const chars = [...(wr.text || '')];
    for (const ch of chars) {
      // Bounded lookahead: only search the next 3 characters to prevent a single mismatch
      // from exhausting the entire array.
      let foundIdx = -1;
      for (let offset = 0; offset < 3 && rubyIdx + offset < rubyList.length; offset++) {
        if (rubyList[rubyIdx + offset].dataset.char === ch) {
          foundIdx = rubyIdx + offset;
          break;
        }
      }

      if (foundIdx === -1) {
        // Character not found in the immediate next DOM nodes (maybe normalized/miscued).
        // Skip this Azure character and try the next one without advancing rubyIdx.
        continue;
      }

      // Advance rubyIdx to the found index
      rubyIdx = foundIdx;
      
      const ruby = rubyList[rubyIdx];
      if (wr.score >= 0.85) {
        ruby.classList.add('word-excellent');
      } else if (wr.score >= 0.65) {
        ruby.classList.add('word-good');
      } else if (wr.score >= 0.45) {
        ruby.classList.add('word-warning', 'show-pinyin');
      } else {
        ruby.classList.add('word-critical', 'show-pinyin');
      }
      rubyIdx++;
    }
  }

  // After the matching loop, color any remaining unmatched characters as neutral
  rubyList.forEach((ruby) => {
    const hasColor = ['word-excellent','word-good','word-warning','word-critical'].some(c => ruby.classList.contains(c));
    if (!hasColor) {
      ruby.classList.add('word-omit');
    }
  });
}

/**
 * Shows the result panel with score and phoneme flags.
 */
function showResultPanel(score, initialError, finalError, toneError, fluency = 0, completeness = 0) {
  const pct = Math.round(score * 100);
  scorePct.textContent = `${pct}%`;
  scoreBar.style.width = `${pct}%`;

  if (fluencyPct && fluencyBar) {
    const fPct = Math.round(fluency);
    fluencyPct.textContent = `${fPct}%`;
    fluencyBar.style.width = `${fPct}%`;
  }
  if (completenessPct && completenessBar) {
    const cPct = Math.round(completeness);
    completenessPct.textContent = `${cPct}%`;
    completenessBar.style.width = `${cPct}%`;
  }

  // Gradient color shift based on score
  if (pct >= 75) {
    scoreBar.style.background = 'linear-gradient(90deg, #10b981, #34d399)';
  } else if (pct >= 60) {
    scoreBar.style.background = 'linear-gradient(90deg, #0d9488, #2dd4bf)';
  } else if (pct >= 45) {
    scoreBar.style.background = 'linear-gradient(90deg, #d97706, #fbbf24)';
  } else {
    scoreBar.style.background = 'linear-gradient(90deg, #f43f5e, #fda4af)';
  }

  // Badge
  if (pct >= 90) {
    resultBadge.textContent = '完美 🎉';
    resultBadge.className   = 'text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300';
  } else if (pct >= 75) {
    resultBadge.textContent = '很好 👍';
    resultBadge.className   = 'text-xs font-bold px-3 py-1 rounded-full bg-teal-500/20 text-teal-300';
  } else if (pct >= 60) {
    resultBadge.textContent = '及格 ✓';
    resultBadge.className   = 'text-xs font-bold px-3 py-1 rounded-full bg-blue-500/20 text-blue-300';
  } else if (pct >= 45) {
    resultBadge.textContent = '部分正确 🔍';
    resultBadge.className   = 'text-xs font-bold px-3 py-1 rounded-full bg-amber-500/20 text-amber-300';
  } else {
    resultBadge.textContent = '需要练习 🔄';
    resultBadge.className   = 'text-xs font-bold px-3 py-1 rounded-full bg-rose-500/20 text-rose-300';
  }

  // Generate constructive feedback
  if (constructiveFeedback) {
    constructiveFeedback.classList.remove('hidden');
    let feedbackText = '';
    
    if (!initialError && !finalError && !toneError) {
      if (pct >= 90) {
        feedbackText = '完美的发音！你准确地读出了所有声母、韵母和声调。听起来非常自然！';
      } else {
        feedbackText = '发音很棒！整体感觉很流利，声母和韵母的结合也非常协调。';
      }
    } else {
      const positives = [];
      if (!initialError) positives.push('声母（辅音）清晰');
      if (!finalError) positives.push('韵母（元音）饱满');
      if (!toneError) positives.push('声调控制得当');

      let positiveSection = '';
      if (positives.length > 0) {
        positiveSection = `优秀部分：${positives.join('，')}。`;
      }

      const tips = [];
      if (initialError) tips.push('可以更多注意声母发音位置（如平翘舌音、送气对比等）');
      if (finalError) tips.push('韵母收尾时可以更完整（注意前后鼻音的微调）');
      if (toneError) tips.push('多留意声调的走势起伏，特别注意阴平、阳平、上声和去声的区别');

      let tipsSection = `优化小建议：${tips.join('；')}。`;
      
      feedbackText = `${positiveSection ? positiveSection + ' ' : ''}${tipsSection}`;
    }
    constructiveFeedback.textContent = feedbackText;
  }

  // Phoneme error flags
  phonemeFlags.innerHTML = '';
  const flags = [
    { label: '声母错误', error: initialError, color: 'bg-red-500/20 text-red-300 border-red-500/30' },
    { label: '韵母错误', error: finalError,   color: 'bg-orange-500/20 text-orange-300 border-orange-500/30' },
    { label: '声调错误', error: toneError,    color: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' },
  ];
  for (const f of flags) {
    if (f.error) {
      const pill = document.createElement('span');
      pill.className = `px-2 py-1 rounded-lg border text-xs font-medium ${f.color}`;
      pill.textContent = f.label;
      phonemeFlags.appendChild(pill);
    }
  }
  if (!initialError && !finalError && !toneError && pct >= 60) {
    const pill = document.createElement('span');
    pill.className = 'px-2 py-1 rounded-lg border text-xs font-medium bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
    pill.textContent = '发音正确 ✓';
    phonemeFlags.appendChild(pill);
  }

  resultPanel.classList.remove('hidden');
  btnNext.classList.remove('hidden');
  recordHint.textContent = 'Tap 🎙️ to try again or tap Next';
  // Auto-reveal pinyin for ALL characters after any evaluation
  setPinyinVisibility(true);
}

/**
 * POST attempt data to the backend.
 */
async function logAttempt(score, initialError, finalError, toneError, azureRaw) {
  if (!currentCard) return;
  try {
    const res = await fetch(`${API}/api/log-attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word_id:            currentCard.id,
        primary_hanzi_text: currentCard.hanzi,   // lets backend exclude target from secondary scan
        sentence:           currentCard.sentenceText,
        accuracy_score:     score,
        initial_error:      initialError,
        final_error:        finalError,
        tone_error:         toneError,
        azure_raw:          azureRaw,
      }),
    });
    const data = await res.json();
    if (data.next_srs) {
      const d = data.next_srs;
      const dueDate = new Date(d.due);
      const daysUntil = Math.round((d.due - Date.now()) / 86400000);
      nextReviewInfo.textContent =
        `下次复习: ${daysUntil <= 0 ? '今天' : daysUntil + ' 天后'} | 难度: ${d.ease.toFixed(2)} | 复习: ${d.reps}`;
      // Update SRS footer
      statReps.textContent   = d.reps;
      statLapses.textContent = d.lapses;
      statEase.textContent   = d.ease.toFixed(2);
    }
  } catch (e) {
    console.error('[log-attempt]', e);
  }
}

// ─── Navigation ──────────────────────────────────────────────────────────────

btnSkip.addEventListener('click', () => {
  if (!currentCard) return;
  loadCard();
});

btnNext.addEventListener('click', () => {
  loadCard();
});

// ─── Favorite button toggling ────────────────────────────────────────────────

function updateFavoriteBtnState(isFavorited) {
  if (!btnFavoriteCard) return;
  if (isFavorited) {
    btnFavoriteCard.textContent = '★';
    btnFavoriteCard.classList.remove('text-slate-400');
    btnFavoriteCard.classList.add('text-amber-400');
  } else {
    btnFavoriteCard.textContent = '☆';
    btnFavoriteCard.classList.remove('text-amber-400');
    btnFavoriteCard.classList.add('text-slate-400');
  }
}

btnFavoriteCard?.addEventListener('click', async () => {
  if (!currentCard) return;
  try {
    const res = await fetch(`${API}/api/toggle-favorite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word_id: currentCard.id })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    currentCard.favorited = data.favorited;
    updateFavoriteBtnState(currentCard.favorited);
    showToast(currentCard.favorited ? '❤️ Added to favorites' : '🤍 Removed from favorites', 'success', 1500);
  } catch (err) {
    console.error('[toggle-favorite]', err);
    showToast('Failed to toggle favorite: ' + err.message, 'error');
  }
});

// ─── Tab switching ───────────────────────────────────────────────────────────

const tabBtns = document.querySelectorAll('.tab-btn');
const views = { sentence: viewSentence, 'word-drill': viewWordDrill, analytics: viewAnalytics };

function switchTab(tabName) {
  activeTab = tabName;
  tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
  Object.entries(views).forEach(([k, v]) => {
    if (v) v.classList.toggle('hidden', k !== tabName);
  });

  // Show/hide floating dock — only visible in sentence & word-drill tabs
  if (floatingDock) {
    floatingDock.classList.toggle('hidden', tabName === 'analytics');
  }

  // Restore audio button state when returning to sentence mode
  if (tabName === 'sentence' && currentCard) {
    if (currentCard.chineseAudio) {
      btnWordAudio.classList.remove('hidden');
      btnWordAudio.classList.add('flex');
    } else {
      btnWordAudio.classList.add('hidden');
      btnWordAudio.classList.remove('flex');
    }
    if (currentCard.sentenceAudio) {
      btnSentenceAudio.classList.remove('hidden');
      btnSentenceAudio.classList.add('flex');
    } else {
      btnSentenceAudio.classList.add('hidden');
      btnSentenceAudio.classList.remove('flex');
    }
  }

  // When entering a tab, trigger its data load
  if (tabName === 'word-drill') loadDrillPool();
  if (tabName === 'analytics') loadAnalytics();
}

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ─── Word Drill functions ────────────────────────────────────────────────────

// Filter pill listeners
document.querySelectorAll('.filter-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    drillFilter = pill.dataset.filter;
    loadDrillPool();
  });
});

async function loadDrillPool() {
  drillLoading.classList.remove('hidden');
  drillContent.classList.add('hidden');
  drillEmpty.classList.add('hidden');
  drillResultPanel.classList.add('hidden');
  btnDrillNext.classList.add('hidden');
  drillHint.textContent = 'Loading drill pool…';

  try {
    const res = await fetch(`${API}/api/focused-pool?filter=${drillFilter}`);
    drillPool = await res.json();
    drillIndex = 0;

    if (drillPool.length === 0) {
      drillLoading.classList.add('hidden');
      drillEmpty.classList.remove('hidden');
      drillHint.textContent = '';
      btnDrillSkip.disabled = true;
      btnRecord.disabled = true;
      drillPoolCounter.textContent = '';
      return;
    }

    showDrillCard();
    fetchAzureToken();
  } catch (err) {
    console.error('[loadDrillPool]', err);
    showToast('Failed to load drill pool.', 'error');
  }
}

function showDrillCard() {
  if (drillIndex >= drillPool.length) drillIndex = 0;
  drillCard = drillPool[drillIndex];

  drillResultPanel.classList.add('hidden');
  btnDrillNext.classList.add('hidden');
  drillCharDisplay.classList.add('hidden');
  drillCharDisplay.innerHTML = '';
  
  if (drillContrastContainer) {
    drillContrastContainer.classList.add('hidden');
  }

  drillTargetWord.textContent = drillCard.hanzi;
  drillPinyin.textContent = drillCard.pinyin || '';
  drillMeaning.textContent = drillCard.meaning || '';

  drillLoading.classList.add('hidden');
  drillEmpty.classList.add('hidden');
  drillContent.classList.remove('hidden');

  drillHint.textContent = 'Tap 🎙️ — pronounce the word only';
  btnDrillSkip.disabled = false;
  btnRecord.disabled = false;
  drillPoolCounter.textContent = `${drillIndex + 1} / ${drillPool.length}`;

  // Show word audio button, hide sentence audio in drill mode
  if (drillCard.chineseAudio) {
    btnWordAudio.classList.remove('hidden');
    btnWordAudio.classList.add('flex');
  } else {
    btnWordAudio.classList.add('hidden');
    btnWordAudio.classList.remove('flex');
  }
  btnSentenceAudio.classList.add('hidden');
  btnSentenceAudio.classList.remove('flex');

  // Trigger contrast check asynchronously
  loadMinimalPairForDrill(drillCard);
}

async function loadMinimalPairForDrill(card) {
  if (!drillContrastContainer) return;
  drillContrastContainer.classList.add('hidden');

  // Determine primary error type
  let errorType = 'tone';
  if (card.total_shengmu_errors > card.total_tone_errors && card.total_shengmu_errors > card.total_yunmu_errors) {
    errorType = 'shengmu';
  } else if (card.total_yunmu_errors > card.total_tone_errors && card.total_yunmu_errors > card.total_shengmu_errors) {
    errorType = 'yunmu';
  } else if (card.total_tone_errors > 0) {
    errorType = 'tone';
  } else if (card.total_shengmu_errors > 0) {
    errorType = 'shengmu';
  } else if (card.total_yunmu_errors > 0) {
    errorType = 'yunmu';
  }

  try {
    const res = await fetch(`${API}/api/minimal-pair?hanzi=${encodeURIComponent(card.hanzi)}&error_type=${errorType}`);
    if (!res.ok) {
      // Try alt error types if the primary check yielded no results
      const alts = [];
      if (errorType !== 'tone' && card.total_tone_errors > 0) alts.push('tone');
      if (errorType !== 'shengmu' && card.total_shengmu_errors > 0) alts.push('shengmu');
      if (errorType !== 'yunmu' && card.total_yunmu_errors > 0) alts.push('yunmu');

      for (const alt of alts) {
        const altRes = await fetch(`${API}/api/minimal-pair?hanzi=${encodeURIComponent(card.hanzi)}&error_type=${alt}`);
        if (altRes.ok) {
          const data = await altRes.json();
          displayMinimalPair(data, card);
          return;
        }
      }
      return;
    }

    const data = await res.json();
    displayMinimalPair(data, card);
  } catch (err) {
    console.warn('[loadMinimalPairForDrill] failed', err);
  }
}

function displayMinimalPair(result, card) {
  contrastTargetChar.textContent = result.targetChar;
  contrastTargetPinyin.textContent = result.targetPinyin;
  contrastChar.textContent = result.contrastChar;
  contrastPinyin.textContent = result.contrastPinyin;
  contrastWordContext.textContent = result.contrastCard ? `在“${result.contrastCard.hanzi}”中` : '';

  // Play controls
  btnContrastTargetAudio.onclick = (e) => {
    e.stopPropagation();
    if (card.chineseAudio) {
      playAudio(audioWord, card.chineseAudio, null);
    }
  };

  btnContrastAudio.onclick = (e) => {
    e.stopPropagation();
    if (result.contrastCard && result.contrastCard.chineseAudio) {
      playAudio(audioContrast, result.contrastCard.chineseAudio, null);
    }
  };

  btnContrastTargetAudio.style.display = card.chineseAudio ? 'inline-block' : 'none';
  btnContrastAudio.style.display = (result.contrastCard && result.contrastCard.chineseAudio) ? 'inline-block' : 'none';

  drillContrastContainer.classList.remove('hidden');
}

btnDrillSkip.addEventListener('click', () => {
  drillIndex++;
  showDrillCard();
});

btnDrillNext.addEventListener('click', () => {
  drillIndex++;
  showDrillCard();
});

/** Process Azure result specifically for the word drill mode */
function processDrillAzureResult(result) {
  const SpeechSDK = window.SpeechSDK;
  const pronResult = SpeechSDK.PronunciationAssessmentResult.fromResult(result);
  if (!pronResult) {
    showToast('No pronunciation result.', 'warn');
    drillHint.textContent = 'Tap 🎙️ to try again';
    return;
  }

  const overallScore = pronResult.pronunciationScore / 100;
  const fluencyScore = pronResult.fluencyScore || 0;
  const completenessScore = pronResult.completenessScore || 0;
  const words = pronResult.detailResult?.Words || [];

  // Color each character of the drill word
  drillCharDisplay.innerHTML = '';
  const chars = [...(drillCard.hanzi || '')];
  // Flatten all phoneme-level data from Azure words
  let charIdx = 0;
  for (const w of words) {
    const wChars = [...(w.Word || '')];
    const wScore = (w.PronunciationAssessment?.AccuracyScore ?? 100) / 100;
    for (const ch of wChars) {
      if (charIdx < chars.length) {
        const span = document.createElement('span');
        span.className = 'font-hanzi text-5xl md:text-6xl transition-colors';
        span.textContent = chars[charIdx];
        span.style.color = wScore >= 0.50 ? '#34d399' : '#f87171';
        drillCharDisplay.appendChild(span);
        charIdx++;
      }
    }
  }
  // Fill remaining chars as omit
  while (charIdx < chars.length) {
    const span = document.createElement('span');
    span.className = 'font-hanzi text-5xl md:text-6xl';
    span.textContent = chars[charIdx];
    span.style.color = '#94a3b8';
    drillCharDisplay.appendChild(span);
    charIdx++;
  }
  drillCharDisplay.classList.remove('hidden');

  // Show drill result panel
  const pct = Math.round(overallScore * 100);
  drillScorePct.textContent = `${pct}%`;
  drillScoreBar.style.width = `${pct}%`;

  if (drillFluencyPct && drillFluencyBar) {
    const fPct = Math.round(fluencyScore);
    drillFluencyPct.textContent = `${fPct}%`;
    drillFluencyBar.style.width = `${fPct}%`;
  }
  if (drillCompletenessPct && drillCompletenessBar) {
    const cPct = Math.round(completenessScore);
    drillCompletenessPct.textContent = `${cPct}%`;
    drillCompletenessBar.style.width = `${cPct}%`;
  }

  if (pct >= 75) {
    drillScoreBar.style.background = 'linear-gradient(90deg, #059669, #34d399)';
    drillResultBadge.textContent = '很好 👍';
    drillResultBadge.className = 'text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300';
  } else if (pct >= 50) {
    drillScoreBar.style.background = 'linear-gradient(90deg, #d97706, #fbbf24)';
    drillResultBadge.textContent = '加油 💪';
    drillResultBadge.className = 'text-xs font-bold px-3 py-1 rounded-full bg-amber-500/20 text-amber-300';
  } else {
    drillScoreBar.style.background = 'linear-gradient(90deg, #b91c1c, #f87171)';
    drillResultBadge.textContent = '再试 🔄';
    drillResultBadge.className = 'text-xs font-bold px-3 py-1 rounded-full bg-red-500/20 text-red-300';
  }

  drillResultPanel.classList.remove('hidden');
  btnDrillNext.classList.remove('hidden');
  drillHint.textContent = 'Tap 🎙️ to retry or tap 下一词';

  // Log the attempt using the drill card's ID
  let azureRaw = null;
  try {
    azureRaw = JSON.parse(result.properties.getProperty(
      SpeechSDK.PropertyId.SpeechServiceResponse_JsonResult
    ));
  } catch (_) {}

  logAttemptGeneric(drillCard.id, drillCard.hanzi, drillCard.hanzi, overallScore, false, false, false, azureRaw);
}

/** Generic attempt logger usable by both sentence and drill modes */
async function logAttemptGeneric(wordId, hanzi, sentence, score, initErr, finErr, toneErr, azureRaw) {
  try {
    await fetch(`${API}/api/log-attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word_id: wordId,
        primary_hanzi_text: hanzi,
        sentence: sentence,
        accuracy_score: score,
        initial_error: initErr,
        final_error: finErr,
        tone_error: toneErr,
        azure_raw: azureRaw,
      }),
    });
  } catch (e) {
    console.error('[logAttemptGeneric]', e);
  }
}

// ─── Analytics functions ─────────────────────────────────────────────────────

async function loadAnalytics() {
  analyticsTableBody.innerHTML = '<tr><td colspan="9" class="text-center text-slate-500 text-sm py-8">正在加载…</td></tr>';

  try {
    const res = await fetch(`${API}/api/analytics/top-words`);
    const rows = await res.json();

    if (rows.length === 0) {
      analyticsTableBody.innerHTML = '<tr><td colspan="9" class="text-center text-slate-500 text-sm py-8">还没有学习数据。先去练习吧！</td></tr>';
      analyticsSummary.innerHTML = '';
      return;
    }

    analyticsTableBody.innerHTML = rows.map((r, i) => {
      const acc = (r.avg_accuracy * 100).toFixed(1);
      const coeff = r.error_coefficient.toFixed(2);
      const accColor = r.avg_accuracy >= 0.7 ? 'text-emerald-400' : r.avg_accuracy >= 0.4 ? 'text-amber-400' : 'text-red-400';
      return `<tr>
        <td class="text-slate-500">${i + 1}</td>
        <td class="font-hanzi text-lg text-white">${r.hanzi}</td>
        <td class="text-brand-400 text-xs">${r.pinyin}</td>
        <td>${r.total_attempts}</td>
        <td class="${accColor} font-medium">${acc}%</td>
        <td class="${r.total_shengmu_errors > 0 ? 'text-red-400' : ''}">${r.total_shengmu_errors}</td>
        <td class="${r.total_yunmu_errors > 0 ? 'text-orange-400' : ''}">${r.total_yunmu_errors}</td>
        <td class="${r.total_tone_errors > 0 ? 'text-yellow-400' : ''}">${r.total_tone_errors}</td>
        <td class="text-brand-300 font-semibold">${coeff}</td>
      </tr>`;
    }).join('');

    // Summary cards
    const totalAttempts = rows.reduce((s, r) => s + r.total_attempts, 0);
    const avgAcc = rows.reduce((s, r) => s + r.avg_accuracy, 0) / rows.length;
    const totalShengmu = rows.reduce((s, r) => s + r.total_shengmu_errors, 0);
    const totalYunmu = rows.reduce((s, r) => s + r.total_yunmu_errors, 0);

    analyticsSummary.innerHTML = `
      <div class="glass rounded-xl p-3 text-center">
        <p class="text-white font-semibold text-lg">${totalAttempts}</p>
        <p class="text-xs text-slate-500">总练习次数</p>
      </div>
      <div class="glass rounded-xl p-3 text-center">
        <p class="text-white font-semibold text-lg">${(avgAcc * 100).toFixed(1)}%</p>
        <p class="text-xs text-slate-500">平均精度</p>
      </div>
      <div class="glass rounded-xl p-3 text-center">
        <p class="text-red-400 font-semibold text-lg">${totalShengmu}</p>
        <p class="text-xs text-slate-500">声母错误</p>
      </div>
      <div class="glass rounded-xl p-3 text-center">
        <p class="text-orange-400 font-semibold text-lg">${totalYunmu}</p>
        <p class="text-xs text-slate-500">韵母错误</p>
      </div>
    `;
  } catch (err) {
    console.error('[loadAnalytics]', err);
    analyticsTableBody.innerHTML = '<tr><td colspan="9" class="text-center text-red-400 text-sm py-8">加载失败</td></tr>';
  }
}

document.getElementById('btn-refresh-analytics')?.addEventListener('click', loadAnalytics);

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  setStatus('offline', 'Connecting…');

  try {
    const res = await fetch(`${API}/api/health`);
    const data = await res.json();
    setStatus('online', `${data.totalActiveCards} cards`);
  } catch (e) {
    setStatus('offline', 'Server offline');
    showToast('Cannot reach server at localhost:3000', 'error');
    return;
  }

  await loadCard();
}

init();
