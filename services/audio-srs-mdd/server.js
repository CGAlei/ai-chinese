/**
 * server.js — MDD (Mispronunciation Detection & Diagnosis) Backend
 *
 * Routes:
 *   GET  /api/next-card              — Serve next study card (dictionary + shadow pool)
 *   GET  /api/get-azure-token        — Secure Azure Speech token exchange
 *   POST /api/log-attempt            — Persist attempt + harvest secondary failures
 *   GET  /api/stats/:word_id         — Aggregate phoneme error stats for LLM coach
 *   GET  /api/analytics/top-words    — Top 20 critical words by error coefficient
 *   GET  /api/focused-pool           — Ordered word drill pool filtered by error type
 *   GET  /api/health                 — Quick health-check
 *
 * Static assets: serves audio from opencodeversion/audio and sentences/.
 */

import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { pinyin, convert } from 'pinyin-pro';

import db from './db.js';
import { getNextCard, getTotalActiveCards, findCardByHanzi, findMinimalPair } from './dictionary.js';
import { scoreToQuality, computeNextSRS } from './srs.js';
import { extractPhonemeErrors } from './phoneme-utils.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Global cache for Azure Speech token to prevent F0 rate limits (429) on hot reloads
let cachedToken = null;
let tokenExpiresAt = 0;

// ─── Static file serving ────────────────────────────────────────────────────
const VOCAB_ROOT = path.resolve(__dirname, '../../web/audio-srs');
app.use('/audio',     express.static(path.join(VOCAB_ROOT, 'audio')));
app.use('/sentences', express.static(path.join(VOCAB_ROOT, 'sentences')));
app.use(express.static(path.join(__dirname, 'public')));

// ─── Prepared DB statements ─────────────────────────────────────────────────

const stmtGetSRS   = db.prepare('SELECT * FROM srs_intervals WHERE word_id = ?');
const stmtAllSRS   = db.prepare('SELECT * FROM srs_intervals');
const stmtUpsertSRS = db.prepare(`
  INSERT INTO srs_intervals (word_id, ease, interval, reps, lapses, due, last_score, updated_at)
  VALUES (@word_id, @ease, @interval, @reps, @lapses, @due, @last_score, @updated_at)
  ON CONFLICT(word_id) DO UPDATE SET
    ease       = excluded.ease,
    interval   = excluded.interval,
    reps       = excluded.reps,
    lapses     = excluded.lapses,
    due        = excluded.due,
    last_score = excluded.last_score,
    updated_at = excluded.updated_at
`);
const stmtInsertAudit = db.prepare(`
  INSERT INTO phoneme_error_audit
    (word_id, attempt_at, sentence, accuracy_score, initial_error, final_error, tone_error, azure_raw)
  VALUES
    (@word_id, @attempt_at, @sentence, @accuracy_score, @initial_error, @final_error, @tone_error, @azure_raw)
`);
const stmtGetAudit = db.prepare(`
  SELECT * FROM phoneme_error_audit WHERE word_id = ? ORDER BY attempt_at DESC LIMIT 50
`);
const stmtPhonemeStats = db.prepare(`
  SELECT
    COUNT(*)            AS total_attempts,
    SUM(initial_error)  AS initial_errors,
    SUM(final_error)    AS final_errors,
    SUM(tone_error)     AS tone_errors,
    AVG(accuracy_score) AS avg_accuracy
  FROM phoneme_error_audit
  WHERE word_id = ?
`);

// ── Shadow card statements ──────────────────────────────────────────────────
const stmtAllShadowCards = db.prepare('SELECT * FROM shadow_cards');
const stmtCountShadows = db.prepare('SELECT COUNT(*) as n FROM shadow_cards');
const stmtUpsertShadowCard = db.prepare(`
  INSERT INTO shadow_cards (id, hanzi, pinyin, sentence_text, sentence_audio)
  VALUES (@id, @hanzi, @pinyin, @sentence_text, @sentence_audio)
  ON CONFLICT(id) DO NOTHING
`);
const stmtDeleteShadowCard = db.prepare('DELETE FROM shadow_cards WHERE id = ?');
const stmtDeleteSRS = db.prepare('DELETE FROM srs_intervals WHERE word_id = ?');

// ─── Routes ─────────────────────────────────────────────────────────────────

/**
 * GET /api/health
 */
