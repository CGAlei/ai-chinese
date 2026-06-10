/**
 * dictionary.js — Loads and filters the read-only vocabulary dictionary.
 *
 * Filtering rules:
 *   • favorited === true  (the active study set)
 *   • sentenceText must be non-empty (we need something to read)
 *
 * If zero cards pass the filter, DEMO MODE activates using the first 20 cards
 * that have a sentence, so the app is always testable before any words are starred.
 *
 * getNextCard() now also accepts SQLite shadow_cards rows so the combined pool
 * (favorited dictionary words + ghost words) feeds a single unified SRS queue.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { pinyin, getInitialAndFinal, getNumOfTone } from 'pinyin-pro';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Resolve dictionary path: env override → default relative location
const DICT_PATH = process.env.DICTIONARY_PATH
  ? path.resolve(__dirname, process.env.DICTIONARY_PATH)
  : path.resolve(__dirname, '../../web/audio-srs/data/vocabulary.json');

let _allCards    = null;
let _activeCards = null;
let _isDemoMode  = false;   // explicit flag — fixes the array-reference comparison bug
let _lastMtime   = 0;

function loadDictionary() {
  if (!fs.existsSync(DICT_PATH)) {
    throw new Error(`Dictionary not found at: ${DICT_PATH}`);
  }

  const stat = fs.statSync(DICT_PATH);
  const mtime = stat.mtimeMs;

  if (_allCards && mtime === _lastMtime) {
    return;
  }

  const raw = fs.readFileSync(DICT_PATH, 'utf-8');
  _allCards = JSON.parse(raw);
  _lastMtime = mtime;

  // Primary filter: favorited cards that have a sentence
  const favorited = _allCards.filter(
    (c) => c.favorited === true && c.sentenceText && c.sentenceText.trim() !== ''
  );

  if (favorited.length > 0) {
    _activeCards = favorited;
    _isDemoMode  = false;
    console.log(`[Dictionary] Loaded ${favorited.length} favorited cards (with sentences) from disk.`);
  } else {
    // Demo fallback: first 20 cards that have a sentence
    const withSentence = _allCards.filter(
      (c) => c.sentenceText && c.sentenceText.trim() !== ''
    );
    _activeCards = withSentence.slice(0, 20);
    _isDemoMode  = true;
    console.log(
      `[Dictionary] ⚠️  No favorited cards found — running in DEMO MODE with ${_activeCards.length} cards.`
    );
  }
}

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Cross-references a hanzi string against the full master dictionary.
 * Used during secondary error harvesting to decide Scenario A vs B.
 *
 * @param {string} hanzi — The Chinese characters to look up (exact match)
 * @returns {object|undefined} The matching vocabulary card, or undefined
 */
export function findCardByHanzi(hanzi) {
  loadDictionary();
  if (!hanzi) return undefined;
  return _allCards.find((c) => c.hanzi === hanzi || c.id === hanzi);
}

/**
 * Returns the next card to study from the unified pool.
 * Pool = favorited dictionary cards + SQLite shadow_cards rows.
 *
 * Priority: cards whose SM-2 "due" timestamp has passed come first.
 *
 * @param {object[]} srsIntervals  — All rows from srs_intervals table
 * @param {function} fetchShadow   — Callback to fetch a shadow card by ID from the DB
 * @returns {object|null}
 */
export function getNextCard(srsIntervals, fetchShadow) {
  loadDictionary();

  const now = Date.now();
  const srsMap = {};
  
  // Track all shadow card IDs that have SRS data
  const shadowIds = new Set();
  
  for (const row of srsIntervals) {
    srsMap[row.word_id] = row;
    if (row.word_id.startsWith('shadow_')) {
      shadowIds.add(row.word_id);
    }
  }

  // 1. Gather all candidates (Dictionary + Shadow IDs)
  // We only consider shadow cards that have an SRS row (meaning they were harvested)
  const allCandidates = [
    ..._activeCards.map(c => ({ id: c.id, isDict: true })),
    ...Array.from(shadowIds).map(id => ({ id, isDict: false }))
  ];
  
  if (allCandidates.length === 0) return null;

  // 2. Filter dictionary cards that are due for the current study session.
  // A dictionary card is session-due if it has never been reviewed, is mathematically due,
  // or hasn't been reviewed in the last 4 hours (ensuring favorites always take priority on startup).
  const SESSION_WINDOW = 4 * 60 * 60 * 1000; // 4 hours session window
  const sessionDueDict = allCandidates.filter(c => {
    if (!c.isDict) return false;
    const srs = srsMap[c.id];
    if (!srs) return true; // Never reviewed
    if (srs.due <= now) return true; // Mathematically due
    return (now - (srs.updated_at || 0)) > SESSION_WINDOW; // Due for a new study session
  });

  let pool;
  if (sessionDueDict.length > 0) {
    // Session-due favorites take absolute priority
    pool = sessionDueDict;
  } else {
    // Otherwise, check for overdue candidates in general (which includes overdue shadow cards)
    const overdue = allCandidates.filter((c) => {
      const srs = srsMap[c.id];
      return !srs || srs.due <= now;
    });

    if (overdue.length > 0) {
      pool = overdue;
    } else {
      // If nothing is overdue, prioritize active dictionary cards first
      const activeDict = allCandidates.filter(c => c.isDict);
      pool = activeDict.length > 0 ? activeDict : allCandidates;
    }
  }
  
  // 3. Select a random candidate
  const selected = pool[Math.floor(Math.random() * pool.length)];

  // 4. Resolve the candidate into a full Card object
  let card;
  if (selected.isDict) {
    card = _activeCards.find(c => c.id === selected.id);
  } else {
    // Fetch on demand to avoid RAM bloat
    const sc = fetchShadow(selected.id);
    if (!sc) return null;
    
    card = {
      id:            sc.id,
      hanzi:         sc.hanzi,
      pinyin:        sc.pinyin,
      meaning:       'Incidental Error Tracking',
      sentenceText:  sc.sentence_text,
      chineseAudio:  null,
      sentenceAudio: sc.sentence_audio,
      isShadow:      true,
    };
  }

  return {
    id:            card.id,
    hanzi:         card.hanzi,
    pinyin:        card.pinyin,
    meaning:       card.meaning,
    sentenceText:  card.sentenceText,
    chineseAudio:  card.chineseAudio  ?? null,
    sentenceAudio: card.sentenceAudio ?? null,
    isShadow:      card.isShadow      ?? false,
    srs: srsMap[card.id] ?? {
      ease:     card.ease     ?? 2.5,
      interval: card.interval ?? 1,
      reps:     card.reps     ?? 0,
      lapses:   card.lapses   ?? 0,
      due:      card.due      ?? now,
    },
    isDemoMode: _isDemoMode,
  };
}

