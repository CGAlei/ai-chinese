/**
 * ZenHanzi - Audio SRS Trainer
 * Refactored Modular Version - FSM & MediaController
 * Engine: Vosk + WebSpeech Fallback
 */

// ============================
// 1. GLOBAL UTILITIES
// ============================
const Utils = {
  $(id) { return document.getElementById(id); },
  safe(fn) { try { fn(); } catch (e) { console.error(e); } },
  normalizeText(text) {
    if (!text) return '';
    return text.toLowerCase().trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w\s]/g, "");
  },
  shuffleArray(arr) {
    if (!arr || arr.length === 0) return arr;
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  },
  levenshtein(a, b) {
    if (a.length === 0) return b.length;
    if (b.length === 0) return a.length;
    const matrix = [];
    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
    for (let i = 1; i <= b.length; i++) {
      for (let j = 1; j <= a.length; j++) {
        if (b.charAt(i - 1) === a.charAt(j - 1)) {
          matrix[i][j] = matrix[i - 1][j - 1];
        } else {
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1, // substitution
            matrix[i][j - 1] + 1,     // insertion
            matrix[i - 1][j] + 1      // deletion
          );
        }
      }
    }
    return matrix[b.length][a.length];
  },
  matchMeaning(spoken, validList) {
    return validList.some(valid => {
      // Direct exact match or substring match (for filler words)
      if (spoken === valid || spoken.startsWith(valid + " ") || spoken.endsWith(" " + valid) || spoken.includes(" " + valid + " ")) return true;
      
      // Levenshtein Tolerance: 1 error for len <= 5, 2 for len > 5
      const tolerance = valid.length <= 5 ? 1 : 2;
      
      // Check each word independently (helps if Vosk adds filler words)
      const spokenWords = spoken.split(' ');
      for (const sw of spokenWords) {
        if (this.levenshtein(sw, valid) <= tolerance) return true;
      }
      
      // Also check the entire phrase against the valid phrase
      if (this.levenshtein(spoken, valid) <= tolerance) return true;
      
      return false;
    });
  }
};

window.addEventListener("error", e => {
  console.error("Global error:", e.error);
});
window.addEventListener("unhandledrejection", e => {
  console.error("Unhandled promise rejection:", e.reason);
});

// ============================
// 2. DOM ELEMENTS
// ============================
const dom = {};
document.addEventListener('DOMContentLoaded', () => {
  Object.assign(dom, {
    welcome: Utils.$('welcomeScreen'),
    session: Utils.$('sessionScreen'),
    summary: Utils.$('summaryScreen'),
    continueBtn: Utils.$('continueSrsBtn'),
    newBtn: Utils.$('newWordsBtn'),
    favBtn: Utils.$('favoritesBtn'),
    exportBtn: Utils.$('exportBtn'),
    importBtn: Utils.$('importBtn'),
    importFile: Utils.$('importFile'),
    exitBtn: Utils.$('exitSessionBtn'),
    replayBtn: Utils.$('replayBtn'),
    helpBtn: Utils.$('helpBtn'),
    voiceStatus: Utils.$('voiceStatus'),
    engineBadge: Utils.$('engineBadge'),
    responseContainer: Utils.$('responseButtons'),
    feedback: Utils.$('feedback'),
    correctBadge: Utils.$('correctBadge'),
    hanzi: Utils.$('hanziDisplay'),
    pinyin: Utils.$('pinyinHint'),
    wordCounter: Utils.$('wordCounter'),
    progressFill: Utils.$('progressFill'),
    newSessionBtn: Utils.$('newSessionBtn'),
    dashboardBtn: Utils.$('dashboardBtn'),
    statDue: Utils.$('statDue'),
    statNew: Utils.$('statNew'),
    statFav: Utils.$('statFav'),
    summaryReviewed: Utils.$('summaryReviewed'),
    summaryNew: Utils.$('summaryNew'),
    summaryAccuracy: Utils.$('summaryAccuracy'),
    toast: Utils.$('toast'),
    favoriteToggleBtn: Utils.$('favoriteToggleBtn'),
    hideWordBtn: Utils.$('hideWordBtn')
  });

  UI.bindEvents();
});

