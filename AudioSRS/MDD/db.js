/**
 * db.js — Initializes and exports the standalone SQLite database.
 *
 * Tables:
 *  1. srs_intervals      — SM-2 spaced-repetition state per word
 *  2. phoneme_error_audit — per-attempt granular sound/tone failure log
 *
 * This file is intentionally isolated from the read-only dictionary JSON.
 * All writes to the dictionary happen through the vocabulary file itself;
 * this DB only tracks practice statistics.
 */

import Database from 'better-sqlite3';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = path.join(__dirname, 'mdd_progress.db');

const db = new Database(DB_PATH);

// Enable WAL mode for better concurrent-read performance
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// ─── Schema ────────────────────────────────────────────────────────────────

db.exec(`
  CREATE TABLE IF NOT EXISTS srs_intervals (
    word_id     TEXT PRIMARY KEY,       -- matches vocabulary.json "id" field
    ease        REAL    NOT NULL DEFAULT 2.5,
    interval    INTEGER NOT NULL DEFAULT 1,   -- days until next review
    reps        INTEGER NOT NULL DEFAULT 0,   -- total successful reviews
    lapses      INTEGER NOT NULL DEFAULT 0,   -- total failures
    due         INTEGER NOT NULL DEFAULT 0,   -- Unix ms timestamp of next review
    last_score  REAL,                         -- 0.0-1.0 accuracy from last attempt
    updated_at  INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
  );

  CREATE TABLE IF NOT EXISTS phoneme_error_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id     TEXT    NOT NULL,          -- vocabulary card ID
    attempt_at  INTEGER NOT NULL DEFAULT (unixepoch() * 1000),
    sentence    TEXT,                      -- the sentence that was read
    -- SM-2 context at time of attempt
    accuracy_score  REAL,                  -- 0.0–1.0 overall Azure score
    -- Phoneme-level boolean flags (set by Azure sub-syllable analysis)
    initial_error   INTEGER NOT NULL DEFAULT 0,  -- 1 = initial consonant wrong
    final_error     INTEGER NOT NULL DEFAULT 0,  -- 1 = final/rhyme wrong
    tone_error      INTEGER NOT NULL DEFAULT 0,  -- 1 = tone wrong
    -- Raw Azure word-level JSON for future LLM ingestion
    azure_raw       TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_audit_word ON phoneme_error_audit (word_id);
  CREATE INDEX IF NOT EXISTS idx_audit_time ON phoneme_error_audit (attempt_at);

  CREATE TABLE IF NOT EXISTS shadow_cards (
    id              TEXT PRIMARY KEY,   -- e.g. "shadow_明天"
    hanzi           TEXT NOT NULL,
    pinyin          TEXT NOT NULL,      -- proper toned pinyin: "míng tiān"
    sentence_text   TEXT NOT NULL,      -- context sentence from the triggering attempt
    sentence_audio  TEXT                -- borrowed from parent card (may be NULL)
  );
`);

export default db;
