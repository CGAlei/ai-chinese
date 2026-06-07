/**
 * mo-common.js — Shared database + utilities for Mo-Chinese webapps
 * Version: 1.0.0
 * 
 * Provides:
 *   - MoDB      : Unified IndexedDB (words, audio, sentences, srs, sessions, settings)
 *   - MoPinyin  : Tone stripping + pinyin helpers
 *   - MoSettings: Unified settings manager (IndexedDB, with localStorage bridge)
 *   - MoBackup  : Export / import all data as JSON
 * 
 * Usage: <script src="mo-common.js"></script>
 */

/* ═══════════════════════════════════════════════
   MODULE 1: MoDB — Unified IndexedDB Layer
   ═══════════════════════════════════════════════ */
const MoDB = (() => {
  'use strict';

  const DB_NAME = 'MoDB';
  const DB_VER  = 5;

  // Store names
  const S = {
    WORDS:     'words',
    AUDIO:     'audio',
    SENTENCES: 'sentences',
    SRS:       'srs',
    SESSIONS:  'sessions',
    SETTINGS:  'settings',
  };

  let _db = null;
  let _initPromise = null;

  /* ── Internal helpers ── */
  function _validateDb() {
    if (!_db) return false;
    try {
      // Quick health check: can we create a transaction?
      _db.transaction(S.WORDS, 'readonly').abort();
      return true;
    } catch (e) {
      _db = null;
      _initPromise = null;
      return false;
    }
  }

  function _validateDb() {
    if (!_db) return false;
    try {
      // Quick health check: can we create a transaction?
      _db.transaction(S.WORDS, 'readonly').abort();
      return true;
    } catch (e) {
      _db = null;
      _initPromise = null;
      return false;
    }
  }

  function open() {
    if (_validateDb()) return Promise.resolve(_db);
    _initPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        // words: PK = hanzi string
        if (!db.objectStoreNames.contains(S.WORDS)) {
          const store = db.createObjectStore(S.WORDS, { keyPath: 'id' });
          store.createIndex('pinyinToneless', 'pinyinToneless', { unique: false });
          store.createIndex('enriched', 'enriched', { unique: false });
        }
        // audio: PK = hanzi string
        if (!db.objectStoreNames.contains(S.AUDIO)) {
          db.createObjectStore(S.AUDIO, { keyPath: 'id' });
        }
        // sentences: PK = auto-increment, index by wordId
        if (!db.objectStoreNames.contains(S.SENTENCES)) {
          db.createObjectStore(S.SENTENCES, { keyPath: 'id', autoIncrement: true });
        }
        if (db.objectStoreNames.contains(S.SENTENCES)) {
          const store = e.currentTarget.transaction.objectStore(S.SENTENCES);
          if (!store.indexNames.contains('wordId')) store.createIndex('wordId', 'wordId', { unique: false });
        }
        // srs: PK = hanzi string
        if (!db.objectStoreNames.contains(S.SRS)) {
          db.createObjectStore(S.SRS, { keyPath: 'id' });
        }
        // sessions: PK = "category/name"
        if (!db.objectStoreNames.contains(S.SESSIONS)) {
          db.createObjectStore(S.SESSIONS, { keyPath: 'id' });
        }
        // settings: PK = "global"
        if (!db.objectStoreNames.contains(S.SETTINGS)) {
          db.createObjectStore(S.SETTINGS, { keyPath: 'id' });
        }
      };
      req.onsuccess = (e) => { _db = e.target.result; resolve(_db); };
      req.onerror   = () => reject(req.error);
    });
    return _initPromise;
  }

  function tx(storeNames, mode = 'readonly') {
    return _db.transaction(storeNames, mode);
  }

  /* ── Generic CRUD ── */
  async function get(storeName, id) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName).objectStore(storeName).get(id);
      request.onsuccess = () => resolve(request.result);
      request.onerror   = () => reject(request.error);
    });
  }

  async function put(storeName, data) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName, 'readwrite').objectStore(storeName).put(data);
      request.onsuccess = () => resolve();
      request.onerror   = () => reject(request.error);
    });
  }

  async function remove(storeName, id) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName, 'readwrite').objectStore(storeName).delete(id);
      request.onsuccess = () => resolve();
      request.onerror   = () => reject(request.error);
    });
  }

  async function getAll(storeName) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName).objectStore(storeName).getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror   = () => reject(request.error);
    });
  }

  async function getAllKeys(storeName) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName).objectStore(storeName).getAllKeys();
      request.onsuccess = () => resolve(request.result);
      request.onerror   = () => reject(request.error);
    });
  }

  async function clear(storeName) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction(storeName, 'readwrite').objectStore(storeName).clear();
      request.onsuccess = () => resolve();
      request.onerror   = () => reject(request.error);
    });
  }

  /* ── WORDS API ── */
  async function getWord(id) { return get(S.WORDS, id); }
  async function putWord(data) {
    if (!data.id) data.id = data.hanzi;
    data.updatedAt = Date.now();
    if (!data.createdAt) data.createdAt = Date.now();
    return put(S.WORDS, data);
  }
  async function hasWord(id) {
    const w = await getWord(id);
    return !!w;
  }
  async function getAllWords() { return getAll(S.WORDS); }
  async function countWords() {
    const db = await open();
    return new Promise((resolve, reject) => {
      const req = db.transaction(S.WORDS).objectStore(S.WORDS).count();
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
  }

  /* ── AUDIO API ── */
  async function getAudio(id) { return get(S.AUDIO, id); }
  async function putAudio(data) {
    if (!data.id) throw new Error('Audio data must have id');
    data.updatedAt = Date.now();
    if (!data.createdAt) data.createdAt = Date.now();
    return put(S.AUDIO, data);
  }

  /* ── SENTENCES API ── */
  async function getSentence(id) { return get(S.SENTENCES, id); }
  async function putSentence(data) {
    data.updatedAt = Date.now();
    if (!data.createdAt) data.createdAt = Date.now();
    return put(S.SENTENCES, data);
  }
  async function getSentencesByWord(wordId) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const req = db.transaction(S.SENTENCES).objectStore(S.SENTENCES).index('wordId').getAll(wordId);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
  }

  /* ── SRS API ── */
  async function getSRS(id) { return get(S.SRS, id); }
  async function putSRS(data) {
    if (!data.id) throw new Error('SRS data must have id');
    return put(S.SRS, data);
  }
  async function getAllSRS() { return getAll(S.SRS); }

  /* ── SESSIONS API ── */
  async function getSession(id) { return get(S.SESSIONS, id); }
  async function putSession(data) {
    if (!data.id) throw new Error('Session data must have id');
    data.updatedAt = Date.now();
    return put(S.SESSIONS, data);
  }
  async function getAllSessions() { return getAll(S.SESSIONS); }

  /* ── SETTINGS API ── */
  async function getSettings() {
    const s = await get(S.SETTINGS, 'global');
    return s || {};
  }
  async function putSettings(data) {
    data.id = 'global';
    data.updatedAt = Date.now();
    return put(S.SETTINGS, data);
  }

  /* ── MIGRATION: Phase 0 detection ── */
  async function detectMigrationNeeded() {
    const flags = {
      srs: false,
      audio: false,
      sentences: false,
      translations: false,
      readCounts: false,
      settings: false,
    };

    // Check localStorage
    if (localStorage.getItem('mo_srs_v2')) flags.srs = true;
    if (localStorage.getItem('mo_settings_v1')) flags.settings = true;
    if (localStorage.getItem('chinread_readcounts')) flags.readCounts = true;
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('mo_sentences_v1:')) { flags.sentences = true; break; }
    }

    // Check old IndexedDB databases
    let dbNames = [];
    if (indexedDB.databases) {
      try {
        const dbs = await indexedDB.databases();
        if (Array.isArray(dbs)) dbNames = dbs.map(d => d.name);
      } catch (e) {
        // indexedDB.databases() not supported in this browser
      }
    }
    if (dbNames.includes('mo_db_v1')) flags.audio = true;
    if (dbNames.includes('ZHReaderProDB')) flags.translations = true;

    return flags;
  }

  async function runMigration() {
    const flags = await detectMigrationNeeded();
    const results = [];

    // Migrate SRS
    if (flags.srs) {
      try {
        const raw = localStorage.getItem('mo_srs_v2');
        const data = JSON.parse(raw || '{}');
        let count = 0;
        for (const [id, obj] of Object.entries(data)) {
          if (!/^[\u4e00-\u9fa5]/.test(id)) continue; // skip non-Chinese keys
          const existing = await getSRS(id);
          if (!existing) {
            await putSRS({ id, ...obj });
            count++;
          }
        }
        results.push(`SRS: migrated ${count} entries`);
      } catch (e) { results.push(`SRS: error — ${e.message}`); }
    }

    // Migrate Settings
    if (flags.settings) {
      try {
        const raw = localStorage.getItem('mo_settings_v1');
        const old = JSON.parse(raw || '{}');
        const existing = await getSettings();
        const merged = { ...existing, ...old };
        await putSettings(merged);
        results.push('Settings: migrated');
      } catch (e) { results.push(`Settings: error — ${e.message}`); }
    }

    // Migrate Read Counts
    if (flags.readCounts) {
      try {
        const raw = localStorage.getItem('chinread_readcounts');
        const data = JSON.parse(raw || '{}');
        let count = 0;
        for (const [id, readCount] of Object.entries(data)) {
          const existing = await getSession(id);
          if (!existing) {
            const [category, name] = id.split('/');
            await putSession({ id, category, name, readCount, lastRead: Date.now() });
            count++;
          }
        }
        results.push(`Sessions: migrated ${count} entries`);
      } catch (e) { results.push(`Sessions: error — ${e.message}`); }
    }

    // Migrate Sentences
    if (flags.sentences) {
      try {
        let count = 0;
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (!k || !k.startsWith('mo_sentences_v1:')) continue;
          const wordId = k.substring('mo_sentences_v1:'.length);
          const raw = localStorage.getItem(k);
          const obj = JSON.parse(raw);
          const existing = await getSentencesByWord(wordId);
          if (existing.length === 0) {
            await putSentence({ wordId, zh: obj.zh, es: obj.es, createdAt: Date.now() });
            count++;
          }
        }
        results.push(`Sentences: migrated ${count} entries`);
      } catch (e) { results.push(`Sentences: error — ${e.message}`); }
    }

    // Migrate Translations from ZHReaderProDB
    if (flags.translations) {
      try {
        const count = await migrateZHReaderProDB();
        results.push(`Translations: migrated ${count} entries`);
      } catch (e) { results.push(`Translations: error — ${e.message}`); }
    }

    // Migrate Audio from mo_db_v1
    if (flags.audio) {
      try {
        const count = await migrateMoDbV1();
        results.push(`Audio: migrated ${count} entries`);
      } catch (e) { results.push(`Audio: error — ${e.message}`); }
    }

    console.log('[MoDB] Migration results:', results);
    return results;
  }

  async function migrateZHReaderProDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open('ZHReaderProDB', 1);
      req.onsuccess = (e) => {
        const oldDb = e.target.result;
        if (!oldDb.objectStoreNames.contains('translations')) {
          resolve(0);
          return;
        }
        const tx = oldDb.transaction('translations', 'readonly');
        const store = tx.objectStore('translations');

        let values = [], keys = [];
        let pending = 2;

        function checkDone() {
          if (pending > 0) return;
          // Both requests finished
          (async () => {
            let count = 0;
            for (let i = 0; i < keys.length; i++) {
              const word = keys[i];
              const meaning = values[i];
              if (!/^[\u4e00-\u9fa5]/.test(word)) continue;
              const existing = await getWord(word);
              if (!existing) {
                await putWord({
                  id: word,
                  hanzi: word,
                  meaning,
                  source: 'reader_migrated',
                  enriched: false,
                });
                count++;
              }
            }
            resolve(count);
          })();
        }

        const reqAll = store.getAll();
        reqAll.onsuccess = () => { values = reqAll.result; pending--; checkDone(); };
        reqAll.onerror = () => reject(reqAll.error);

        const reqKeys = store.getAllKeys();
        reqKeys.onsuccess = () => { keys = reqKeys.result; pending--; checkDone(); };
        reqKeys.onerror = () => reject(reqKeys.error);
      };
      req.onerror = () => reject(req.error);
    });
  }

  async function migrateMoDbV1() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open('mo_db_v1', 1);
      req.onsuccess = (e) => {
        const oldDb = e.target.result;

        // Migrate word_audio
        if (oldDb.objectStoreNames.contains('word_audio')) {
          const tx = oldDb.transaction('word_audio', 'readonly');
          const store = tx.objectStore('word_audio');

          let values = [], keys = [];
          let pending = 2;

          function checkDone() {
            if (pending > 0) return;
            (async () => {
              let count = 0;
              for (let i = 0; i < keys.length; i++) {
                const hanzi = keys[i];
                const audio = values[i].audio || values[i];
                const existing = await getAudio(hanzi);
                if (!existing) {
                  await putAudio({ id: hanzi, wordAudio: audio, source: 'migrated' });
                  count++;
                }
              }
              resolve(count);
            })();
          }

          const reqAll = store.getAll();
          reqAll.onsuccess = () => { values = reqAll.result; pending--; checkDone(); };
          reqAll.onerror = () => reject(reqAll.error);

          const reqKeys = store.getAllKeys();
          reqKeys.onsuccess = () => { keys = reqKeys.result; pending--; checkDone(); };
          reqKeys.onerror = () => reject(reqKeys.error);
        } else {
          resolve(0);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  /* ── Cleanup old stores (Phase 3, call manually when ready) ── */
  async function cleanupOldStores() {
    localStorage.removeItem('mo_srs_v2');
    localStorage.removeItem('mo_settings_v1');
    localStorage.removeItem('chinread_readcounts');
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith('mo_sentences_v1:')) localStorage.removeItem(k);
    }
    // Old IndexedDBs are left for the browser to garbage collect;
    // deleting them requires calling indexedDB.deleteDatabase(name)
    try { indexedDB.deleteDatabase('mo_db_v1'); } catch (e) {}
    try { indexedDB.deleteDatabase('ZHReaderProDB'); } catch (e) {}
  }

  /* ── Export / Import ── */
  async function exportAll() {
    const [words, audioList, sentences, srsList, sessions, settings] = await Promise.all([
      getAll(S.WORDS),
      getAll(S.AUDIO),
      getAll(S.SENTENCES),
      getAll(S.SRS),
      getAll(S.SESSIONS),
      getSettings(),
    ]);

    // Audio ArrayBuffers → base64
    const audio = {};
    for (const a of audioList) {
      audio[a.id] = {
        wordAudio: a.wordAudio ? bufferToBase64(a.wordAudio) : null,
        sentenceAudios: (a.sentenceAudios || []).map(sa => ({
          index: sa.index,
          audio: sa.audio ? bufferToBase64(sa.audio) : null,
        })),
        source: a.source,
      };
    }

    return {
      version: 4,
      date: new Date().toISOString(),
      words,
      audio,
      sentences,
      srs: srsList,
      sessions,
      settings,
    };
  }

  async function importAll(data) {
    if (!data || data.version !== 4) throw new Error('Invalid backup format');
    await open(); // ensure _db is alive
    const results = [];

    // Helper: bulk-put into one store using a single transaction
    function bulkPut(storeName, items) {
      if (!items || items.length === 0) return Promise.resolve();
      return new Promise((resolve, reject) => {
        const transaction = _db.transaction(storeName, 'readwrite');
        const store = transaction.objectStore(storeName);
        for (const item of items) store.put(item);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
      });
    }

    if (data.words) {
      await bulkPut(S.WORDS, data.words);
      results.push(`words: ${data.words.length}`);
    }
    if (data.audio) {
      const audioItems = [];
      for (const [id, a] of Object.entries(data.audio)) {
        audioItems.push({
          id,
          wordAudio: a.wordAudio ? base64ToBuffer(a.wordAudio) : null,
          sentenceAudios: (a.sentenceAudios || []).map(sa => ({
            index: sa.index,
            audio: sa.audio ? base64ToBuffer(sa.audio) : null,
          })),
          source: a.source || 'import',
          createdAt: Date.now(),
          updatedAt: Date.now(),
        });
      }
      await bulkPut(S.AUDIO, audioItems);
      results.push(`audio: ${audioItems.length}`);
    }
    if (data.sentences) {
      await bulkPut(S.SENTENCES, data.sentences);
      results.push(`sentences: ${data.sentences.length}`);
    }
    if (data.srs) {
      await bulkPut(S.SRS, data.srs);
      results.push(`srs: ${data.srs.length}`);
    }
    if (data.sessions) {
      await bulkPut(S.SESSIONS, data.sessions);
      results.push(`sessions: ${data.sessions.length}`);
    }
    if (data.settings) {
      await putSettings(data.settings);
      results.push('settings: 1');
    }

    return results;
  }

  /* ── Buffer helpers ── */
  function bufferToBase64(buf) {
    if (!buf) return null;
    let binary = '';
    const bytes = new Uint8Array(buf);
    const chunkSize = 8192;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  function base64ToBuffer(base64) {
    if (!base64) return null;
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  /* ── Public API ── */
  return {
    DB_NAME, DB_VER, S,
    open,
    get, put, remove, getAll, getAllKeys, clear,
    // Words
    getWord, putWord, hasWord, getAllWords, countWords,
    // Audio
    getAudio, putAudio,
    // Sentences
    getSentence, putSentence, getSentencesByWord,
    // SRS
    getSRS, putSRS, getAllSRS,
    // Sessions
    getSession, putSession, getAllSessions,
    // Settings
    getSettings, putSettings,
    // Migration
    detectMigrationNeeded, runMigration, cleanupOldStores,
    // Backup
    exportAll, importAll,
    // Utils
    bufferToBase64, base64ToBuffer,
  };
})();