// ============================
// 3. EVENT BUS (Pub/Sub)
// ============================
const EventBus = {
  events: {},
  on(event, listener) {
    if (!this.events[event]) this.events[event] = [];
    this.events[event].push(listener);
  },
  emit(event, data) {
    if (this.events[event]) {
      this.events[event].forEach(l => Utils.safe(() => l(data)));
    }
  }
};

// ============================
// 4. USER INTERFACE (UI)
// ============================
const UI = {
  showToast(message, type = 'info', duration = 3000) {
    if (!dom.toast) return;
    dom.toast.textContent = message;
    dom.toast.className = 'toast show ' + type;
    setTimeout(() => { dom.toast.classList.remove('show'); }, duration);
  },

  updateWelcomeStats(vocabulary, userData) {
    const now = Date.now();
    let due = 0, newWords = 0, fav = 0;
    for (const w of vocabulary) {
      const ud = userData[w.id];
      if (!ud || ud.hidden) continue;
      if (ud.due <= now) due++;
      if (ud.reps === 0) newWords++;
      if (ud.favorited) fav++;
    }
    if (dom.statDue) dom.statDue.textContent = due;
    if (dom.statNew) dom.statNew.textContent = newWords;
    if (dom.statFav) dom.statFav.textContent = fav;
  },

  updateEngineBadge(state, text) {
    if (!dom.engineBadge) return;
    dom.engineBadge.classList.remove('hidden', 'online', 'offline', 'error');
    if (state === 'hidden') {
      dom.engineBadge.classList.add('hidden');
      return;
    }
    dom.engineBadge.classList.add(state);
    dom.engineBadge.textContent = text;
  },

  updateFavoriteButton(isFavorited) {
    if (!dom.favoriteToggleBtn) return;
    if (isFavorited) {
      dom.favoriteToggleBtn.textContent = '♥';
      dom.favoriteToggleBtn.classList.add('favorited');
      dom.favoriteToggleBtn.title = 'Quitar de favoritos';
    } else {
      dom.favoriteToggleBtn.textContent = '♡';
      dom.favoriteToggleBtn.classList.remove('favorited');
      dom.favoriteToggleBtn.title = 'Marcar como favorito';
    }
  },

  renderWord(wordObj, sessionIndex, totalWords) {
    if (!dom.hanzi) return;
    dom.hanzi.textContent = wordObj.hanzi;
    dom.pinyin.textContent = wordObj.pinyin;
    dom.wordCounter.textContent = `${sessionIndex + 1} / ${totalWords}`;
    const percent = ((sessionIndex + 1) / totalWords) * 100;
    dom.progressFill.style.width = `${percent}%`;

    const meanings = (wordObj.meaning || '').split(',');
    const correctAnswer = meanings[0] ? meanings[0].trim() : '';
    const distractors = wordObj.distractors && wordObj.distractors.length > 0 
      ? [...wordObj.distractors] 
      : ['correcto', 'incorrecto', 'tal vez'];
    const options = [correctAnswer, ...distractors.slice(0, 3)];
    Utils.shuffleArray(options);

    const fragment = document.createDocumentFragment();
    options.forEach((opt, idx) => {
      const btn = document.createElement('button');
      btn.textContent = opt;
      btn.dataset.index = idx;
      btn.onclick = () => EventBus.emit('ui_answer', opt);
      fragment.appendChild(btn);
    });
    dom.responseContainer.replaceChildren(fragment);

    if (dom.helpBtn) {
      if (wordObj.sentenceAudio) {
        dom.helpBtn.classList.remove('hidden', 'disabled');
        dom.helpBtn.disabled = false;
      } else {
        dom.helpBtn.classList.add('hidden');
      }
    }

    const ud = StorageManager.userData[wordObj.id];
    UI.updateFavoriteButton(ud ? ud.favorited : false);

    dom.feedback.classList.add('hidden');
    if (dom.correctBadge) dom.correctBadge.classList.remove('visible');
  },

  showFeedback(isCorrect, correctAnswer) {
    if (isCorrect) {
      dom.feedback.textContent = '✅ ¡Correcto!';
      dom.feedback.classList.remove('wrong');
      dom.feedback.classList.add('correct');
      if (dom.correctBadge) dom.correctBadge.classList.add('visible');
    } else {
      dom.feedback.textContent = `❌ Incorrecto. Era: ${correctAnswer}`;
      dom.feedback.classList.remove('correct');
      dom.feedback.classList.add('wrong');
      if (dom.correctBadge) dom.correctBadge.classList.remove('visible');
    }
    dom.feedback.classList.remove('hidden');
  },

  bindEvents() {
    if (dom.continueBtn) dom.continueBtn.onclick = () => EventBus.emit('ui_start_session', 'srs');
    if (dom.newBtn) dom.newBtn.onclick = () => EventBus.emit('ui_start_session', 'new');
    if (dom.favBtn) dom.favBtn.onclick = () => EventBus.emit('ui_start_session', 'favorites');
    if (dom.exportBtn) dom.exportBtn.onclick = () => StorageManager.exportProgress();
    if (dom.importBtn) dom.importBtn.onclick = () => dom.importFile.click();
    if (dom.importFile) dom.importFile.onchange = (e) => {
      if (e.target.files[0]) StorageManager.importProgress(e.target.files[0]);
      dom.importFile.value = '';
    };
    if (dom.exitBtn) dom.exitBtn.onclick = () => EventBus.emit('ui_exit_session');
    if (dom.replayBtn) dom.replayBtn.onclick = () => EventBus.emit('ui_replay');
    if (dom.helpBtn) dom.helpBtn.onclick = () => EventBus.emit('ui_help');
    if (dom.favoriteToggleBtn) dom.favoriteToggleBtn.onclick = () => EventBus.emit('ui_toggle_favorite');
    if (dom.hideWordBtn) dom.hideWordBtn.onclick = () => EventBus.emit('ui_hide_word');
    
    const goHome = () => {
      dom.summary.classList.remove('active');
      dom.welcome.classList.add('active');
      UI.updateWelcomeStats(StorageManager.vocabulary, StorageManager.userData);
    };
    if (dom.newSessionBtn) dom.newSessionBtn.onclick = goHome;
    if (dom.dashboardBtn) dom.dashboardBtn.onclick = goHome;

    document.addEventListener('keydown', (e) => {
      if (!dom.session || !dom.session.classList.contains('active')) return;
      
      const buttons = dom.responseContainer.querySelectorAll('button');
      if (e.key >= '1' && e.key <= '4') {
        const idx = parseInt(e.key) - 1;
        if (buttons[idx]) {
          buttons[idx].click();
          buttons[idx].classList.add('pressed');
          setTimeout(() => buttons[idx].classList.remove('pressed'), 200);
        }
      } else if (e.key === 'h' || e.key === 'H') {
        if (dom.helpBtn && !dom.helpBtn.classList.contains('hidden')) dom.helpBtn.click();
      } else if (e.key === 'r' || e.key === 'R') {
        if (dom.replayBtn) dom.replayBtn.click();
      } else if (e.key === 'Escape') {
        if (dom.exitBtn) dom.exitBtn.click();
      }
    });

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        MediaController.resumeContext();
      }
    });

    document.addEventListener('touchend', (e) => {
      if (e.target.tagName === 'BUTTON') {
        e.preventDefault();
        e.target.click();
      }
    }, { passive: false });
  }
};

