#!/usr/bin/env python3
"""
enrich_dict.py — Batch-enrich Chinese→Spanish dictionary translations via LLM.

Accepts TWO input formats:
  1. v5 MoDB backup  — JSON object with { version: 4, words, audio, sentences, srs, ... }
                       Only words[*].meaning is enriched; all other stores pass through untouched.
  2. Legacy array    — JSON array of [word, translation] pairs (backward compatible)

Identifies poorly translated entries (single-word, no "/" separator produced by
Google Translate), enriches them via LLM in efficient batches, and saves an
enriched output file without modifying the original.

Providers:
    openai      — OpenAI API  (gpt-4o-mini by default, ~$0.002 per 300 words)
    openrouter  — OpenRouter  (any model via https://openrouter.ai, one API key)

Required env vars:
    OPENAI_API_KEY       — when using --provider openai
    OPENROUTER_API_KEY   — when using --provider openrouter

Usage:
    python enrich_dict.py dictionary.json
    python enrich_dict.py dictionary.json --dry-run
    python enrich_dict.py dictionary.json --provider openrouter --model google/gemini-flash-1.5
    python enrich_dict.py dictionary.json --batch-size 30 --output enriched.json
    python enrich_dict.py dictionary.json --target-lang English
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

# Automatically load variables from .env file located in the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

# =============================================================================
# Provider Configuration
# Extend this dict to add new providers in the future.
# Both OpenAI and OpenRouter share the same openai SDK — only base_url differs.
# =============================================================================
PROVIDER_CONFIGS: dict[str, dict] = {
    "openai": {
        "base_url":      "https://api.openai.com/v1",
        "env_key":       "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "note":          "~$0.002 per 300 words — negligible cost",
    },
    "openrouter": {
        "base_url":      "https://openrouter.ai/api/v1",
        "env_key":       "OPENROUTER_API_KEY",
        "default_model": "google/gemini-flash-1.5",
        "note":          "Access to 100+ models with a single API key",
    },
}

# =============================================================================
# LLM System Prompt
# =============================================================================
SYSTEM_PROMPT = """\
You are a professional Mandarin Chinese to {target_lang} linguist and lexicographer.
Your task: enrich a vocabulary dictionary by providing concise, multi-sense translations.

You will receive a numbered list of Mandarin Chinese words or short phrases.
For each entry, return EXACTLY one output line in this format:
  N. meaning1 / meaning2 / meaning3