/* ═══════════════════════════════════════════════
   MODULE 2: MoPinyin — Pinyin Utilities
   ═══════════════════════════════════════════════ */
const MoPinyin = (() => {
  'use strict';

  function stripTones(s) {
    if (!s) return '';
    return s
      .replace(/[āáǎà]/g, 'a').replace(/[ĀÁǍÀ]/g, 'A')
      .replace(/[ēéěè]/g, 'e').replace(/[ĒÉĚÈ]/g, 'E')
      .replace(/[īíǐì]/g, 'i').replace(/[ĪÍǏÌ]/g, 'I')
      .replace(/[ōóǒò]/g, 'o').replace(/[ŌÓǑÒ]/g, 'O')
      .replace(/[ūúǔù]/g, 'u').replace(/[ŪÚǓÙ]/g, 'U')
      .replace(/[ǖǘǚǜ]/g, 'v').replace(/[ǕǗǙǛ]/g, 'V')
      .replace(/ü/g, 'v').replace(/Ü/g, 'V');
  }

  function getToned(word) {
    if (typeof window !== 'undefined' && window.pinyinPro) {
      return window.pinyinPro.pinyin(word);
    }
    // Fallback: try inline PINYIN_TONED if available
    if (typeof PINYIN_TONED !== 'undefined' && PINYIN_TONED[word]) {
      return PINYIN_TONED[word];
    }
    return word;
  }

  function getToneless(word) {
    if (typeof window !== 'undefined' && window.pinyinPro) {
      return window.pinyinPro.pinyin(word, { toneType: 'none' });
    }
    return stripTones(getToned(word));
  }

  return { stripTones, getToned, getToneless };
})();