// ============================
// 5. STORAGE MANAGER
// ============================
const StorageManager = {
  vocabulary: [],
  vocabMap: new Map(),
  userData: {},

  async loadInitialData() {
    try {
      // Prioritize fetching fresh data (bypass browser cache for the check)
      const res = await fetch('data/vocabulary.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.vocabulary = await res.json();

      if (!Array.isArray(this.vocabulary) || this.vocabulary.length === 0) {
        throw new Error('Vocabulario vacío o inválido');
      }

      // Update the local cache for offline usage
      Utils.safe(() => {
        localStorage.setItem('zenhanzi_vocab_cache', JSON.stringify(this.vocabulary));
        localStorage.setItem('zenhanzi_vocab_cache_time', String(Date.now()));
      });

      this.buildVocabMap();
      this.loadUserData();
      return true;
    } catch (err) {
      console.warn('Network fetch failed, trying local cache', err);
      const cached = localStorage.getItem('zenhanzi_vocab_cache');
      if (cached) {
        try {
          this.vocabulary = JSON.parse(cached);
          this.buildVocabMap();
          this.loadUserData();
          console.info('Usando vocabulario en caché (modo offline)');
          return true;
        } catch (e) { }
      }
      UI.showToast('Error cargando vocabulario. Revisa data/vocabulary.json', 'error');
      return false;
    }
  },

  buildVocabMap() {
    this.vocabMap.clear();
    for (const word of this.vocabulary) {
      if (word && word.id) this.vocabMap.set(word.id, word);
    }
  },

  loadUserData() {
    try {
      const stored = localStorage.getItem('zenhanzi_userdata');
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed === 'object') this.userData = parsed;
      }
    } catch (e) {
      console.error('Error loading userData, starting fresh', e);
      this.userData = {};
    }

    for (const word of this.vocabulary) {
      if (!this.userData[word.id]) {
        this.userData[word.id] = {
          favorited: word.favorited || false,
          interval: word.interval || 1,
          ease: word.ease || 2.5,
          due: word.due || 0,
          reps: word.reps || 0,
          lapses: word.lapses || 0,
          hidden: word.hidden || false
        };
      }
    }
    this.saveUserData();
  },

  saveUserData() {
    try {
      localStorage.setItem('zenhanzi_userdata', JSON.stringify(this.userData));
    } catch (e) {
      console.error('Storage full or error', e);
      UI.showToast('Error guardando progreso - almacenamiento lleno', 'error');
    }
  },

  getDueWords(mode) {
    const now = Date.now();
    let queue = [];
    if (mode === 'srs') {
      queue = this.vocabulary.filter(w => this.userData[w.id] && !this.userData[w.id].hidden && this.userData[w.id].due <= now);
      Utils.shuffleArray(queue);
    } else if (mode === 'new') {
      queue = this.vocabulary.filter(w => this.userData[w.id] && !this.userData[w.id].hidden && this.userData[w.id].reps === 0);
      queue.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
    } else if (mode === 'favorites') {
      queue = this.vocabulary.filter(w => this.userData[w.id] && !this.userData[w.id].hidden && this.userData[w.id].favorited);
      Utils.shuffleArray(queue);
    }
    return queue.map(w => w.id);
  },

  exportProgress() {
    try {
      const fullExport = JSON.parse(JSON.stringify(this.vocabulary));
      
      for (let word of fullExport) {
        const ud = this.userData[word.id];
        if (ud) {
          word.favorited = ud.favorited;
          word.interval = ud.interval;
          word.ease = ud.ease;
          word.due = ud.due;
          word.reps = ud.reps;
          word.lapses = ud.lapses;
          word.hidden = ud.hidden;
        }
      }

      const dataStr = JSON.stringify(fullExport, null, 2);
      const blob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vocabulary_updated_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      UI.showToast('Vocabulario exportado', 'success');
    } catch (e) {
      console.error('Export error', e);
      UI.showToast('Error al exportar', 'error');
    }
  },

  importProgress(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const imported = JSON.parse(e.target.result);
        if (!imported) throw new Error('Formato inválido');
        
        let newUserData = { ...this.userData };

        if (Array.isArray(imported)) {
          if (imported.length === 0) throw new Error('Array vacío');
          for (const word of imported) {
            if (word && word.id) {
              newUserData[word.id] = {
                favorited: word.favorited || false,
                interval: word.interval || 1,
                ease: word.ease || 2.5,
                due: word.due || 0,
                reps: word.reps || 0,
                lapses: word.lapses || 0,
                hidden: word.hidden || false
              };
            }
          }
        } else {
          const keys = Object.keys(imported);
          if (keys.length === 0) throw new Error('Archivo vacío');
          const sample = imported[keys[0]];
          if (!sample || typeof sample !== 'object' || !('interval' in sample || 'reps' in sample)) {
            throw new Error('Datos no reconocidos');
          }
          newUserData = { ...this.userData, ...imported };
        }

        this.userData = newUserData;
        this.saveUserData();
        UI.showToast('Progreso importado. Recargando...', 'success');
        setTimeout(() => location.reload(), 1500);
      } catch (err) {
        console.error('Import error', err);
        UI.showToast('Archivo inválido: ' + err.message, 'error');
      }
    };
    reader.onerror = () => UI.showToast('Error leyendo archivo', 'error');
    reader.readAsText(file);
  }
};

