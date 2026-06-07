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

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Resolve dictionary path: env override → default relative location
const DICT_PATH = process.env.DICTIONARY_PATH
  ? path.resolve(process.env.DICTIONARY_PATH)
  : path.join(__dirname, 'data', 'vocabulary.json');

let _allCards    = null;
let _activeCards = null;
let _isDemoMode  = false;   // explicit flag — fixes the array-reference comparison bug

function loadDictionary() {
  if (_allCards) return;

  if (!fs.existsSync(DICT_PATH)) {
    throw new Error(`Dictionary not found at: ${DICT_PATH}`);
  }

  const raw = fs.readFileSync(DICT_PATH, 'utf-8');
  _allCards = JSON.parse(raw);

  // Primary filter: favorited cards that have a sentence
  const favorited = _allCards.filter(
    (c) => c.favorited === true && c.sentenceText && c.sentenceText.trim() !== ''
  );

  if (favorited.length > 0) {
    _activeCards = favorited;
    _isDemoMode  = false;
    console.log(`[Dictionary] Loaded ${favorited.length} favorited cards (with sentences).`);
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

  // 2. Filter overdue candidates
  const overdue = allCandidates.filter((c) => {
    const srs = srsMap[c.id];
    return !srs || srs.due <= now;
  });

  const pool = overdue.length > 0 ? overdue : allCandidates;
  
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
