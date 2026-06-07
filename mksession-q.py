#!/usr/bin/env python3
"""
Transcribe audio to Simplified Chinese JSON with word-level segmentation using Qwen3-ASR.

Usage:
    python mksession-q.py audio.mp3
    python mksession-q.py audio.mp3 --model 1.7b    # Use larger model (needs more VRAM)
    python mksession-q.py audio.mp3 --device cpu     # Force CPU usage

Output:
    audio.json (word-segmented, simplified Chinese, saved next to audio file)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import warnings
from typing import Any, Dict, List, Optional

import jieba
import opencc
from dotenv import load_dotenv

# Automatically load variables from .env file located in the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

# =============================================================================
# Configuration
# =============================================================================

# Suppress Python warnings globally (transformers, torch, etc.)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Chinese punctuation set
PUNCT = set('，。！？、；：""（）【】…—,.:!?;()[]""「」『』《》·• 　')

# Initialize OpenCC converter (Traditional to Simplified)
CONVERTER = opencc.OpenCC("t2s")

# =============================================================================
# Helper Functions
# =============================================================================


def get_audio_duration(audio_path: str) -> Optional[float]:
    """
    Get audio duration in seconds using ffprobe.
    Returns None if ffprobe is not available or file is invalid.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def group_chars_into_words(characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert character-level timestamps to word-level timestamps using Jieba.
    Optimized for O(N) performance with proper timestamp aggregation.
    Supports multi-character English words and preserves punctuation.
    """
    if not characters:
        return characters

    def is_chinese_char(c: str) -> bool:
        if len(c) != 1:
            return False
        val = ord(c)
        return (0x4E00 <= val <= 0x9FFF) or (0x3400 <= val <= 0x4DBF) or (val == 0x3007)

    result = []
    current_run = []

    def process_run(run: List[Dict[str, Any]]):
        if not run:
            return
        
        # 1. Convert to simplified Chinese
        simplified_chars = []
        for c in run:
            orig_word = c.get("word", "")
            simp_word = CONVERTER.convert(orig_word)
            simplified_chars.append({
                "word": simp_word,
                "start": c.get("start"),
                "end": c.get("end"),
                "score": c.get("score")
            })

        # 2. Run Jieba segmentation on the simplified Chinese run
        run_text = "".join(c["word"] for c in simplified_chars)
        words = list(jieba.cut(run_text))

        # 3. Map Jieba words back to character timestamps
        char_idx = 0
        for word in words:
            w_len = len(word)
            if w_len == 0:
                continue

            chunk = simplified_chars[char_idx : char_idx + w_len]
            char_idx += w_len

            if not chunk:
                continue

            starts = [c["start"] for c in chunk if c.get("start") is not None]
            ends = [c["end"] for c in chunk if c.get("end") is not None]
            scores = [c["score"] for c in chunk if c.get("score") is not None]

            entry = {"word": word}
            if starts:
                entry["start"] = min(starts)
            if ends:
                entry["end"] = max(ends)
            if scores:
                entry["score"] = round(sum(scores) / len(scores), 3)

            result.append(entry)

    for c in characters:
        word = c.get("word", "")
        # If it's a single Chinese character, add to current run
        if is_chinese_char(word):
            current_run.append(c)
        else:
            # Process existing run of Chinese characters first
            if current_run:
                process_run(current_run)
                current_run = []
            
            # Convert non-Chinese content (like English or punctuation) to simplified
            word_simp = CONVERTER.convert(word)
            entry = {
                "word": word_simp,
            }
            if c.get("start") is not None:
                entry["start"] = c["start"]
            if c.get("end") is not None:
                entry["end"] = c["end"]
            if c.get("score") is not None:
                entry["score"] = c["score"]
                
            result.append(entry)

    # Process any final run
    if current_run:
        process_run(current_run)

    return result


def reconstruct_aligned_words(original_text: str, aligned_items: List[Dict[str, Any]], offset_sec: float) -> List[Dict[str, Any]]:
    """
    Reconstruct the character/word sequence from original_text preserving all punctuation,
    spaces, brackets, and case, while mapping aligned timestamps from aligned_items.
    """
    # Helper to check if a character is silent (punctuation, space, brackets)
    def is_silent_char(char: str) -> bool:
        if char.isspace():
            return True
        return char in PUNCT or char in '()（）[]【】{}｛｝<>《》「」『』·•*-_+=|\\/`~@#$%^&'

    # Normalization helper for alignment comparison
    def normalize_str(s: str) -> str:
        return "".join(c.lower() for c in s if not is_silent_char(c))

    output = []
    orig_idx = 0
    align_idx = 0
    
    n_orig = len(original_text)
    n_align = len(aligned_items)
    
    # Start time for silent characters at the beginning of the chunk
    last_time = offset_sec
    if n_align > 0:
        last_time = aligned_items[0].get("start", offset_sec)

    while orig_idx < n_orig:
        char = original_text[orig_idx]
        
        # 1. Handle silent characters (spaces, punctuation, brackets)
        if is_silent_char(char):
            next_start = last_time
            if align_idx < n_align:
                next_start = aligned_items[align_idx].get("start", last_time)
            
            output.append({
                "word": char,
                "start": last_time,
                "end": next_start,
                "score": 1.0
            })
            orig_idx += 1
            last_time = next_start
            continue
            
        # 2. Handle content characters/words
        if align_idx < n_align:
            item = aligned_items[align_idx]
            item_word = item.get("word", "")
            norm_item = normalize_str(item_word)
            
            if not norm_item:
                align_idx += 1
                continue
                
            match_len = 0
            accum_norm = ""
            
            for offset in range(n_orig - orig_idx):
                curr_char = original_text[orig_idx + offset]
                if not is_silent_char(curr_char):
                    accum_norm += curr_char.lower()
                
                if accum_norm == norm_item:
                    match_len = offset + 1
                    break
                    
            if match_len > 0:
                matched_substring = original_text[orig_idx : orig_idx + match_len]
                output.append({
                    "word": matched_substring,
                    "start": item.get("start", last_time),
                    "end": item.get("end", last_time),
                    "score": item.get("score", 1.0)
                })
                orig_idx += match_len
                align_idx += 1
                last_time = item.get("end", last_time)
            else:
                output.append({
                    "word": char,
                    "start": item.get("start", last_time),
                    "end": item.get("end", last_time),
                    "score": 1.0
                })
                orig_idx += 1
                if len(norm_item) <= 1:
                    align_idx += 1
                    last_time = item.get("end", last_time)
        else:
            output.append({
                "word": char,
                "start": last_time,
                "end": last_time + 0.1,
                "score": 1.0
            })
            orig_idx += 1
            last_time += 0.1

    return output


# =============================================================================
# Qwen3-ASR Local Pipeline
# =============================================================================



def run_local_qwen_transcription(audio_path: str, args: argparse.Namespace) -> Dict[str, Any]:
    """
    Run local Qwen3-ASR model transcription and Qwen3-ForcedAligner sequentially
    on 30-second chunks to conserve VRAM and avoid Out-Of-Memory (OOM) errors on 4GB GPUs.
    """
    try:
        import torch
        from qwen_asr import Qwen3ASRModel
        from qwen_asr import Qwen3ForcedAligner
        from qwen_asr.inference.utils import normalize_audio_input, split_audio_into_chunks, SAMPLE_RATE
    except ImportError:
        logger.error("The 'qwen-asr' package is required for local transcription.")
        logger.error("Please install it or use the --online flag.")
        sys.exit(1)

    # Determine device and dtype
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA is not available. Falling back to CPU.")
        device = "cpu"

    # Setup appropriate precision
    if device == "cuda":
        # Ampere/Ada cards support bfloat16 better than float16
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        dtype_str = "bfloat16" if dtype == torch.bfloat16 else "float16"
    else:
        dtype = torch.float32
        dtype_str = "float32"

    # Map model selection
    asr_model_name = "Qwen/Qwen3-ASR-0.6B"
    if args.model == "1.7b":
        asr_model_name = "Qwen/Qwen3-ASR-1.7B"

    aligner_model_name = "Qwen/Qwen3-ForcedAligner-0.6B"

    # Load and chunk the audio first
    logger.info("     -> Loading and preprocessing audio file...")
    try:
        wav = normalize_audio_input(audio_path)
        # Split into chunks of 30 seconds for optimal memory usage
        chunks = split_audio_into_chunks(wav=wav, sr=SAMPLE_RATE, max_chunk_sec=30.0)
        logger.info(f"     -> Audio duration: {len(wav)/SAMPLE_RATE:.1f}s, split into {len(chunks)} chunks.")
    except Exception as e:
        logger.error(f"Failed to preprocess audio: {e}")
        sys.exit(1)

    try:
        # Load only the ASR model
        model = Qwen3ASRModel.from_pretrained(
            pretrained_model_name_or_path=asr_model_name,
            dtype=dtype,
            device_map=device,
        )
        logger.info("     -> Transcribing audio chunks sequentially...")
        chunk_texts = []
        for idx, (chunk_wav, offset_sec) in enumerate(chunks):
            logger.info(f"        -> Transcribing chunk {idx+1}/{len(chunks)} (offset: {offset_sec:.1f}s)...")
            results = model.transcribe(
                audio=(chunk_wav, SAMPLE_RATE),
                return_time_stamps=False,
                language="Chinese"
            )
            chunk_text = results[0].text if results else ""
            chunk_texts.append((chunk_wav, offset_sec, chunk_text))
    except Exception as e:
        if device == "cuda":
            logger.warning(f"ASR Step failed on CUDA ({e}). Freeing memory and falling back to CPU...")
            if 'model' in locals():
                del model
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            
            # Switch to CPU
            device = "cpu"
            dtype = torch.float32
            dtype_str = "float32"
            try:
                logger.info(f"[1/3] Step A (CPU Fallback): Loading ASR Model on CPU...")
                model = Qwen3ASRModel.from_pretrained(
                    pretrained_model_name_or_path=asr_model_name,
                    dtype=dtype,
                    device_map="cpu",
                )
                logger.info("     -> Transcribing audio chunks sequentially on CPU...")
                chunk_texts = []
                for idx, (chunk_wav, offset_sec) in enumerate(chunks):
                    logger.info(f"        -> Transcribing chunk {idx+1}/{len(chunks)} (offset: {offset_sec:.1f}s)...")
                    results = model.transcribe(
                        audio=(chunk_wav, SAMPLE_RATE),
                        return_time_stamps=False,
                        language="Chinese"
                    )
                    chunk_text = results[0].text if results else ""
                    chunk_texts.append((chunk_wav, offset_sec, chunk_text))
            except Exception as e_cpu:
                logger.error(f"ASR Transcription failed on CPU: {e_cpu}")
                sys.exit(1)
        else:
            logger.error(f"ASR Transcription failed: {e}")
            sys.exit(1)

    # Unload ASR model to completely free GPU memory
    logger.info("     -> Unloading ASR model to free VRAM...")
    if 'model' in locals():
        del model
    import gc
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    # Step B: Load the Forced Aligner model
    logger.info("     -> Step B: Loading Forced Aligner into memory...")
    logger.info(f"     -> Aligner Model: {aligner_model_name} | Device: {device}")

    try:
        aligner = Qwen3ForcedAligner.from_pretrained(
            aligner_model_name,
            dtype=dtype,
            device_map=device,
        )
        logger.info("     -> Aligning text with audio chunk-by-chunk...")
        raw_chars = []
        full_text_parts = []
        for idx, (chunk_wav, offset_sec, chunk_text) in enumerate(chunk_texts):
            if chunk_text.strip():
                full_text_parts.append(chunk_text)
                logger.info(f"        -> Aligning chunk {idx+1}/{len(chunks)} (text: '{chunk_text[:15]}...')...")
                align_results = aligner.align(
                    audio=[(chunk_wav, SAMPLE_RATE)],
                    text=[chunk_text],
                    language=["Chinese"]
                )
                
                if align_results and align_results[0] is not None:
                    chunk_aligned_items = []
                    for item in align_results[0]:
                        chunk_aligned_items.append({
                            "word": item.text,
                            "start": round(item.start_time + offset_sec, 3),
                            "end": round(item.end_time + offset_sec, 3),
                            "score": 1.0
                        })
                    reconstructed = reconstruct_aligned_words(chunk_text, chunk_aligned_items, offset_sec)
                    raw_chars.extend(reconstructed)
    except Exception as e:
        if device == "cuda":
            logger.warning(f"Forced Aligner step failed on CUDA ({e}). Freeing memory and falling back to CPU...")
            if 'aligner' in locals():
                del aligner
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            
            # Switch to CPU
            device = "cpu"
            dtype = torch.float32
            try:
                logger.info("     -> Loading Forced Aligner on CPU...")
                aligner = Qwen3ForcedAligner.from_pretrained(
                    aligner_model_name,
                    dtype=dtype,
                    device_map="cpu",
                )
                logger.info("     -> Aligning text with audio chunk-by-chunk on CPU...")
                raw_chars = []
                full_text_parts = []
                for idx, (chunk_wav, offset_sec, chunk_text) in enumerate(chunk_texts):
                    if chunk_text.strip():
                        full_text_parts.append(chunk_text)
                        logger.info(f"        -> Aligning chunk {idx+1}/{len(chunks)} (text: '{chunk_text[:15]}...')...")
                        align_results = aligner.align(
                            audio=[(chunk_wav, SAMPLE_RATE)],
                            text=[chunk_text],
                            language=["Chinese"]
                        )
                        
                        if align_results and align_results[0] is not None:
                            chunk_aligned_items = []
                            for item in align_results[0]:
                                chunk_aligned_items.append({
                                    "word": item.text,
                                    "start": round(item.start_time + offset_sec, 3),
                                    "end": round(item.end_time + offset_sec, 3),
                                    "score": 1.0
                                })
                            reconstructed = reconstruct_aligned_words(chunk_text, chunk_aligned_items, offset_sec)
                            raw_chars.extend(reconstructed)
            except Exception as e_cpu:
                logger.warning(f"Forced alignment failed on CPU: {e_cpu}. Outputting transcription without word timestamps.")
        else:
            logger.warning(f"Forced alignment failed: {e}. Outputting transcription without word timestamps.")

    # Unload Aligner model
    logger.info("     -> Unloading Forced Aligner...")
    if 'aligner' in locals():
        del aligner
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    transcribed_text = "".join(full_text_parts)
    logger.info(f"     -> Complete Transcription: {transcribed_text}")

    # Duration of audio
    duration = len(wav) / SAMPLE_RATE if 'wav' in locals() else None
    if not duration and raw_chars:
        duration = raw_chars[-1]["end"]

    # Wrap in segments structure compatible with the frontend
    simplified_text = CONVERTER.convert(transcribed_text)
    
    # Group characters into words using Jieba
    grouped_words = group_chars_into_words(raw_chars)

    data = {
        "segments": [
            {
                "text": simplified_text,
                "start": 0.0,
                "end": duration or 0.0,
                "words": grouped_words
            }
        ],
        "word_segments": grouped_words
    }

    return data


# =============================================================================
# Online Transcription Fallback
# =============================================================================


def run_online_transcription(audio_path: str, args: argparse.Namespace) -> Dict[str, Any]:
    """
    Run OpenAI Whisper API transcription and return the formatted transcription data.
    """
    try:
        import openai
    except ImportError:
        logger.error("The 'openai' package is required for online transcription.")
        logger.error("Please install it with: pip install openai")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable is not set.")
        logger.error("Please export it e.g., export OPENAI_API_KEY='your_key_here'")
        sys.exit(1)

    duration = get_audio_duration(audio_path)

    logger.info(f"[1/3] Starting online OpenAI transcription...")
    logger.info(f"     -> Contacting API (this may take a minute)...")

    client = openai.OpenAI(api_key=api_key)

    try:
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                prompt="这里是一段录音，请保留标点符号：，、。！？",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]
            )
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}")
        sys.exit(1)

    # Convert response to dictionary
    try:
        data = response.model_dump()
    except AttributeError:
        try:
            data = response.dict()
        except AttributeError:
            data = response if isinstance(response, dict) else vars(response)

    simplified_text = CONVERTER.convert(data.get("text", ""))

    # Convert word segments into normalized format
    aligned_items = []
    if isinstance(data, dict) and "words" in data:
        for w in data.get("words", []):
            aligned_items.append({
                "word": CONVERTER.convert(w.get("word", "")),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
                "score": 1.0
            })

    # Reconstruct timestamps for punctuation, spaces, and brackets
    reconstructed_chars = reconstruct_aligned_words(simplified_text, aligned_items, 0.0)

    # Group characters into words using Jieba
    grouped_words = group_chars_into_words(reconstructed_chars)

    formatted_data = {
        "segments": [
            {
                "text": simplified_text,
                "start": 0.0,
                "end": duration or (grouped_words[-1]["end"] if grouped_words else 0.0),
                "words": grouped_words
            }
        ],
        "word_segments": grouped_words
    }

    return formatted_data


# =============================================================================
# Main Program
# =============================================================================


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio to Simplified Chinese JSON with word-level segmentation using Qwen3-ASR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python mksession-q.py audio.mp3
    python mksession-q.py audio.mp3 --model 1.7b
    python mksession-q.py audio.mp3 --device cpu
    python mksession-q.py audio.mp3 --online
        """,
    )

    # Required arguments
    parser.add_argument(
        "audio_file", help="Path to the audio file (mp3, wav, m4a, etc.)"
    )

    # Configuration options
    parser.add_argument(
        "--model",
        default="0.6b",
        choices=["0.6b", "1.7b"],
        help="Qwen3-ASR model size (default: 0.6b). Use 1.7b for higher accuracy if you have enough VRAM.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cuda", "cpu"],
        help="Device to use (default: cuda). Use 'cpu' if no GPU available.",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Use OpenAI Whisper API for transcription instead of local Qwen3-ASR.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save the output JSON file (default: same directory as the audio file).",
    )

    args = parser.parse_args()

    # Validate audio file exists
    if not os.path.exists(args.audio_file):
        logger.error(f"File not found: {args.audio_file}")
        sys.exit(1)

    if not os.path.isfile(args.audio_file):
        logger.error(f"Not a file: {args.audio_file}")
        sys.exit(1)

    # Determine output path
    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    else:
        out_dir = os.path.dirname(os.path.abspath(args.audio_file)) or os.getcwd()
    base_name = os.path.splitext(os.path.basename(args.audio_file))[0]
    json_path = os.path.join(out_dir, f"{base_name}.json")

    # Run transcription
    if args.online:
        transcription_data = run_online_transcription(args.audio_file, args)
    else:
        # Check audio duration for CPU usage warning
        if args.device == "cpu":
            duration = get_audio_duration(args.audio_file)
            if duration and duration > 300:  # > 5 minutes
                logger.warning(
                    "CPU transcription detected for long audio. This may take a while..."
                )
        transcription_data = run_local_qwen_transcription(args.audio_file, args)

    # Step 2 & 3: Save processed JSON
    logger.info(f"[2/3] Segmenting words and converting to Simplified Chinese ...")

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(transcription_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Failed to write output file: {e}")
        sys.exit(1)

    logger.info(f"[3/3] Done — saved as: {os.path.abspath(json_path)}")


if __name__ == "__main__":
    main()