app.get('/api/health', (_req, res) => {
  const shadowCount = stmtCountShadows.get().n;
  res.json({
    status: 'ok',
    totalActiveCards: getTotalActiveCards(),
    shadowCards: shadowCount,
    dbPath: 'mdd_progress.db',
    timestamp: Date.now(),
  });
});

app.get('/api/minimal-pair', (req, res) => {
  try {
    const { hanzi, char_index, error_type } = req.query;
    if (!hanzi || !error_type) {
      return res.status(400).json({ error: 'Missing query parameters: hanzi, error_type' });
    }
    if (char_index !== undefined) {
      const idx = parseInt(char_index, 10);
      const result = findMinimalPair(hanzi, idx, error_type);
      if (!result) {
        return res.status(404).json({ error: 'No minimal pair found.' });
      }
      return res.json(result);
    } else {
      // Loop over characters of hanzi to find the first minimal pair
      for (let i = 0; i < hanzi.length; i++) {
        const result = findMinimalPair(hanzi, i, error_type);
        if (result) {
          return res.json({ ...result, charIndex: i });
        }
      }
      return res.status(404).json({ error: 'No minimal pair found for any character in the word.' });
    }
  } catch (err) {
    console.error('[/api/minimal-pair]', err);
    res.status(500).json({ error: err.message });
  }
});

const stmtGetShadowCard = db.prepare('SELECT * FROM shadow_cards WHERE id = ?');

/**
 * GET /api/next-card
 * Returns the next card from the unified pool (dictionary + shadow_cards).
 */