// ============================
// 6. MEDIA CONTROLLER
// ============================
const MediaController = {
  audioContext: null,
  currentAudio: null,
  
  // Speech properties
  type: null, 
  webSpeechRec: null,
  voskModel: null,
  voskRecognizer: null,
  micStream: null,
  micSourceNode: null,
  recognizerNode: null,
  isVoskLoaded: false,
  VOICE_TRIGGERS: ['pista', 'no se', 'no sé', 'no lo se', 'no lo sé', 'ayuda', 'help', 'repite', 'otra vez'],

  async init() {
    if (!this.audioContext) {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    }
    await this.resumeContext();

    if (dom.voiceStatus) dom.voiceStatus.classList.remove('hidden');

    const isMicActive = this.micStream && this.micStream.getTracks().every(t => t.readyState === 'live');
    if (this.type === 'vosk' && this.isVoskLoaded && this.audioContext.state === 'running' && isMicActive) {
      return;
    }

    if ((!this.type || this.type === 'vosk') && typeof Vosk !== 'undefined') {
      if (dom.voiceStatus) dom.voiceStatus.textContent = '⏳ Preparando voz offline...';
      try {
        await this.initVosk();
        this.type = 'vosk';
        UI.updateEngineBadge('offline', 'Vosk · Offline');
        if (dom.voiceStatus) dom.voiceStatus.textContent = '🎙️ Voz offline activa';
        return;
      } catch (err) {
        console.error('Vosk init/restart failed:', err);
        if (this.type === 'vosk') this.type = null; 
      }
    }

    if (!this.type && (window.SpeechRecognition || window.webkitSpeechRecognition)) {
      if (dom.voiceStatus) dom.voiceStatus.textContent = '⏳ Iniciando voz online...';
      try {
        this.initWebSpeech();
        this.type = 'webspeech';
        UI.updateEngineBadge('online', 'Google · Online');
        if (dom.voiceStatus) dom.voiceStatus.textContent = '🎙️ Voz online activa';
      } catch (err) {
        console.error('WebSpeech init failed:', err);
        UI.updateEngineBadge('error', 'Sin reconocimiento');
        if (dom.voiceStatus) dom.voiceStatus.textContent = '❌ Reconocimiento no disponible';
      }
    }
  },

  async initVosk() {
    if (!this.micStream || !this.micStream.getTracks().every(t => t.readyState === 'live')) {
      if (this.micStream) this.micStream.getTracks().forEach(t => t.stop());
      this.micStream = await navigator.mediaDevices.getUserMedia({
        video: false,
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1, sampleRate: 16000 }
      });
    }

    if (!this.isVoskLoaded) {
      const modelUrl = new URL('models/es-model.tar.gz', window.location.href).href;
      this.voskModel = await Vosk.createModel(modelUrl);
      this.voskRecognizer = new this.voskModel.KaldiRecognizer(16000);
      this.voskRecognizer.on("result", (message) => {
        if (message.result.text) this.handleTranscript(message.result.text);
      });
      this.isVoskLoaded = true;
    }

    if (this.micSourceNode) this.micSourceNode.disconnect();
    if (this.recognizerNode) this.recognizerNode.disconnect();

    this.micSourceNode = this.audioContext.createMediaStreamSource(this.micStream);
    this.recognizerNode = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.recognizerNode.onaudioprocess = (event) => {
      // Only process when FSM is explicitly listening
      if (SessionManager.state === 'LISTENING' && this.voskRecognizer) {
        try { this.voskRecognizer.acceptWaveform(event.inputBuffer); } catch (e) { }
      }
    };

    this.micSourceNode.connect(this.recognizerNode);
    const dummyGain = this.audioContext.createGain();
    dummyGain.gain.value = 0;
    this.recognizerNode.connect(dummyGain);
    dummyGain.connect(this.audioContext.destination);
  },

  initWebSpeech() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.webSpeechRec = new SpeechRecognition();
    this.webSpeechRec.lang = 'es-ES';
    this.webSpeechRec.continuous = false;
    this.webSpeechRec.interimResults = false;
    this.webSpeechRec.maxAlternatives = 1;

    this.webSpeechRec.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      this.handleTranscript(transcript);
    };

    this.webSpeechRec.onerror = (event) => {
      if (event.error === 'network' || event.error === 'service-not-allowed') {
        if (dom.voiceStatus) dom.voiceStatus.textContent = '❌ Voz online bloqueada por navegador';
        UI.updateEngineBadge('error', 'Google bloqueado');
        this.type = null;
        this.webSpeechRec = null;
      } else if (event.error === 'not-allowed') {
        if (dom.voiceStatus) dom.voiceStatus.textContent = '❌ Micrófono bloqueado';
        UI.updateEngineBadge('error', 'Micrófono bloqueado');
        this.type = null;
      }
    };

    this.webSpeechRec.onend = () => {
      if (SessionManager.state === 'LISTENING' && this.type === 'webspeech') {
        try { this.webSpeechRec.start(); } catch (e) { } // auto restart
      }
    };
  },

  handleTranscript(transcript) {
    if (SessionManager.state !== 'LISTENING') return;
    
    const normalized = Utils.normalizeText(transcript);
    const isTrigger = this.VOICE_TRIGGERS.some(t => normalized === t || normalized.includes(t));

    if (isTrigger) {
      EventBus.emit('ui_help');
      return;
    }
    
    EventBus.emit('voice_recognized', transcript);
  },

  startListening() {
    if (this.type === 'webspeech' && this.webSpeechRec) {
      try {
        this.webSpeechRec.start();
        if (dom.voiceStatus) dom.voiceStatus.textContent = '🎙️ Escuchando... (di "pista")';
      } catch (e) {} 
    } else if (this.type === 'vosk') {
      this.resumeContext();
      if (dom.voiceStatus) dom.voiceStatus.textContent = '🎙️ Escuchando... (di "pista")';
    }
  },

  stopListening() {
    if (this.type === 'webspeech' && this.webSpeechRec) {
      try { this.webSpeechRec.stop(); } catch (e) { }
    }
  },

  async resumeContext() {
    if (this.audioContext && this.audioContext.state === 'suspended') {
      await Utils.safe(() => this.audioContext.resume());
    }
  },

  stopAudio() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.onended = null;
      this.currentAudio.onerror = null;
      this.currentAudio = null;
    }
  },

  playAudio(src) {
    return new Promise((resolve, reject) => {
      this.stopAudio();
      if (!src) return reject('No source');
      
      this.currentAudio = new Audio(src);
      this.currentAudio.onended = () => resolve();
      this.currentAudio.onerror = () => reject('Playback failed');
      this.currentAudio.play().catch(reject);
    });
  },

  playBeep(type) {
    try {
      this.resumeContext();
      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      osc.connect(gain);
      gain.connect(this.audioContext.destination);
      const now = this.audioContext.currentTime;

      if (type === 'listen') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, now);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
        osc.start(now);
        osc.stop(now + 0.1);
      } else if (type === 'correct') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, now);
        osc.frequency.setValueAtTime(659.25, now + 0.1);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
      } else if (type === 'wrong') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(300, now);
        osc.frequency.setValueAtTime(250, now + 0.15);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
      } else if (type === 'help') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(700, now);
        osc.frequency.setValueAtTime(900, now + 0.1);
        osc.frequency.setValueAtTime(700, now + 0.2);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
        osc.start(now);
        osc.stop(now + 0.25);
      }
    } catch (e) {
      console.warn("AudioContext no soportado o bloqueado", e);
    }
  },

  shutdown() {
    this.stopListening();
    this.stopAudio();
    this.isVoskLoaded = false;
    if (this.micStream) {
      this.micStream.getTracks().forEach(t => t.stop());
      this.micStream = null;
    }
    if (this.audioContext) {
      Utils.safe(() => this.audioContext.close());
      this.audioContext = null;
    }
    this.micSourceNode = null;
    this.recognizerNode = null;
  }
};