export function getTotalActiveCards() {
  loadDictionary();
  return _activeCards?.length ?? 0;
}

export function getDictionaryPath() {
  return DICT_PATH;
}

/**
 * Finds a minimal pair card in the master dictionary for a given target character and error type.
 *
 * @param {string} targetHanzi - The target word/sentence Hanzi string
 * @param {number} charIndex - The index of the character that failed
 * @param {string} errorType - 'initial' (shengmu), 'final' (yunmu), or 'tone' (biansheng)
 * @returns {object|null} Structured minimal pair details
 */
export function findMinimalPair(targetHanzi, charIndex, errorType) {
  loadDictionary();
  if (!targetHanzi) return null;

  const char = targetHanzi[charIndex];
  if (!char) return null;

  const targetPinyin = pinyin(char, { toneType: 'symbol' });
  const sym = pinyin(char, { toneType: 'symbol' });
  const tone = parseInt(getNumOfTone(sym)) || 0;
  const pyn = pinyin(char, { toneType: 'num' });

  const parsed = getInitialAndFinal(pyn);
  const initial = parsed.initial;
  const final = parsed.final.replace(/[0-4]/g, '');

  const contrasts = [];
  if (errorType === 'tone') {
    const tones = [1, 2, 3, 4].filter(t => t !== tone);
    for (const t of tones) {
      contrasts.push(initial + final + t);
    }
  } else if (errorType === 'shengmu' || errorType === 'initial') {
    let altInitials = [];
    if (['zh', 'ch', 'sh'].includes(initial)) altInitials = ['z', 'c', 's'];
    else if (['z', 'c', 's'].includes(initial)) altInitials = ['zh', 'ch', 'sh'];
    else if (initial === 'n') altInitials = ['l'];
    else if (initial === 'l') altInitials = ['n'];
    else altInitials = ['bpmfdtnlgkhjqxzcsryw'.replace(initial, '')[0]];

    for (const ai of altInitials) {
      contrasts.push(ai + final + tone);
    }
  } else if (errorType === 'yunmu' || errorType === 'final') {
    let altFinal = final;
    if (final.endsWith('ng')) altFinal = final.slice(0, -2) + 'n';
    else if (final.endsWith('n')) altFinal = final + 'g';
    else altFinal = final + 'o';

    contrasts.push(initial + altFinal + tone);
  }

  // Scan master dictionary for a card containing any of the contrast syllables
  for (const c of _allCards) {
    if (!c.pinyin || !c.hanzi) continue;
    // Skip if it contains the target character
    if (c.hanzi.includes(char)) continue;

    const cChars = [...c.hanzi];
    for (const cc of cChars) {
      const ccNum = pinyin(cc, { toneType: 'num' });
      if (contrasts.includes(ccNum)) {
        return {
          targetChar: char,
          targetPinyin: targetPinyin,
          contrastChar: cc,
          contrastPinyin: pinyin(cc, { toneType: 'symbol' }),
          contrastCard: {
            id: c.id,
            hanzi: c.hanzi,
            pinyin: c.pinyin,
            meaning: c.meaning,
            chineseAudio: c.chineseAudio || null
          }
        };
      }
    }
  }
  return null;
}

/**
 * Toggles the favorited status of a card in the master JSON dictionary on disk.
 * Updates both the memory cache and the file.
 *
 * @param {string} wordId - The target word/card ID to toggle
 * @returns {boolean|null} The new favorited status, or null if card not found
 */
export function toggleCardFavorite(wordId) {
  loadDictionary();
  const card = _allCards.find(c => c.id === wordId || c.hanzi === wordId);
  if (!card) return null;

  card.favorited = !card.favorited;

  try {
    fs.writeFileSync(DICT_PATH, JSON.stringify(_allCards, null, 2), 'utf-8');
    _lastMtime = fs.statSync(DICT_PATH).mtimeMs;
    console.log(`[Dictionary] Successfully toggled favorite for '${wordId}' to ${card.favorited}`);
  } catch (err) {
    console.error(`[Dictionary] Failed to write updated favorite to ${DICT_PATH}:`, err);
    throw err;
  }

  // Re-filter active cards to update study queue instantly
  const favorited = _allCards.filter(
    (c) => c.favorited === true && c.sentenceText && c.sentenceText.trim() !== ''
  );

  if (favorited.length > 0) {
    _activeCards = favorited;
    _isDemoMode = false;
  } else {
    const withSentence = _allCards.filter(
      (c) => c.sentenceText && c.sentenceText.trim() !== ''
    );
    _activeCards = withSentence.slice(0, 20);
    _isDemoMode = true;
  }

  return card.favorited;
}
