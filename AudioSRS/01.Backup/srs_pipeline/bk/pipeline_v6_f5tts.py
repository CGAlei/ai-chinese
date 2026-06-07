#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AudioSRS Pipeline v6.0 — F5-TTS Local Audio + Gemini LLM

This script automates the creation of an Anki-like SRS vocabulary database.
It performs the following steps:
1. Filters a raw list of Chinese words based on frequency (zipf) and part-of-speech.
2. Uses Gemini LLM to generate natural Chinese example sentences and Spanish distractors.
3. Uses a locally running F5-TTS model (via GPU) to generate high-quality voice clones.
4. Saves the MP3 audio files and synchronizes everything into `vocabulary.json`.

Author: Antigravity & User
Date: May 2026
"""

import os
import sys
import json
import time
import logging
import argparse
import io
import tempfile
import shutil
import gc
import re
import signal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

if not shutil.which("ffmpeg"):
    sys.exit("CRITICAL ERROR: 'ffmpeg' binary is missing. Please install it and add it to your PATH.")

# ============================================================================
# LOGGING & SIGNAL HANDLING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("AudioSRS")

# Global event to handle graceful shutdown (Ctrl+C)
import threading
_shutdown = threading.Event()

def _signal_handler(sig, frame):
    log.warning("Interrupt signal received! Finishing current batch before exiting...")
    _shutdown.set()

signal.signal(signal.SIGINT, _signal_handler)

# ============================================================================
# DEPENDENCY CHECKS
# ============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import tomllib
except ImportError:
    tomllib = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    sys.exit("CRITICAL ERROR: Please install google-genai ('pip install google-genai')")

try:
    from pydub import AudioSegment
except ImportError:
    sys.exit("CRITICAL ERROR: Please install pydub ('pip install pydub') and ensure ffmpeg is installed on your system.")

import jieba.posseg as pseg
from wordfreq import zipf_frequency

# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================
BASE_DIR = Path(__file__).parent.resolve()

def load_configuration(path: Path = BASE_DIR / "gemini_tts_config.toml") -> dict:
    """Loads settings from a TOML file, falling back to safe defaults."""
    defaults = {
        "gemini_key_env": "GEMINI_API_KEY",
        "gemini_model_llm": "gemini-3.1-flash-lite-preview",
        "llm_temperature": 0.3,
        "llm_retries": 5,
        "llm_backoff": 2,
        "llm_batch_size": 5,
        "llm_prompt_template": (
            "You are a Chinese teacher. Return JSON: each key is word ID, value has "
            "\"sentence_cn\" (natural Chinese sentence including hanzi) and \"distractors\": "
            "[wrong1, wrong2, wrong3] — three WRONG Spanish meanings. Plausible but incorrect. "
            "No correct meaning or synonyms. ONLY JSON, no markdown.\n\n{lines}"
        ),
        "llm_fallback_template": (
            "Return ONLY JSON: {{\"{sid}\": {{\"sentence_cn\":\"...\",\"distractors\":[\"x\",\"y\",\"z\"]}}}}\n"
            "Word: {hanzi} | Meaning: {meanings} | Pinyin: {pinyin}\n"
            "Rules: sentence MUST include \"{hanzi}\". Distractors are WRONG Spanish meanings."
        ),
        "f5_ref_audio": "reference.wav",
        "f5_ref_text": "这是一个测试声音",
        "word_prompt_prefix": "",
        "word_prompt_suffix": "",
        "sent_prompt_prefix": "",
        "sent_prompt_suffix": "",
        "mp3_bitrate": "128k",
        "zipf_min": 1.8,
        "zipf_max": 3.8,
        "zipf_max_2char": 4.2,
        "audio_dir": "audio",
        "sent_dir": "sentences",
    }
    
    if tomllib and path.exists():
        try:
            with path.open("rb") as f:
                user_config = tomllib.load(f)
            defaults.update(user_config)
            log.info(f"Configuration loaded successfully from {path}")
        except Exception as e:
            log.warning(f"Error parsing {path}: {e}. Proceeding with default values.")
    elif path.exists():
        log.warning("Python < 3.11 does not support tomllib natively. Proceeding with default values.")
        
    return defaults

CFG = load_configuration()

# Hardcoded linguistic filters
CFG["pos_exclude"] = {"u", "p", "c", "r", "m", "q", "y", "e", "o", "h", "k", "w", "x", "zg"}
CFG["pos_proper"] = {"nr", "ns", "nt", "nz"}

# Ensure directories exist
AUDIO_DIR = BASE_DIR / CFG.get("audio_dir", "audio")
SENT_DIR = BASE_DIR / CFG.get("sent_dir", "sentences")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SENT_DIR.mkdir(parents=True, exist_ok=True)
VOCAB_FILE = BASE_DIR / "vocabulary.json"

# ============================================================================
# F5-TTS ENGINE (LAZY LOADED)
# ============================================================================
class LocalTTSManager:
    """Manages the F5-TTS local GPU model for voice cloning and synthesis."""
    def __init__(self):
        self._model = None
        
    def get_model(self):
        """Lazy loads the F5-TTS model into VRAM only when first needed."""
        if self._model is None:
            log.info("Booting F5-TTS Engine. Loading model weights into GPU VRAM...")
            try:
                from f5_tts.api import F5TTS
                self._model = F5TTS(model="F5TTS_Base", device="cuda")
                log.info("F5-TTS successfully loaded into CUDA VRAM.")
            except ImportError:
                log.error("F5-TTS is not installed. Run: pip install f5-tts torch torchaudio soundfile")
                sys.exit(1)
            except Exception as e:
                log.error(f"Failed to initialize GPU TTS Model: {e}")
                sys.exit(1)
        return self._model

    def synthesize(self, text: str, is_sentence: bool = False) -> bytes:
        """Synthesizes text into an MP3 byte stream using voice cloning."""
        model = self.get_model()
        
        # Apply optional prefixes/suffixes
        prefix = CFG['sent_prompt_prefix'] if is_sentence else CFG['word_prompt_prefix']
        suffix = CFG['sent_prompt_suffix'] if is_sentence else CFG['word_prompt_suffix']
        final_text = f"{prefix}{text}{suffix}".strip()
        
        ref_audio_path = BASE_DIR / CFG.get("f5_ref_audio", "reference.wav")
        ref_text = CFG.get("f5_ref_text", "这是一个测试声音")
        
        if not ref_audio_path.exists():
            raise RuntimeError(f"Reference audio missing: '{ref_audio_path}'. F5-TTS requires this to clone the voice.")
            
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
            
        try:
            # 1. GPU Audio Synthesis
            for attempt in range(2):
                try:
                    audio_data, sample_rate, _ = model.infer(
                        ref_file=str(ref_audio_path),
                        ref_text=ref_text,
                        gen_text=final_text,
                        nfe_step=16 if attempt == 0 else 8, # Fallback to faster/lighter inference on OOM
                        cfg_strength=2.0
                    )
                    break
                except RuntimeError as e:
                    if "out of memory" in str(e).lower() and attempt == 0:
                        log.warning("[VRAM] OOM detected. Clearing cache and retrying with reduced nfe_step=8...")
                        gc.collect()
                        import torch
                        torch.cuda.empty_cache()
                        continue
                    raise
            
            # 2. Write raw array to temporary WAV
            sf.write(tmp_wav, audio_data, sample_rate)
            
            # 3. Convert WAV to compressed MP3
            seg = AudioSegment.from_wav(tmp_wav)
            mp3_buffer = io.BytesIO()
            seg.export(mp3_buffer, format="mp3", bitrate=CFG["mp3_bitrate"])
            mp3_bytes = mp3_buffer.getvalue()
            
            if len(mp3_bytes) < 1024:
                raise RuntimeError("Generated audio file is suspiciously small (<1KB).")
                
            return mp3_bytes
            
        finally:
            # Cleanup temporary files and GPU VRAM to prevent OutOfMemory errors
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)
            try:
                import torch
                gc.collect()
                torch.cuda.empty_cache()
            except ImportError:
                pass

TTS_ENGINE = LocalTTSManager()

# ============================================================================
# LLM ENGINE (GEMINI)
# ============================================================================
def call_llm(prompt: str) -> str:
    """Synchronous call to Gemini API with robust backoff and rate-limit handling."""
    key_env_var = CFG.get("gemini_key_env", "GEMINI_API_KEY")
    api_key = os.environ.get(key_env_var, key_env_var)
    
    if not api_key or api_key == "GEMINI_API_KEY":
        log.error(f"Missing Gemini API Key. Please set {key_env_var} in your environment or .toml file.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    for attempt in range(CFG["llm_retries"]):
        try:
            response = client.models.generate_content(
                model=CFG["gemini_model_llm"],
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=CFG["llm_temperature"],
                    response_mime_type="application/json",
                ),
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if attempt == CFG["llm_retries"] - 1:
                raise RuntimeError(f"LLM exhausted all retries. Last error: {err_str}")
                
            log.warning(f"  [LLM] Attempt {attempt+1}/{CFG['llm_retries']} failed: {err_str}")
            
            # Smart Rate Limit parsing
            if "429" in err_str:
                match = re.search(r"retry in ([0-9.]+)s", err_str)
                delay = float(match.group(1)) + 2.0 if match else 60.0
                delay = min(delay, 300.0) # Cap at 5 minutes
                log.info(f"  [LLM] Quota exceeded. Sleeping dynamically for {delay:.1f}s...")
                time.sleep(delay)
            else:
                time.sleep(CFG["llm_backoff"] * (attempt + 1))
    return ""

# ============================================================================
# UTILITIES & HELPERS
# ============================================================================
def extract_json(text: str) -> dict:
    """Safely extracts and parses JSON from markdown-formatted LLM responses."""
    text = re.sub(r"^```json\s*|^```\s*$|//.*$", "", text.strip(), flags=re.M)
    try:
        return json.loads(text)
    except Exception:
        start_idx = text.find("{")
        if start_idx == -1:
            return {}
        depth = 0
        for i, ch in enumerate(text[start_idx:], start=start_idx):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start_idx:i+1])
                    except Exception:
                        pass # If it fails, keep searching for the real closing brace
    return {}

def is_hanzi(text: str) -> bool:
    """Returns True if the string consists entirely of Chinese characters."""
    return bool(text and all("\u4e00" <= char <= "\u9fff" for char in text))

def extract_meanings(word_dict: dict) -> List[str]:
    """Extracts and normalizes Spanish meanings from a dictionary entry."""
    raw_meaning = word_dict.get("meaning", "").lower()
    raw_meaning = re.sub(r"\s*/\s*", ",", raw_meaning)
    return [p.strip() for p in raw_meaning.split(",") if p.strip()]

def is_valid_mp3(path: Path) -> bool:
    """Checks if a file exists, is reasonably sized, and has an MP3 header."""
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        with path.open("rb") as f:
            header = f.read(4)
        if len(header) < 4:
            return False
        # ID3 tag or MPEG ADTS sync word
        if header[:3] == b"ID3" or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
            return True
    except Exception:
        pass
    return False

def validate_llm_response(word: dict, response: dict) -> Tuple[bool, str]:
    """Validates that the LLM generated proper sentences and distractors."""
    hanzi = word.get("hanzi", "")
    sentence = response.get("sentence_cn", "")
    distractors = response.get("distractors", [])
    
    if not sentence:
        return False, "Empty sentence"
    if hanzi not in sentence:
        return False, f"Target word '{hanzi}' is missing from the sentence"
    if not isinstance(distractors, list) or len(distractors) != 3:
        return False, f"Expected 3 distractors, got {len(distractors) if isinstance(distractors, list) else type(distractors)}"
    if not all(isinstance(x, str) and x.strip() for x in distractors):
        return False, "One or more distractors are empty or invalid"
        
    meanings = [x.lower() for x in extract_meanings(word)]
    for dist in distractors:
        if dist.lower().strip() in meanings:
            return False, f"Distractor '{dist}' is too similar to the real meaning"
            
    return True, "ok"

def safe_file_write(path: Path, data: bytes):
    """Writes data atomically to prevent corrupted files if interrupted."""
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)

# ============================================================================
# PIPELINE CORE LOGIC
# ============================================================================
def load_existing_vocabulary() -> Dict[str, dict]:
    """Loads the compiled JSON dictionary."""
    if not VOCAB_FILE.exists():
        return {}
    try:
        data = json.loads(VOCAB_FILE.read_text("utf-8"))
        return {w["id"]: w for w in data if "id" in w}
    except Exception as e:
        log.warning(f"Failed to load vocabulary cache: {e}. Starting fresh.")
        return {}

def save_vocabulary(vocab_dict: Dict[str, dict]):
    """Standardizes and saves the vocabulary entries back to JSON."""
    out_list = []
    defaults = [
        ("favorited", False), ("interval", 1), ("ease", 2.5),
        ("due", int(time.time() * 1000)), ("reps", 0), ("lapses", 0),
        ("hidden", False), ("createdAt", int(time.time() * 1000)),
        ("tts_errors", 0)
    ]
    
    for word_obj in vocab_dict.values():
        entry = dict(word_obj)
        entry["meaning"] = re.sub(r"\s*/\s*", ",", entry.get("meaning", ""))
        
        # Link paths relative to the project root
        hanzi = entry.get("hanzi", "")
        entry.setdefault("chineseAudio", f'audio/{hanzi}.mp3')
        entry.setdefault("sentenceAudio", f'sentences/{hanzi}.mp3')
        entry.setdefault("sentenceText", entry.get("sentence_cn", ""))
        
        # Apply Anki/SRS default states if missing
        for key, val in defaults:
            entry.setdefault(key, val)
            
        out_list.append(entry)
        
    tmp_path = VOCAB_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(out_list, ensure_ascii=False, indent=2), "utf-8")
    backup_path = VOCAB_FILE.with_suffix(".json.bak")
    if VOCAB_FILE.exists():
        VOCAB_FILE.replace(backup_path)
    tmp_path.replace(VOCAB_FILE)

def filter_candidates(words: List[dict], limit: Optional[int] = None) -> List[dict]:
    """Filters out invalid, overly rare, or overly common words based on linguistic rules."""
    log.info("Filtering vocabulary candidates...")
    approved = []
    
    for w in words:
        hanzi = w.get("hanzi", "")
        if len(hanzi) < 2 or len(hanzi) > 6 or not is_hanzi(hanzi):
            continue
            
        freq = zipf_frequency(hanzi, "zh")
        if freq == 0 or freq < CFG["zipf_min"]:
            continue
        if len(hanzi) == 2 and freq > CFG["zipf_max_2char"]:
            continue
        if len(hanzi) >= 3 and freq > CFG["zipf_max"]:
            continue
            
        pos_tags = [flag for _, flag in pseg.cut(hanzi)]
        if all(tag in CFG["pos_exclude"] for tag in pos_tags) or all(tag in CFG["pos_proper"] for tag in pos_tags):
            continue
            
        approved.append(w)
        
    # Sort by frequency (most common first) and cap
    approved = sorted(approved, key=lambda x: zipf_frequency(x.get("hanzi", ""), "zh"), reverse=True)
    if limit:
        approved = approved[:limit]
        
    log.info(f"Approved {len(approved)} viable candidates for processing.")
    return approved

def enrich_llm_batch(batch: List[dict]) -> Dict[str, dict]:
    """Submits a batch of words to Gemini to generate sentences and distractors."""
    if not batch:
        return {}
        
    ids = [w["id"] for w in batch]
    formatted_lines = "\n".join(
        f'{i+1}. ID: {w["id"]} | Hanzi: {w["hanzi"]} | Pinyin: {w.get("pinyin", "")} | Meaning: {", ".join(extract_meanings(w))}'
        for i, w in enumerate(batch)
    )
    
    # Primary Batch Request
    prompt = CFG["llm_prompt_template"].format(lines=formatted_lines)
    response_data = extract_json(call_llm(prompt))
    
    validated_results = {}
    if isinstance(response_data, dict):
        for sid, val in response_data.items():
            if isinstance(val, dict) and sid in ids:
                validated_results[sid] = val
                
    # Fallback for failed or invalid generations
    for word in batch:
        sid = word["id"]
        if sid in validated_results:
            is_valid, reason = validate_llm_response(word, validated_results[sid])
            if is_valid:
                continue
            log.warning(f"  [INVALID {sid}] {reason}. Retrying individually...")
            validated_results.pop(sid, None)
            
        fallback_prompt = CFG["llm_fallback_template"].format(
            sid=sid,
            hanzi=word["hanzi"],
            meanings=", ".join(extract_meanings(word)),
            pinyin=word.get("pinyin", "")
        )
        try:
            fallback_res = extract_json(call_llm(fallback_prompt))
            if isinstance(fallback_res, dict) and sid in fallback_res:
                cand = fallback_res[sid]
                is_valid, reason = validate_llm_response(word, cand)
                if is_valid:
                    validated_results[sid] = cand
                    log.info(f"  [FALLBACK OK] {sid}")
                else:
                    log.warning(f"  [FALLBACK INVALID] {sid} - {reason}")
        except Exception as e:
            log.error(f"  Fallback failed for {sid}: {e}")
            
    return validated_results

def process_word_audio(word_obj: dict, vocab: Dict[str, dict], force_tts: bool) -> bool:
    """Handles audio generation for a single word and its sentence."""
    sid, hanzi = word_obj["id"], word_obj["hanzi"]
    entry = vocab.get(sid, dict(word_obj))
    
    if entry.get("tts_errors", 0) >= 3:
        log.warning(f"  [TTS] '{hanzi}' has failed 3 times in the past. Skipping permanently.")
        return False
        
    word_audio_path = AUDIO_DIR / f"{hanzi}.mp3"
    sent_audio_path = SENT_DIR / f"{hanzi}.mp3"
    
    has_word_audio = is_valid_mp3(word_audio_path)
    has_sent_audio = is_valid_mp3(sent_audio_path)
    has_sentence_text = bool(entry.get("sentence_cn", "").strip())
    has_distractors = isinstance(entry.get("distractors"), list) and len(entry.get("distractors", [])) == 3
    
    # If everything is complete and we aren't forcing an overwrite, skip.
    if not force_tts and has_word_audio and has_sent_audio and has_sentence_text and has_distractors:
        return False
        
    activity_occurred = False
    newly_completed = False
    
    # 1. Generate Hanzi Audio
    if force_tts or not has_word_audio:
        try:
            audio_bytes = TTS_ENGINE.synthesize(hanzi, is_sentence=False)
            safe_file_write(word_audio_path, audio_bytes)
            log.info(f"     [TTS] Word audio OK: {hanzi}")
            activity_occurred = True
            entry["tts_errors"] = 0
            if not has_word_audio: newly_completed = True
        except Exception as e:
            log.error(f"     [TTS] Word audio FAILED for {hanzi}: {e}")
            entry["tts_errors"] = entry.get("tts_errors", 0) + 1
            
    # 2. Generate Sentence Audio
    sentence_text = entry.get("sentence_cn", "")
    if sentence_text and (force_tts or not has_sent_audio):
        try:
            audio_bytes = TTS_ENGINE.synthesize(sentence_text, is_sentence=True)
            safe_file_write(sent_audio_path, audio_bytes)
            log.info(f"     [TTS] Sentence audio OK: {hanzi}")
            activity_occurred = True
            entry["tts_errors"] = 0
            if not has_sent_audio: newly_completed = True
        except Exception as e:
            log.error(f"     [TTS] Sentence audio FAILED for {hanzi}: {e}")
            entry["tts_errors"] = entry.get("tts_errors", 0) + 1
            
    if newly_completed and entry.get("reps", 0) == 0:
        now = int(time.time() * 1000)
        entry["createdAt"] = now
        entry["due"] = now
            
    vocab[sid] = entry
    return activity_occurred

def run_pipeline(args):
    """Main execution orchestrator."""
    src_file = Path(args.source)
    if not src_file.exists():
        log.error(f"Source file not found: {src_file}")
        sys.exit(1)

    # 1. Load Source Data
    try:
        raw_data = json.loads(src_file.read_text("utf-8"))
        raw_words = raw_data.get("words", raw_data) if isinstance(raw_data, dict) else raw_data
        log.info(f"Loaded {len(raw_words)} source words from {src_file}")
    except Exception as e:
        log.error(f"Failed to parse JSON source: {e}")
        sys.exit(1)

    # 2. Filter Candidates & Load State
    candidates = filter_candidates(raw_words, args.max_candidates)
    if args.limit:
        candidates = candidates[:args.limit]

    vocab_state = load_existing_vocabulary()
    log.info(f"Loaded existing vocabulary state: {len(vocab_state)} items")

    total_candidates = len(candidates)
    stats = {"processed": 0, "skipped": 0, "failed": 0}
    llm_batch_queue = []

    # 3. Main Processing Loop
    for idx, word_obj in enumerate(candidates, 1):
        if _shutdown.is_set():
            log.warning("Shutdown flag detected. Saving state and halting...")
            break

        sid, hanzi = word_obj["id"], word_obj["hanzi"]
        entry = vocab_state.get(sid, dict(word_obj))
        
        # State discovery
        has_word_audio = is_valid_mp3(AUDIO_DIR / f"{hanzi}.mp3")
        has_sent_audio = is_valid_mp3(SENT_DIR / f"{hanzi}.mp3")
        has_sentence_text = bool(entry.get("sentence_cn", "").strip())
        has_distractors = isinstance(entry.get("distractors"), list) and len(entry.get("distractors", [])) == 3

        # Assess Needs
        needs = []
        if args.force_tts or not has_word_audio: needs.append("TTS(word)")
        if (args.force_tts or not has_sent_audio) and has_sentence_text: needs.append("TTS(sent)")
        if not has_sentence_text: needs.append("LLM(sent)")
        if not has_distractors: needs.append("LLM(distractors)")
        
        # Fully processed already?
        if not args.force_tts and not needs:
            stats["skipped"] += 1
            log.info(f"[{idx}/{total_candidates}] SKIP {hanzi} (Already Complete)")
            continue

        log.info(f"[{idx}/{total_candidates}] PROCESS {hanzi} -> requires: {', '.join(needs)}")

        if args.dry_run:
            continue

        # Enqueue for LLM processing if missing text data
        if not has_sentence_text or not has_distractors:
            llm_batch_queue.append(word_obj)
            
            # Wait until batch is full or we hit the end of the list
            if len(llm_batch_queue) < CFG["llm_batch_size"] and idx < total_candidates:
                continue

        # Flush LLM Queue
        if llm_batch_queue:
            log.info(f"  [LLM] Processing text batch of {len(llm_batch_queue)} words...")
            enriched_data = enrich_llm_batch(llm_batch_queue)
            
            for b_word in llm_batch_queue:
                b_sid = b_word["id"]
                if b_sid in enriched_data:
                    e = vocab_state.get(b_sid, dict(b_word))
                    e["sentence_cn"] = enriched_data[b_sid].get("sentence_cn", "")
                    e["distractors"] = enriched_data[b_sid].get("distractors", [])
                    vocab_state[b_sid] = e
                else:
                    log.warning(f"  [LLM] Failed to generate valid text for {b_sid}")
                    
            save_vocabulary(vocab_state) # Commit text progress
            
            # Flush TTS Queue for the items we just got text for
            for b_word in llm_batch_queue:
                if _shutdown.is_set(): break
                process_word_audio(b_word, vocab_state, args.force_tts)
                    
            save_vocabulary(vocab_state) # Commit audio progress
            llm_batch_queue.clear()

        # Handle TTS for words that already had text but just needed audio regenerated
        elif needs:
            process_word_audio(word_obj, vocab_state, args.force_tts)

    # Final sweep
    if llm_batch_queue and not _shutdown.is_set():
        log.info(f"  [LLM] Processing final text batch of {len(llm_batch_queue)} words...")
        enriched_data = enrich_llm_batch(llm_batch_queue)
        
        for b_word in llm_batch_queue:
            b_sid = b_word["id"]
            if b_sid in enriched_data:
                e = vocab_state.get(b_sid, dict(b_word))
                e["sentence_cn"] = enriched_data[b_sid].get("sentence_cn", "")
                e["distractors"] = enriched_data[b_sid].get("distractors", [])
                vocab_state[b_sid] = e
            else:
                log.warning(f"  [LLM] Failed to generate valid text for {b_sid}")
                
        save_vocabulary(vocab_state)
        
        for b_word in llm_batch_queue:
            if _shutdown.is_set(): break
            process_word_audio(b_word, vocab_state, args.force_tts)
                
        llm_batch_queue.clear()

    save_vocabulary(vocab_state)
    
    # Calculate truthful metrics based on final disk state
    total_complete = 0
    for w in candidates:
        e = vocab_state.get(w["id"], {})
        if is_valid_mp3(AUDIO_DIR / f"{w['hanzi']}.mp3") and \
           is_valid_mp3(SENT_DIR / f"{w['hanzi']}.mp3") and \
           bool(e.get("sentence_cn", "").strip()) and \
           isinstance(e.get("distractors"), list) and len(e.get("distractors", [])) == 3:
            total_complete += 1
            
    stats["processed"] = max(0, total_complete - stats["skipped"])
    stats["failed"] = total_candidates - total_complete
    
    log.info("=" * 50)
    log.info(f"EXECUTION COMPLETE")
    log.info(f"Total Evaluated: {total_candidates}")
    log.info(f"Successfully Processed: {stats['processed']}")
    log.info(f"Skipped (Cached): {stats['skipped']}")
    log.info(f"Failed/Incomplete: {max(0, stats['failed'])}")
    log.info("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AudioSRS v6.0 F5-TTS Pipeline")
    parser.add_argument("source", nargs="?", default="maindata.json", help="Path to input JSON dictionary")
    parser.add_argument("--max-candidates", type=int, default=None, help="Cap the number of candidates filtered")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N items")
    parser.add_argument("--force-tts", action="store_true", help="Overwrite existing audio files")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API/GPU calls")
    
    args = parser.parse_args()
    run_pipeline(args)