/* ═══════════════════════════════════════════════
   MODULE 3: MoSettings — Unified Settings Manager
   ═══════════════════════════════════════════════ */
const MoSettings = (() => {
  'use strict';

  const LS_KEY = 'mo_settings_bridge_v1';
  const DEFAULTS = {
    theme: 'dark',
    cardScale: 1,
    sessionSize: 30,
    minimaxKey: '',
    openrouterKey: '',
    readerTheme: 'oled',
    readerFont: '"Taipei Sans TC Beta", "Microsoft YaHei", sans-serif',
    readerFontSize: 28,
    readerHighlight: '#38bdf8',
    readerActiveStyle: 'underline-text',
    readerAnimStyle: 'pop',
  };

  let _cache = { ...DEFAULTS };
  let _ready = false;

  async function _load() {
    try {
      const dbSettings = await MoDB.getSettings();
      _cache = { ...DEFAULTS, ...dbSettings };
    } catch (e) {
      // Fallback to localStorage bridge
      try {
        const bridge = JSON.parse(localStorage.getItem(LS_KEY) || '{}');
        _cache = { ...DEFAULTS, ...bridge };
      } catch (e2) {
        _cache = { ...DEFAULTS };
      }
    }
    _ready = true;
  }

  async function _save() {
    try {
      const existing = await MoDB.getSettings();
      await MoDB.putSettings({ ...existing, ..._cache });
    } catch (e) {
      // Fallback to localStorage bridge
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(_cache));
      } catch (e2) {}
    }
  }

  function get(k) {
    if (!_ready) console.warn('[MoSettings] Access before init');
    return _cache[k];
  }

  function set(k, v) {
    _cache[k] = v;
    _save();
  }

  function all() {
    return { ..._cache };
  }

  async function init() {
    await _load();
  }

  return { init, get, set, all, DEFAULTS };
})();