// ============================
// 7. SESSION MANAGER (FSM)
// ============================
const SessionManager = {
  state: 'IDLE', // IDLE, PLAYING_PROMPT, LISTENING, PLAYING_HELP, FEEDBACK
  queue: [],
  index: 0,
  stats: { total: 0, correct: 0, newCount: 0 },
  currentWordObj: null,
  currentMode: 'srs',
  timer: null,

  initEvents() {
    EventBus.on('ui_start_session', (mode) => this.startSession(mode));
    EventBus.on('ui_answer', (opt) => this.handleAnswer(opt));
    EventBus.on('voice_recognized', (text) => this.handleVoice(text));
    EventBus.on('ui_help', () => this.handleHelp());
    EventBus.on('ui_replay', () => this.transition('PLAYING_PROMPT'));
    EventBus.on('ui_toggle_favorite', () => this.toggleFavorite());
    EventBus.on('ui_hide_word', () => this.hideCurrentWord());
    EventBus.on('ui_exit_session', () => this.exitSession());
  },

  transition(newState) {
    if (this.state === 'IDLE' && newState !== 'PLAYING_PROMPT') return;
    if (newState === 'PLAYING_PROMPT' && !this.currentWordObj) return;
    this.state = newState;

    if (this.timer) { clearTimeout(this.timer); this.timer = null; }

    switch (this.state) {
      case 'IDLE':
        MediaController.shutdown();
        UI.updateEngineBadge('hidden');
        if (dom.session) dom.session.classList.remove('active');
        if (dom.welcome) dom.welcome.classList.add('active');
        UI.updateWelcomeStats(StorageManager.vocabulary, StorageManager.userData);
        break;

      case 'PLAYING_PROMPT':
        MediaController.stopListening();
        if (dom.helpBtn) dom.helpBtn.classList.remove('disabled');
        if (dom.responseContainer) dom.responseContainer.classList.remove('disabled');
        if (dom.voiceStatus) dom.voiceStatus.textContent = "🔊 Reproduciendo...";
        
        MediaController.playAudio(this.currentWordObj.chineseAudio)
          .then(() => this.transition('LISTENING'))
          .catch(() => this.transition('LISTENING'));
        break;

      case 'LISTENING':
        if (dom.helpBtn) dom.helpBtn.classList.remove('disabled');
        if (dom.responseContainer) dom.responseContainer.classList.remove('disabled');
        MediaController.playBeep('listen');
        MediaController.startListening();
        break;

      case 'PLAYING_HELP':
        MediaController.stopListening();
        if (dom.helpBtn) dom.helpBtn.classList.add('disabled');
        
        MediaController.playBeep('help');
        MediaController.playAudio(this.currentWordObj.sentenceAudio)
          .then(() => {
            if (this.state !== 'PLAYING_HELP') return; // State changed by user action
            if (dom.voiceStatus) dom.voiceStatus.textContent = '🔊 Repitiendo palabra...';
            this.timer = setTimeout(() => {
              if (this.state !== 'PLAYING_HELP') return;
              MediaController.playAudio(this.currentWordObj.chineseAudio)
                .then(() => this.transition('LISTENING'))
                .catch(() => this.transition('LISTENING'));
            }, 600);
          })
          .catch(() => this.transition('LISTENING'));
        break;

      case 'FEEDBACK':
        MediaController.stopListening();
        MediaController.stopAudio();
        if (dom.responseContainer) dom.responseContainer.classList.add('disabled');
        if (dom.helpBtn) dom.helpBtn.classList.add('disabled');
        break;
    }
  },

  async startSession(mode) {
    this.currentMode = mode;
    const queueIds = StorageManager.getDueWords(mode);
    if (queueIds.length === 0) {
      UI.showToast('No hay palabras para este criterio.', 'info');
      return;
    }

    this.queue = queueIds;
    this.index = 0;
    this.stats = {
      total: this.queue.length,
      correct: 0,
      newCount: this.queue.filter(id => StorageManager.userData[id]?.reps === 0).length
    };

    if (dom.welcome) dom.welcome.classList.remove('active');
    if (dom.session) dom.session.classList.add('active');

    try {
      await MediaController.init();
      this.loadCurrentWord();
    } catch (err) {
      console.error('[SessionManager] Failed to init session speech/audio:', err);
      UI.showToast('Error de inicio: ' + err.message, 'error');
      this.transition('IDLE');
    }
  },

  loadCurrentWord() {
    const id = this.queue[this.index];
    this.currentWordObj = StorageManager.vocabMap.get(id);
    
    if (!this.currentWordObj) {
      return this.nextWord();
    }

    UI.renderWord(this.currentWordObj, this.index, this.queue.length);
    this.transition('PLAYING_PROMPT');
  },

  handleAnswer(selectedOption) {
    if (this.state !== 'PLAYING_PROMPT' && this.state !== 'LISTENING' && this.state !== 'PLAYING_HELP') return;
    
    const validMeanings = (this.currentWordObj.meaning || '').split(',').map(m => m.trim());
    const isCorrect = selectedOption === validMeanings[0];
    this.submitResult(isCorrect);
  },

  handleVoice(spokenText) {
    if (this.state !== 'LISTENING') return;
    
    const normalizedSpoken = Utils.normalizeText(spokenText);
    const validMeanings = (this.currentWordObj.meaning || '').split(',').map(m => Utils.normalizeText(m.trim()));
    
    const isCorrect = Utils.matchMeaning(normalizedSpoken, validMeanings);
    
    // Enfoque Indulgente: Solo procesamos si la voz es correcta.
    // Evitamos penalizar el SRS por errores de Vosk o ruidos de fondo.
    if (isCorrect) {
      this.submitResult(true);
    }
  },

  handleHelp() {
    if (this.state !== 'PLAYING_PROMPT' && this.state !== 'LISTENING') return;
    if (!this.currentWordObj.sentenceAudio) {
      UI.showToast('No hay oración de ayuda', 'info');
      return;
    }
    UI.showToast('💡 Pista activada', 'info', 1500);
    if (dom.voiceStatus) dom.voiceStatus.textContent = '💡 Ayuda...';
    this.transition('PLAYING_HELP');
  },

  submitResult(isCorrect) {
    this.transition('FEEDBACK');

    const ud = StorageManager.userData[this.currentWordObj.id];
    if (!ud) return this.nextWord();

    let newInterval, newEase, newReps, newDue;

    if (isCorrect) {
      MediaController.playBeep('correct');
      this.stats.correct++;
      if (ud.reps === 0) {
        newInterval = 1;
        newReps = 1;
        newEase = ud.ease;
      } else {
        newReps = ud.reps + 1;
        newEase = Math.min(2.8, ud.ease + 0.1);
        newInterval = Math.round(ud.interval * newEase);
        if (newInterval > 365) newInterval = 365;
      }
      newDue = Date.now() + (newInterval * 86400000);
    } else {
      MediaController.playBeep('wrong');
      ud.lapses = (ud.lapses || 0) + 1;
      newReps = 0;
      newInterval = 1;
      newEase = Math.max(1.3, ud.ease - 0.2);
      newDue = Date.now() + 86400000;
    }

    ud.reps = newReps;
    ud.interval = newInterval;
    ud.ease = newEase;
    ud.due = newDue;
    StorageManager.userData[this.currentWordObj.id] = ud;
    StorageManager.saveUserData();

    const firstMeaning = (this.currentWordObj.meaning || '').split(',')[0];
    UI.showFeedback(isCorrect, firstMeaning);

    const delay = isCorrect ? 1500 : 2000;
    this.timer = setTimeout(() => this.nextWord(), delay);
  },

  nextWord() {
    this.index++;
    if (this.index < this.queue.length) {
      this.loadCurrentWord();
    } else {
      this.endSession();
    }
  },

  toggleFavorite() {
    if (!this.currentWordObj) return;
    const id = this.currentWordObj.id;
    const ud = StorageManager.userData[id];
    if (!ud) return;

    ud.favorited = !ud.favorited;
    StorageManager.userData[id] = ud;
    StorageManager.saveUserData();

    UI.updateFavoriteButton(ud.favorited);
    const msg = ud.favorited ? '❤️ Añadido a favoritos' : '🤍 Eliminado de favoritos';
    UI.showToast(msg, 'info', 1200);
  },

  hideCurrentWord() {
    if (!this.currentWordObj) return;
    const id = this.currentWordObj.id;
    const ud = StorageManager.userData[id];
    if (!ud) return;

    ud.hidden = true;
    StorageManager.userData[id] = ud;
    StorageManager.saveUserData();

    UI.showToast('🚫 Palabra oculta', 'info', 1500);
    this.nextWord();
  },

  endSession() {
    this.transition('IDLE');
    if (dom.session) dom.session.classList.remove('active');
    if (dom.summary) dom.summary.classList.add('active');
    
    if (dom.summaryReviewed) dom.summaryReviewed.textContent = this.stats.total;
    if (dom.summaryNew) dom.summaryNew.textContent = this.stats.newCount;
    const accuracy = this.stats.total ? Math.round((this.stats.correct / this.stats.total) * 100) : 0;
    if (dom.summaryAccuracy) dom.summaryAccuracy.textContent = accuracy;
  },

  exitSession() {
    this.transition('IDLE');
  }
};

// ============================
// 8. BOOTSTRAP
// ============================
document.addEventListener('DOMContentLoaded', () => {
  SessionManager.initEvents();
  StorageManager.loadInitialData().then(success => {
    if (success) UI.updateWelcomeStats(StorageManager.vocabulary, StorageManager.userData);
  });
});