app.get('/api/next-card', (_req, res) => {
  try {
    const allSRS = stmtAllSRS.all();
    
    // Pass a callback to getNextCard so it can fetch a specific shadow card on-demand
    // instead of loading all thousands of shadow cards into RAM.
    const fetchShadow = (id) => stmtGetShadowCard.get(id);
    
    const card = getNextCard(allSRS, fetchShadow);
    if (!card) {
      return res.status(404).json({ error: 'No active cards available.' });
    }

    // Enrich with live DB SRS state if present
    const dbSRS = stmtGetSRS.get(card.id);
    if (dbSRS) card.srs = dbSRS;

    // Pre-compute per-character toned pinyin for the sentence.
    // The frontend uses this map to label failed <ruby> characters with
    // correct diacritic pinyin (e.g. "zhōng") instead of Azure phoneme symbols.
    if (card.sentenceText) {
      const sentencePinyinMap = {};
      const chars = [...card.sentenceText];
      // Generate pinyin with tone numbers as an array for the entire sentence
      const pyNums = pinyin(card.sentenceText, { toneType: 'num', type: 'array' });
      
      // Apply 3rd tone sandhi
      for (let i = 0; i < pyNums.length - 1; i++) {
        const curr = pyNums[i];
        if (typeof curr === 'string' && curr.endsWith('3')) {
          const next = pyNums[i + 1];
          if (typeof next === 'string' && next.endsWith('3')) {
            pyNums[i] = curr.slice(0, -1) + '2';
          }
        }
      }
      
      // Populate map by index and character fallback
      chars.forEach((ch, idx) => {
        if (/[\u4e00-\u9fff]/.test(ch)) {
          const pyn = pyNums[idx];
          if (pyn) {
            const sym = /[a-z]+[0-4]/.test(pyn) ? convert(pyn) : pyn;
            sentencePinyinMap[idx] = sym;
            sentencePinyinMap[ch] = sym;
          } else {
            sentencePinyinMap[ch] = pinyin(ch, { toneType: 'symbol' });
          }
        }
      });
      card.sentencePinyinMap = sentencePinyinMap;
    }

    res.json(card);
  } catch (err) {
    console.error('[/api/next-card]', err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/get-azure-token
 * Exchanges server-side Azure Speech key for a short-lived bearer token.
 */
app.get('/api/get-azure-token', async (_req, res) => {
  const key    = process.env.AZURE_SPEECH_KEY;
  const region = process.env.AZURE_SPEECH_REGION || 'eastus';

  if (!key || key === 'your_azure_speech_key_here') {
    return res.status(503).json({
      error: 'Azure Speech key not configured. Add AZURE_SPEECH_KEY to .env',
    });
  }

  // Use cached token if valid (using a 1-minute buffer for the 10-minute Azure token)
  const now = Date.now();
  if (cachedToken && now < tokenExpiresAt) {
    return res.json({ token: cachedToken, region });
  }

  try {
    const tokenUrl = `https://${region}.api.cognitive.microsoft.com/sts/v1.0/issueToken`;
    const response = await fetch(tokenUrl, {
      method: 'POST',
      headers: {
        'Ocp-Apim-Subscription-Key': key,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Azure token exchange failed (${response.status}): ${body}`);
    }
    const token = await response.text();

    // Cache the token for 9 minutes
    cachedToken = token;
    tokenExpiresAt = Date.now() + 9 * 60 * 1000;

    res.json({ token, region });
  } catch (err) {
    console.error('[/api/get-azure-token]', err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @typedef {Object} AttemptPayload
 * @property {string} word_id
 * @property {string} [primary_hanzi_text]
 * @property {string} [sentence]
 * @property {number} [accuracy_score]
 * @property {boolean} [initial_error]
 * @property {boolean} [final_error]
 * @property {boolean} [tone_error]
 * @property {Object} [azure_raw]
 */

/**
 * Process the primary target word's attempt and update SRS.
 */
function processPrimaryAttempt(payload, now) {
  const {
    word_id, sentence, accuracy_score,
    initial_error, final_error, tone_error, azure_raw
  } = payload;

  stmtInsertAudit.run({
    word_id,
    attempt_at:    now,
    sentence:      sentence || '',
    accuracy_score: accuracy_score || 0,
    initial_error: initial_error ? 1 : 0,
    final_error:   final_error   ? 1 : 0,
    tone_error:    tone_error    ? 1 : 0,
    azure_raw:     azure_raw ? JSON.stringify(azure_raw) : null,
  });

  const currentSRS    = stmtGetSRS.get(word_id) ?? { ease: 2.5, interval: 1, reps: 0, lapses: 0 };
  const targetQuality = scoreToQuality(accuracy_score || 0);
  const nextTargetSRS = computeNextSRS(currentSRS, targetQuality);

  let deleted = false;

  // Auto-Destruction: if it's a shadow card and we scored a pass (quality >= 3)
  if (word_id.startsWith('shadow_') && targetQuality >= 3) {
    stmtDeleteShadowCard.run(word_id);
    stmtDeleteSRS.run(word_id);
    deleted = true;
  } else {
    stmtUpsertSRS.run({
      word_id,
      ease:       nextTargetSRS.ease,
      interval:   nextTargetSRS.interval,
      reps:       nextTargetSRS.reps,
      lapses:     nextTargetSRS.lapses,
      due:        nextTargetSRS.due,
      last_score: accuracy_score || 0,
      updated_at: now,
    });
  }

  return { targetQuality, nextTargetSRS, deleted };
}

/**
 * Scan Azure results for secondary word failures and log them as shadow cards.
 */
function harvestSecondaryFailures(payload, now) {
  const azureWords     = payload.azure_raw?.NBest?.[0]?.Words ?? [];
  const shadowsCreated = [];

  for (const w of azureWords) {
    const hanziToken = w?.Word ?? '';
    if (!hanziToken || hanziToken.length < 2) continue;

    const wordScore = (w.PronunciationAssessment?.AccuracyScore ?? 100) / 100;
    if (wordScore >= 0.60 || hanziToken === payload.primary_hanzi_text) continue;

    const dictMatch = findCardByHanzi(hanziToken);
    let activeId;

    if (dictMatch) {
      activeId = dictMatch.id; // Scenario A: Exists in dictionary
    } else {
      // Safety Cap: Don't harvest if we already have too many shadow cards
      const activeShadows = stmtCountShadows.get().n;
      if (activeShadows >= 50) continue;

      activeId = `shadow_${hanziToken}`; // Scenario B: Create shadow entry
      const tonedPinyin = pinyin(hanziToken, { toneType: 'symbol' });
      const parentCard = findCardByHanzi(payload.primary_hanzi_text);

      stmtUpsertShadowCard.run({
        id:             activeId,
        hanzi:          hanziToken,
        pinyin:         tonedPinyin,
        sentence_text:  payload.sentence || '',
        sentence_audio: parentCard?.sentenceAudio ?? null,
      });
      shadowsCreated.push(activeId);
    }

    const { initialError: secInit, finalError: secFinal, toneError: secTone } = extractPhonemeErrors(w);

    stmtInsertAudit.run({
      word_id:       activeId,
      attempt_at:    now,
      sentence:      payload.sentence || '',
      accuracy_score: wordScore,
      initial_error: secInit  ? 1 : 0,
      final_error:   secFinal ? 1 : 0,
      tone_error:    secTone  ? 1 : 0,
      azure_raw:     JSON.stringify(w),
    });

    const secondarySRS     = stmtGetSRS.get(activeId) ?? { ease: 2.5, interval: 1, reps: 0, lapses: 0 };
    const secondaryQuality = scoreToQuality(wordScore);
    const nextSecondarySRS = computeNextSRS(secondarySRS, secondaryQuality);

    stmtUpsertSRS.run({
      word_id:    activeId,
      ease:       nextSecondarySRS.ease,
      interval:   nextSecondarySRS.interval,
      reps:       nextSecondarySRS.reps,
      lapses:     nextSecondarySRS.lapses,
      due:        nextSecondarySRS.due,
      last_score: wordScore,
      updated_at: now,
    });
  }
  return shadowsCreated;
}

// Atomic transaction for logging an attempt
const logAttemptTx = db.transaction((payload, now) => {
  const { targetQuality, nextTargetSRS, deleted } = processPrimaryAttempt(payload, now);
  const shadowsCreated = harvestSecondaryFailures(payload, now);
  
  return {
    success:         true,
    quality:         targetQuality,
    next_srs:        nextTargetSRS,
    shadows_created: shadowsCreated,
    deleted:         deleted,
  };
});

/**
 * POST /api/log-attempt
 * Persists user attempt and extracts secondary failures securely.
 */
app.post('/api/log-attempt', (req, res) => {
  try {
    const payload = req.body;
    if (!payload.word_id) {
      return res.status(400).json({ error: 'word_id is required.' });
    }
    const result = logAttemptTx(payload, Date.now());
    res.json(result);
  } catch (err) {
    console.error('[/api/log-attempt]', err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/stats/:word_id
 * Returns aggregate phoneme stats + recent audit rows for a word (primary or shadow).
 */
app.get('/api/stats/:word_id', (req, res) => {
  try {
    const { word_id } = req.params;
    const aggregate = stmtPhonemeStats.get(word_id);
    const recent    = stmtGetAudit.all(word_id);
    const srs       = stmtGetSRS.get(word_id) ?? null;

    res.json({ word_id, aggregate, srs, recent_attempts: recent });
  } catch (err) {
    console.error('[/api/stats]', err);
    res.status(500).json({ error: err.message });
  }
});

// ─── Analytics queries ──────────────────────────────────────────────────────

/**
 * SQL-computed Error Coefficient:
 * Combines total phoneme errors with inverse average accuracy.
 * Higher = worse pronunciation. Shadow cards excluded.
 */
const stmtGetTop20Errors = db.prepare(`
  SELECT
    word_id,
    COUNT(*)            AS total_attempts,
    AVG(accuracy_score) AS avg_accuracy,
    SUM(initial_error)  AS total_shengmu_errors,
    SUM(final_error)    AS total_yunmu_errors,
    SUM(tone_error)     AS total_tone_errors,
    (SUM(initial_error + final_error + tone_error) * (1.0 - AVG(accuracy_score))) AS error_coefficient
  FROM phoneme_error_audit
  WHERE word_id NOT LIKE 'shadow_%'
  GROUP BY word_id
  HAVING total_attempts > 0 AND avg_accuracy < 0.80
  ORDER BY error_coefficient DESC
  LIMIT 20
`);

/** Focused pool filtered by error type (shengmu, yunmu, tone, or all) */
const stmtFocusedAll = db.prepare(`
  SELECT
    word_id,
    COUNT(*) AS total_attempts,
    AVG(accuracy_score) AS avg_accuracy,
    SUM(initial_error) AS total_shengmu_errors,
    SUM(final_error)   AS total_yunmu_errors,
    SUM(tone_error)    AS total_tone_errors,
    (SUM(initial_error + final_error + tone_error) * (1.0 - AVG(accuracy_score))) AS error_coefficient
  FROM phoneme_error_audit
  WHERE word_id NOT LIKE 'shadow_%'
  GROUP BY word_id
  HAVING total_attempts > 0 AND avg_accuracy < 0.80
  ORDER BY error_coefficient DESC
  LIMIT 30
`);
const stmtFocusedShengmu = db.prepare(`
  SELECT word_id, COUNT(*) AS total_attempts, AVG(accuracy_score) AS avg_accuracy,
    SUM(initial_error) AS total_shengmu_errors, SUM(final_error) AS total_yunmu_errors,
    SUM(tone_error) AS total_tone_errors,
    (SUM(initial_error) * (1.0 - AVG(accuracy_score))) AS error_coefficient
  FROM phoneme_error_audit
  WHERE word_id NOT LIKE 'shadow_%' AND initial_error = 1
  GROUP BY word_id HAVING total_attempts > 0 AND avg_accuracy < 0.80
  ORDER BY error_coefficient DESC LIMIT 30
`);
const stmtFocusedYunmu = db.prepare(`
  SELECT word_id, COUNT(*) AS total_attempts, AVG(accuracy_score) AS avg_accuracy,
    SUM(initial_error) AS total_shengmu_errors, SUM(final_error) AS total_yunmu_errors,
    SUM(tone_error) AS total_tone_errors,
    (SUM(final_error) * (1.0 - AVG(accuracy_score))) AS error_coefficient
  FROM phoneme_error_audit
  WHERE word_id NOT LIKE 'shadow_%' AND final_error = 1
  GROUP BY word_id HAVING total_attempts > 0 AND avg_accuracy < 0.80
  ORDER BY error_coefficient DESC LIMIT 30
`);
const stmtFocusedTone = db.prepare(`
  SELECT word_id, COUNT(*) AS total_attempts, AVG(accuracy_score) AS avg_accuracy,
    SUM(initial_error) AS total_shengmu_errors, SUM(final_error) AS total_yunmu_errors,
    SUM(tone_error) AS total_tone_errors,
    (SUM(tone_error) * (1.0 - AVG(accuracy_score))) AS error_coefficient
  FROM phoneme_error_audit
  WHERE word_id NOT LIKE 'shadow_%' AND tone_error = 1
  GROUP BY word_id HAVING total_attempts > 0 AND avg_accuracy < 0.80
  ORDER BY error_coefficient DESC LIMIT 30
`);

/**
 * GET /api/analytics/top-words
 * Returns the Top 20 critical words ranked by SQL-computed error coefficient.
 */
app.get('/api/analytics/top-words', (_req, res) => {
  try {
    const rows = stmtGetTop20Errors.all();
    // Enrich each row with hanzi/pinyin from dictionary
    const enriched = rows.map(row => {
      const card = findCardByHanzi(row.word_id) || {};
      return {
        ...row,
        hanzi: card.hanzi || row.word_id,
        pinyin: card.pinyin || pinyin(row.word_id, { toneType: 'symbol' }),
      };
    });
    res.json(enriched);
  } catch (err) {
    console.error('[/api/analytics/top-words]', err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/focused-pool?filter=shengmu|yunmu|tone|all
 * Returns an ordered pool of critical words for the Word Drill tab.
 * Each entry includes full card data so the frontend can render it directly.
 */
app.get('/api/focused-pool', (req, res) => {
  try {
    const filter = req.query.filter || 'all';
    let rows;
    switch (filter) {
      case 'shengmu': rows = stmtFocusedShengmu.all(); break;
      case 'yunmu':   rows = stmtFocusedYunmu.all();   break;
      case 'tone':    rows = stmtFocusedTone.all();    break;
      default:        rows = stmtFocusedAll.all();      break;
    }

    const pool = rows.map(row => {
      const card = findCardByHanzi(row.word_id);
      return {
        ...row,
        id:            card?.id || row.word_id,
        hanzi:         card?.hanzi || row.word_id,
        pinyin:        card?.pinyin || pinyin(row.word_id, { toneType: 'symbol' }),
        meaning:       card?.meaning || '',
        sentenceText:  card?.sentenceText || '',
        chineseAudio:  card?.chineseAudio || null,
        sentenceAudio: card?.sentenceAudio || null,
      };
    });
    res.json(pool);
  } catch (err) {
    console.error('[/api/focused-pool]', err);
    res.status(500).json({ error: err.message });
  }
});

// ─── Start ──────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`\n🎙️  MDD Pronunciation Coach — http://localhost:${PORT}`);
  console.log(`   SQLite DB  : ${path.resolve(__dirname, 'mdd_progress.db')}`);
  console.log(`   Dictionary : see dictionary.js output above`);
  console.log(`   Azure key  : ${process.env.AZURE_SPEECH_KEY ? '✓ configured' : '✗ MISSING — add to .env'}\n`);
});
