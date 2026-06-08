/**
 * phoneme-utils.js — Shared phoneme error classification for Azure word results.
 *
 * Used server-side so the same logic applies to both the primary target word
 * and any secondary words harvested from the full sentence transcript.
 *
 * Azure's zh-CN phoneme set uses consonant initials (b, p, m, f, d, t, n, l,
 * g, k, h, j, q, x, zh, ch, sh, r, z, c, s, y, w) followed by vowel finals.
 * Position 0 = initial consonant cluster; position ≥ 1 = final/vowel nucleus.
 */

/**
 * Classifies phoneme-level errors from a single Azure word result object.
 *
 * @param {object} azureWord  — One item from NBest[0].Words[]
 * @returns {{ initialError: boolean, finalError: boolean, toneError: boolean }}
 */
export function extractPhonemeErrors(azureWord) {
  let initialError = false;
  let finalError   = false;
  let toneError    = false;

  const phonemes = azureWord?.Phonemes ?? [];

  for (let i = 0; i < phonemes.length; i++) {
    const ph    = phonemes[i];
    const score = ph?.PronunciationAssessment?.AccuracyScore ?? 100;

    if (score < 60) {
      const sym = (ph?.Phoneme ?? '').toLowerCase();
      // Initial: first phoneme and starts with a consonant character
      const startsConsonant = /^[bpmfdtnlgkhjqxzcsryw]/.test(sym);
      if (i === 0 && startsConsonant) {
        initialError = true;
      } else {
        finalError = true;
      }
    }
  }

  // Tone error: Azure flags this in Prosody feedback
  const toneErrorTypes =
    azureWord?.PronunciationAssessment?.Feedback?.Prosody?.Tone?.ErrorTypes;
  if (Array.isArray(toneErrorTypes) && toneErrorTypes.length > 0) {
    toneError = true;
  }

  return { initialError, finalError, toneError };
}
