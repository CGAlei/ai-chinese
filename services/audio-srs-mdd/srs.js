/**
 * srs.js — SM-2 spaced repetition algorithm helpers.
 *
 * The classic SM-2 algorithm:
 *   • q = quality of response (0–5 scale; we map Azure 0–1 score onto this)
 *   • ease factor (EF): starts at 2.5, adjusts per response
 *   • interval: days to next review
 *   • lapses: counts of total failures
 *
 * We compress Azure's 0.0–1.0 pronunciation score to SM-2's 0–5 quality scale:
 *   ≥ 0.90 → 5  (perfect)
 *   ≥ 0.75 → 4  (good)
 *   ≥ 0.60 → 3  (pass)
 *   ≥ 0.45 → 2  (barely pass — treated as lapse in SM-2 terms)
 *   < 0.45 → 1  (failure)
 */

const MIN_EASE = 1.3;
const MAX_EASE = 2.5;

/**
 * Map an Azure accuracy score (0.0–1.0) to SM-2 quality (1–5).
 */
export function scoreToQuality(accuracyScore) {
  if (accuracyScore >= 0.90) return 5;
  if (accuracyScore >= 0.75) return 4;
  if (accuracyScore >= 0.60) return 3;
  if (accuracyScore >= 0.45) return 2;
  return 1;
}

/**
 * Compute the next SM-2 SRS state.
 *
 * @param {object} current  — { ease, interval, reps, lapses }
 * @param {number} quality  — SM-2 quality 1–5
 * @returns {object}        — { ease, interval, reps, lapses, due }
 */
export function computeNextSRS(current, quality) {
  let { ease, interval, reps, lapses } = current;
  const now = Date.now();

  if (quality >= 3) {
    // Successful recall
    if (reps === 0) {
      interval = 1;
    } else if (reps === 1) {
      interval = 6;
    } else {
      interval = Math.round(interval * ease);
    }
    reps += 1;
    ease = Math.max(MIN_EASE, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)));
    ease = Math.min(MAX_EASE, ease);
  } else if (quality === 2) {
    // Partial success / soft lapse: halve reps, halve interval, minor ease penalty
    lapses += 1;
    reps = Math.max(0, Math.floor(reps / 2));
    interval = Math.max(1, Math.round(interval * 0.5));
    ease = Math.max(MIN_EASE, ease - 0.1);
  } else {
    // Failure / hard lapse — reset interval, bump lapses, standard ease penalty
    lapses += 1;
    reps = 0;
    interval = 1;
    ease = Math.max(MIN_EASE, ease - 0.2);
  }

  const due = now + interval * 24 * 60 * 60 * 1000;

  return { ease, interval, reps, lapses, due };
}