Rules:
- N must match the number given to you exactly.
- Provide 2 to 4 {target_lang} meanings, separated by " / ".
- Each meaning must be a SHORT word or phrase (1-4 words). No full sentences.
- Order meanings from the most common usage to the least.
- Capture different grammatical roles when relevant (e.g. verb / noun / adjective).
- Do NOT include the Chinese word in your output.
- Do NOT add explanations, parentheses, notes, or extra lines.
- Do NOT skip any number. Every input must have exactly one output line.\
"""

# =============================================================================
# Core Detection Logic
# =============================================================================

def is_poor_translation(translation: str) -> bool:
    """
    Returns True if a translation looks like a raw single-word Google Translate result
    that should be replaced by a richer LLM-generated definition.

    A translation is considered 'good' if:
      - It contains "/" (LLM multi-sense format: "ir / caminar / andar")
      - It contains "\\" (legacy separator used by some older LLM exports)

    A translation is considered 'poor' if:
      - It is empty
      - It has no separator and is 2 words or fewer (typical Google Translate output)
    """
    if not translation or not translation.strip():
        return True
    if "/" in translation:
        return False
    if "\\" in translation:
        return False
    # Single or double word with no separator → poor
    word_count = len(translation.strip().split())
    return word_count <= 2


# =============================================================================
# Batch Prompt Builder
# =============================================================================

def build_batch_prompt(words: list[str]) -> str:
    """Build a numbered list prompt from a batch of Mandarin words."""
    numbered = "\n".join(f"{i + 1}. {w}" for i, w in enumerate(words))
    return f"Enrich the translations for these Mandarin words:\n\n{numbered}"


# =============================================================================
# Response Parser
# =============================================================================

def parse_batch_response(response_text: str, words: list[str]) -> dict[str, str]:
    """
    Parse the LLM's numbered response back into a {word: translation} dict.
    Tolerates minor formatting variations from different models.
    """
    results: dict[str, str] = {}

    for line in response_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Expect: "1. meaning1 / meaning2" or "1) meaning1 / meaning2"
        for separator in (".", ")"):
            if separator in line:
                num_part, _, definition = line.partition(separator)
                try:
                    idx = int(num_part.strip()) - 1
                    if 0 <= idx < len(words):
                        cleaned = definition.strip().lstrip("-–—:").strip()
                        if cleaned:
                            results[words[idx]] = cleaned
                    break
                except ValueError:
                    continue

    return results


# =============================================================================
# Main Enrichment Pipeline
# =============================================================================

def enrich(
    input_path: str,
    output_path: Optional[str],
    provider: str,
    model: str,
    batch_size: int,
    dry_run: bool,
    target_lang: str,
    delay: float,
    in_place: bool = False,
) -> None:

    # ── Load input ────────────────────────────────────────────────────────
    logger.info(f"Loading: {input_path}")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {input_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        sys.exit(1)

    # Detect format: v5 backup (object with version + stores) vs legacy flat array
    v5_backup: Optional[dict] = None
    word_objects: list[dict] = []   # list of {id, hanzi, meaning, ...}
    dictionary: dict[str, str] = {} # extraction dict for enrichment logic

    if isinstance(raw, dict) and raw.get("version") == 4:
        v5_backup = raw
        word_objects = raw.get("words", []) if isinstance(raw.get("words"), list) else []
        logger.info("Detected v5 MoDB backup format (version 4).")
        for w in word_objects:
            if isinstance(w, dict) and w.get("id"):
                dictionary[w["id"]] = str(w.get("meaning", ""))
    elif isinstance(raw, list):
        logger.info("Detected legacy dictionary array format.")
        for entry in raw:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                word, translation = str(entry[0]), str(entry[1])
            elif isinstance(entry, dict):
                word = str(entry.get("word", entry.get("key", "")))
                translation = str(entry.get("translation", entry.get("value", "")))
            else:
                continue
            if word:
                dictionary[word] = translation
    else:
        logger.error("Unknown JSON format. Expected v5 backup object or legacy array.")
        sys.exit(1)

    # ── Analyse ──────────────────────────────────────────────────────────
    total = len(dictionary)
    poor_entries = [(w, t) for w, t in dictionary.items() if is_poor_translation(t)]
    good_count = total - len(poor_entries)

    logger.info(f"─" * 52)
    logger.info(f"Total entries       : {total}")
    logger.info(f"Already enriched    : {good_count}  (will be skipped)")
    logger.info(f"Needs enrichment    : {len(poor_entries)}")
    logger.info(f"─" * 52)

    if not poor_entries:
        logger.info("✅ Nothing to enrich. All translations already look good!")
        return

    # ── Dry run preview ───────────────────────────────────────────────────
    if dry_run:
        preview_count = min(15, len(poor_entries))
        logger.info(f"── DRY RUN PREVIEW ({preview_count} of {len(poor_entries)} entries) ──")
        for word, translation in poor_entries[:preview_count]:
            logger.info(f"  '{word}'  →  '{translation}'")
        if len(poor_entries) > preview_count:
            logger.info(f"  ... and {len(poor_entries) - preview_count} more.")
        total_batches = -(-len(poor_entries) // batch_size)
        logger.info(f"\nWould run {total_batches} API batch(es) of up to {batch_size} words each.")
        logger.info("Re-run without --dry-run to process.")
        return

    # ── Validate provider & API key ───────────────────────────────────────
    try:
        import openai
    except ImportError:
        logger.error("The 'openai' package is required. Install with: pip install openai")
        sys.exit(1)

    config = PROVIDER_CONFIGS[provider]
    api_key = os.environ.get(config["env_key"])
    if not api_key:
        logger.error(f"Missing API key: environment variable '{config['env_key']}' is not set.")
        logger.error(f"  Fix: export {config['env_key']}='your-key-here'")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key, base_url=config["base_url"])
    total_batches = -(-len(poor_entries) // batch_size)
    system_prompt = SYSTEM_PROMPT.replace("{target_lang}", target_lang)

    logger.info(f"Provider   : {provider}  ({config['note']})")
    logger.info(f"Model      : {model}")
    logger.info(f"Target lang: {target_lang}")
    logger.info(f"Batches    : {total_batches}  ({batch_size} words each)")
    logger.info(f"─" * 52)

    # ── Batch loop ────────────────────────────────────────────────────────
    enriched_count = 0
    failed_words: list[str] = []

    for batch_idx in range(0, len(poor_entries), batch_size):
        batch = poor_entries[batch_idx : batch_idx + batch_size]
        words_only = [w for w, _ in batch]
        batch_num = batch_idx // batch_size + 1

        logger.info(f"[{batch_num}/{total_batches}] Processing {len(words_only)} words...")

        try:
            prompt = build_batch_prompt(words_only)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.2,  # Low temp: consistent, structured output
            )
            response_text = response.choices[0].message.content or ""
            parsed = parse_batch_response(response_text, words_only)

            for word, new_translation in parsed.items():
                dictionary[word] = new_translation
                enriched_count += 1

            missed = set(words_only) - set(parsed.keys())
            if missed:
                logger.warning(f"  ⚠  {len(missed)} words not parsed — will keep originals.")
                failed_words.extend(missed)

            logger.info(f"  ✓  {len(parsed)} words enriched.")

        except KeyboardInterrupt:
            logger.info("\nInterrupted by user. Saving progress so far...")
            break
        except Exception as e:
            logger.error(f"  Batch {batch_num} failed: {e}")
            failed_words.extend(words_only)
            logger.info("  Continuing to next batch...")

        # Polite delay between batches to avoid rate limits
        if delay > 0 and batch_idx + batch_size < len(poor_entries):
            time.sleep(delay)

    # ── Save output ───────────────────────────────────────────────────────
    if in_place:
        output_path = input_path
    elif output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_enriched{ext}"

    now = int(time.time() * 1000)
    if v5_backup is not None:
        # Update word objects in place using the enriched dictionary
        updated_count = 0
        for w in word_objects:
            if not isinstance(w, dict):
                continue
            hanzi = w.get("id", "")
            new_meaning = dictionary.get(hanzi)
            if new_meaning is not None and new_meaning != w.get("meaning", ""):
                w["meaning"] = new_meaning
                w["enriched"] = True
                w["updatedAt"] = now
                updated_count += 1
        v5_backup["date"] = datetime.now().isoformat()
        output_data = v5_backup
        logger.info(f"Preserved v5 format — enriched {updated_count} word meanings in place.")
    else:
        output_data = [[word, translation] for word, translation in dictionary.items()]

    try:
        if in_place:
            tmp_path = output_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, output_path)
            logger.info("Atomic in-place update completed.")
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Failed to write output: {e}")
        sys.exit(1)

    # ── Final summary ─────────────────────────────────────────────────────
    logger.info(f"\n{'═' * 52}")
    logger.info(f"  ✅  Enriched  : {enriched_count} translations")
    logger.info(f"  ⏭   Skipped   : {good_count} (already good)")
    if failed_words:
        logger.warning(f"  ⚠   Failed    : {len(failed_words)} (left unchanged)")
    logger.info(f"  📁  Saved to  : {os.path.abspath(output_path)}")
    logger.info(f"{'═' * 52}")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Batch-enrich a Chinese Reader dictionary backup via LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python enrich_dict.py dictionary.json
  python enrich_dict.py dictionary.json --dry-run
  python enrich_dict.py dictionary.json --provider openrouter --model google/gemini-flash-1.5
  python enrich_dict.py dictionary.json --provider openrouter --model mistralai/mistral-7b-instruct
  python enrich_dict.py dictionary.json --batch-size 30 --output my_enriched.json
  python enrich_dict.py dictionary.json --target-lang English

Environment variables:
  OPENAI_API_KEY      Required when using --provider openai
  OPENROUTER_API_KEY  Required when using --provider openrouter
        """,
    )

    default_dict_path = os.path.join(script_dir, "Dict", "chinese_reader_dictionary_backup.json")
    parser.add_argument(
        "input",
        nargs="?",
        default=default_dict_path,
        help="Path to the dictionary JSON backup exported from Chinese Reader.",
    )
    out_group = parser.add_mutually_exclusive_group()
    out_group.add_argument(
        "--output", "-o",
        default=None,
        metavar="PATH",
        help="Output file path. Default: <input>_enriched.json (never overwrites input).",
    )
    out_group.add_argument(
        "--in-place", "-i",
        action="store_true",
        help="Enrich and overwrite the input file atomically (writes to .tmp first, then renames).",
    )
    parser.add_argument(
        "--provider", "-p",
        default="openai",
        choices=list(PROVIDER_CONFIGS.keys()),
        help="LLM provider. (default: openai)",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        metavar="MODEL",
        help=(
            "Model name override. "
            "Defaults: openai=gpt-4o-mini | openrouter=google/gemini-flash-1.5. "
            "Any OpenRouter model slug works, e.g. 'anthropic/claude-3-haiku'."
        ),
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=50,
        metavar="N",
        help="Number of words per API call. Lower if a model returns inconsistent output. (default: 50)",
    )
    parser.add_argument(
        "--target-lang", "-t",
        default="Spanish",
        metavar="LANG",
        help="Target language for translations. (default: Spanish)",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.5,
        metavar="SECS",
        help="Seconds to wait between batches to respect rate limits. (default: 0.5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which entries would be enriched without making any API calls.",
    )

    args = parser.parse_args()

    config = PROVIDER_CONFIGS[args.provider]
    model = args.model or config["default_model"]

    enrich(
        input_path=args.input,
        output_path=args.output,
        provider=args.provider,
        model=model,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        target_lang=args.target_lang,
        delay=args.delay,
        in_place=args.in_place,
    )


if __name__ == "__main__":
    main()