/* ═══════════════════════════════════════════════
   MODULE 4: MoBackup — Export / Import JSON
   ═══════════════════════════════════════════════ */
const MoBackup = (() => {
  'use strict';

  async function fullExport() {
    const data = await MoDB.exportAll();
    return JSON.stringify(data, null, 2);
  }

  async function fullImport(jsonString) {
    const data = JSON.parse(jsonString);
    return MoDB.importAll(data);
  }

  function downloadJSON(data, filename) {
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  async function exportAndDownload() {
    // Build export data object first (without stringifying yet)
    const data = await MoDB.exportAll();

    // Estimate byte size before heavy JSON.stringify
    const textPartLen = JSON.stringify({
      version: data.version,
      date: data.date,
      words: data.words,
      sentences: data.sentences,
      srs: data.srs,
      sessions: data.sessions,
      settings: data.settings,
    }).length;

    let audioLen = 0;
    for (const a of Object.values(data.audio || {})) {
      audioLen += (a.wordAudio || '').length;
      for (const sa of (a.sentenceAudios || [])) {
        audioLen += (sa.audio || '').length;
      }
      audioLen += 200; // JSON object overhead per record
    }

    const estimatedBytes = textPartLen + audioLen;
    const estimatedMB = (estimatedBytes / (1024 * 1024)).toFixed(1);
    const THRESHOLD = 15 * 1024 * 1024; // 15 MB

    if (estimatedBytes > THRESHOLD) {
      const proceed = confirm(
        'Backup size: ~' + estimatedMB + ' MB (mostly audio).\n\n' +
        'Large backups may be slow on mobile and crash older browsers.\n' +
        'Your audio is safe, but consider using a ZIP-based backup for\n' +
        'migrating to a new device.\n\n' +
        'Continue with JSON export?'
      );
      if (!proceed) return;
    }

    console.log('[MoBackup] Estimated size: ' + estimatedMB + ' MB, threshold: 15 MB');

    const json = JSON.stringify(data, null, 2);
    const timeStr = new Date().toTimeString().slice(0, 8).replace(/:/g, '-');
    const dateStr = new Date().toISOString().slice(0, 10);
    downloadJSON(json, `mo_backup_${dateStr}_${timeStr}.json`);
  }

  return { fullExport, fullImport, downloadJSON, exportAndDownload };
})();


/* ═══════════════════════════════════════════════
   AUTO-INIT
   ═══════════════════════════════════════════════ */
(function() {
  'use strict';
  // Open DB, run migration if needed, then init settings
  MoDB.open().then(async () => {
    console.log('[MoCommon] MoDB v4 ready');
    const flags = await MoDB.detectMigrationNeeded();
    const needsMigration = Object.values(flags).some(Boolean);
    const alreadyMigrated = localStorage.getItem('mo_db_v4_migrated');

    if (needsMigration && !alreadyMigrated) {
      console.log('[MoCommon] Migration sources detected:', flags);
      console.log('[MoCommon] Running one-time migration...');
      const results = await MoDB.runMigration();
      console.log('[MoCommon] Migration complete:', results);
      localStorage.setItem('mo_db_v4_migrated', '1');
    } else if (needsMigration && alreadyMigrated) {
      console.log('[MoCommon] Old data still present but migration already ran.');
      console.log('[MoCommon] Call MoDB.cleanupOldStores() when ready to remove old storage.');
    }

    window.__MoDB_migrationFlags = flags;
    await MoSettings.init();
  }).catch(err => {
    console.error('[MoCommon] Failed to initialize MoDB:', err);
  });
})();


/* ═══════════════════════════════════════════════
   UNIFIED THEME CYCLER  (Alt+A)
   ═══════════════════════════════════════════════ */
(function() {
  'use strict';
  const THEMES = ['midnight', 'oled', 'nordic', 'gruvbox', 'everforest'];
  const LS_KEY = 'mo_dict_theme';

  function applyTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    document.querySelectorAll('#themeSelect').forEach(function(sel) {
      if (sel.value !== name) sel.value = name;
    });
    try { localStorage.setItem(LS_KEY, name); } catch (e) {}
    if (typeof MoSettings !== 'undefined' && MoSettings.set) {
      try { MoSettings.set('theme', name); } catch (e) {}
    }
  }

  function cycleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'gruvbox';
    const idx = THEMES.indexOf(current);
    const next = THEMES[(idx + 1) % THEMES.length];
    applyTheme(next);
    showToast(next);
  }

  function showToast(name) {
    const id = 'mo-theme-toast';
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;padding:10px 18px;border-radius:8px;background:var(--panel-bg);color:var(--highlight);border:1px solid var(--border);font-family:var(--ui-font-family);font-size:13px;letter-spacing:0.08em;text-transform:uppercase;font-weight:700;box-shadow:var(--shadow-md);opacity:0;transform:translateY(-10px);transition:opacity 0.2s,transform 0.2s;pointer-events:none;';
      document.body.appendChild(el);
    }
    el.textContent = name;
    void el.offsetWidth;
    el.style.opacity = '1';
    el.style.transform = 'translateY(0)';
    clearTimeout(el._t);
    el._t = setTimeout(function() {
      el.style.opacity = '0';
      el.style.transform = 'translateY(-10px)';
    }, 1200);
  }

  document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.shiftKey && (e.key === 'x' || e.key === 'X')) {
      e.preventDefault();
      cycleTheme();
    }
  });

  // Best-effort cross-tab sync via localStorage event
  window.addEventListener('storage', function(e) {
    if (e.key === LS_KEY && e.newValue) {
      document.documentElement.setAttribute('data-theme', e.newValue);
      document.querySelectorAll('#themeSelect').forEach(function(sel) {
        if (sel.value !== e.newValue) sel.value = e.newValue;
      });
    }
  });
})();
