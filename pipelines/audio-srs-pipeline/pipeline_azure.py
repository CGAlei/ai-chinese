#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AudioSRS Pipeline (Azure Cloud edition)

This script automates the creation of an Anki-like SRS vocabulary database.
It performs the following steps:
1. Filters a raw list of Chinese words from maindata.json based on frequency (zipf) and POS.
2. Uses OpenRouter or Gemini REST APIs to generate example sentences and Spanish distractors.
3. Uses Azure Cognitive Text-to-Speech (TTS) cloud service to generate high-quality voice audio.
4. Saves MP3 audio files and synchronizes everything into the shared `vocabulary.json`.

Required env vars:
    AZURE_SPEECH_KEY      - Azure Cognitive Speech key
    AZURE_SPEECH_REGION   - Azure Cognitive Speech region (e.g. eastus)
    OPENROUTER_API_KEY    - OpenRouter API key (or GEMINI_API_KEY)
"""

import os
import sys
import json
import time
import logging
import argparse
import re
import signal
import urllib.request
import warnings
import contextlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Silence UserWarning warnings (like pkg_resources/setuptools deprecations)
warnings.filterwarnings("ignore", category=UserWarning)

# Set jieba logger to only report warnings/errors
logging.getLogger("jieba").setLevel(logging.WARNING)

# ============================================================================
# LOGGING & SIGNAL HANDLING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("AudioSRS-Azure")

# Handle Ctrl+C gracefully
import threading
_shutdown = threading.Event()

def _signal_handler(sig, frame):
    log.warning("Interrupt signal received! Finishing current batch before exiting...")
    _shutdown.set()

signal.signal(signal.SIGINT, _signal_handler)

# Silence stdout/stderr and logging temporarily to suppress noisy imports/initialization
@contextlib.contextmanager
def silence_all():
    logging.disable(logging.CRITICAL)
    try:
        with open(os.devnull, "w") as f:
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                yield
    finally:
        logging.disable(logging.NOTSET)

# Load env variables
try:
    from dotenv import load_dotenv
    # Resolve project root .env
    script_dir = Path(__file__).parent.resolve()
    root_env = script_dir.parent.parent / ".env"
    load_dotenv(dotenv_path=root_env)
except ImportError:
    pass

with silence_all():
    import jieba
    import jieba.posseg as pseg
    from wordfreq import zipf_frequency
    
    # Initialize all dictionaries fully under silence
    jieba.initialize()
    pseg.initialize()
    zipf_frequency("初始化", "zh")

# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================
BASE_DIR = Path(__file__).parent.resolve()

def load_configuration(path: Path = BASE_DIR / "gemini_tts_config.toml") -> dict:
    """Loads settings from a TOML file, falling back to safe defaults."""
    defaults = {
        "llm_provider": "openrouter",  # "openrouter" or "gemini"
        "openrouter_model": "google/gemini-2.5-flash",
        "gemini_model": "gemini-2.5-flash",
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
        "azure_voice_name": "zh-CN-XiaoxiaoNeural",
        "zipf_min": 1.8,
        "zipf_max": 3.8,
        "zipf_max_2char": 4.2,
        "audio_dir": "../../web/audio-srs/audio",
        "sent_dir": "../../web/audio-srs/sentences",
        "vocab_file": "../../web/audio-srs/data/vocabulary.json",
    }
    
    # Try parsing manually to avoid tomllib dependency if not on Python 3.11+
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                content = f.read()
            # Simple regex parser for basic strings
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if v.isdigit():
                        defaults[k] = int(v)
                    elif v.replace(".", "", 1).isdigit():
                        defaults[k] = float(v)
                    elif v.lower() == "true":
                        defaults[k] = True
                    elif v.lower() == "false":
                        defaults[k] = False
                    else:
                        defaults[k] = v
            log.info(f"Configuration loaded successfully from {path}")
        except Exception as e:
            log.warning(f"Error parsing {path}: {e}. Proceeding with default values.")
            
    return defaults

CFG = load_configuration()

# Hardcoded linguistic filters
CFG["pos_exclude"] = {"u", "p", "c", "r", "m", "q", "y", "e", "o", "h", "k", "w", "x", "zg"}
CFG["pos_proper"] = {"nr", "ns", "nt", "nz"}

# Ensure directories exist
AUDIO_DIR = (BASE_DIR / CFG.get("audio_dir", "../../web/audio-srs/audio")).resolve()
SENT_DIR = (BASE_DIR / CFG.get("sent_dir", "../../web/audio-srs/sentences")).resolve()
VOCAB_FILE = (BASE_DIR / CFG.get("vocab_file", "../../web/audio-srs/data/vocabulary.json")).resolve()

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SENT_DIR.mkdir(parents=True, exist_ok=True)
VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# AZURE TTS CLIENT
# ============================================================================
class AzureTTSManager:
    """Manages Microsoft Azure Speech Services Text-to-Speech synthesis."""
    def __init__(self):
        self.key = os.environ.get("AZURE_SPEECH_KEY")
        self.region = os.environ.get("AZURE_SPEECH_REGION", "eastus")
        
    def synthesize(self, text: str, is_sentence: bool = False) -> bytes:
        if not self.key:
            log.error("AZURE_SPEECH_KEY is missing from .env.")
            sys.exit(1)
            
        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "AudioSRS-Pipeline-Azure"
        }
        
        voice_name = CFG.get("azure_voice_name", "zh-CN-XiaoxiaoNeural")
        ssml = f"""<speak version='1.0' xml:lang='zh-CN'>
            <voice name='{voice_name}'>
                {text}
            </voice>
        </speak>"""
        
        req = urllib.request.Request(
            url,
            data=ssml.encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
        except Exception as e:
            raise RuntimeError(f"Azure TTS Cloud synthesis failed: {e}")

TTS_ENGINE = AzureTTSManager()

# ============================================================================
# LLM ENGINE (OPENROUTER / GEMINI REST API)
# ============================================================================
def call_llm(prompt: str) -> str:
    """Synchronous REST client for OpenRouter/Gemini to keep dependencies zero-weight."""
    provider = CFG.get("llm_provider", "openrouter")
    
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            log.error("Missing OPENROUTER_API_KEY in .env.")
            sys.exit(1)
            
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/CGAlei/ai-chinese",
            "X-Title": "Ai-Chinese AudioSRS"
        }
        payload = {
            "model": CFG.get("openrouter_model", "google/gemini-2.5-flash"),
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": CFG.get("llm_temperature", 0.3)
        }
    else:  # Direct Gemini API
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            log.error("Missing GEMINI_API_KEY in .env.")
            sys.exit(1)
            
        model = CFG.get("gemini_model", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": CFG.get("llm_temperature", 0.3),
                "responseMimeType": "application/json"
            }
        }
        
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    for attempt in range(CFG["llm_retries"]):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                
            if provider == "openrouter":
                return res_data["choices"][0]["message"]["content"]
            else:
                return res_data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if attempt == CFG["llm_retries"] - 1:
                raise RuntimeError(f"LLM exhausted all retries. Error: {e}")
            log.warning(f"  [LLM] Attempt {attempt+1}/{CFG['llm_retries']} failed: {e}")
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
                        pass
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
        if not entry.get("chineseAudio"):
            entry["chineseAudio"] = f'audio/{hanzi}.mp3'
        if not entry.get("sentenceAudio"):
            entry["sentenceAudio"] = f'sentences/{hanzi}.mp3'
        if not entry.get("sentenceText"):
            entry["sentenceText"] = entry.get("sentence_cn", "")
        
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
    """Submits a batch of words to OpenRouter/Gemini to generate sentences and distractors."""
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
    """Handles cloud audio generation via Azure TTS."""
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
    
    if not force_tts and has_word_audio and has_sent_audio and has_sentence_text and has_distractors:
        return False
        
    activity_occurred = False
    newly_completed = False
    
    # 1. Generate Hanzi Audio
    if force_tts or not has_word_audio:
        try:
            audio_bytes = TTS_ENGINE.synthesize(hanzi, is_sentence=False)
            safe_file_write(word_audio_path, audio_bytes)
            log.info(f"     [Azure Cloud TTS] Word audio OK: {hanzi}")
            activity_occurred = True
            entry["tts_errors"] = 0
            if not has_word_audio: newly_completed = True
        except Exception as e:
            log.error(f"     [Azure Cloud TTS] Word audio FAILED for {hanzi}: {e}")
            entry["tts_errors"] = entry.get("tts_errors", 0) + 1
            
    # 2. Generate Sentence Audio
    sentence_text = entry.get("sentence_cn", "")
    if sentence_text and (force_tts or not has_sent_audio):
        try:
            audio_bytes = TTS_ENGINE.synthesize(sentence_text, is_sentence=True)
            safe_file_write(sent_audio_path, audio_bytes)
            log.info(f"     [Azure Cloud TTS] Sentence audio OK: {hanzi}")
            activity_occurred = True
            entry["tts_errors"] = 0
            if not has_sent_audio: newly_completed = True
        except Exception as e:
            log.error(f"     [Azure Cloud TTS] Sentence audio FAILED for {hanzi}: {e}")
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
        
        has_word_audio = is_valid_mp3(AUDIO_DIR / f"{hanzi}.mp3")
        has_sent_audio = is_valid_mp3(SENT_DIR / f"{hanzi}.mp3")
        has_sentence_text = bool(entry.get("sentence_cn", "").strip())
        has_distractors = isinstance(entry.get("distractors"), list) and len(entry.get("distractors", [])) == 3

        needs = []
        if args.force_tts or not has_word_audio: needs.append("TTS(word)")
        if (args.force_tts or not has_sent_audio) and has_sentence_text: needs.append("TTS(sent)")
        if not has_sentence_text: needs.append("LLM(sent)")
        if not has_distractors: needs.append("LLM(distractors)")
        
        if not args.force_tts and not needs:
            stats["skipped"] += 1
            if args.verbose:
                log.info(f"[{idx}/{total_candidates}] SKIP {hanzi} (Already Complete)")
            elif stats["skipped"] % 500 == 0:
                log.info(f"Scanning: Checked {idx}/{total_candidates} candidates (skipped {stats['skipped']} already complete)...")
            continue

        log.info(f"[{idx}/{total_candidates}] PROCESS {hanzi} -> requires: {', '.join(needs)}")

        if args.dry_run:
            continue

        if not has_sentence_text or not has_distractors:
            llm_batch_queue.append(word_obj)
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
                    
            save_vocabulary(vocab_state)
            
            for b_word in llm_batch_queue:
                if _shutdown.is_set(): break
                process_word_audio(b_word, vocab_state, args.force_tts)
                    
            save_vocabulary(vocab_state)
            llm_batch_queue.clear()

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
    parser = argparse.ArgumentParser(description="AudioSRS Lightweight Azure Cloud TTS Pipeline")
    parser.add_argument("source", nargs="?", default="data/dict/maindata.json", help="Path to input JSON dictionary")
    parser.add_argument("--max-candidates", type=int, default=None, help="Cap the number of candidates filtered")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N items")
    parser.add_argument("--force-tts", action="store_true", help="Overwrite existing audio files")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without API/GPU calls")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose logs, including skipped items")
    
    args = parser.parse_args()
    
    # Resolve default source relative to root if needed
    if args.source == "data/dict/maindata.json":
        proj_root = BASE_DIR.parent.parent
        args.source = str((proj_root / "data/dict/maindata.json").resolve())
        
    run_pipeline(args)
