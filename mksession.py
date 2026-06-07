#!/usr/bin/env python3
"""
Transcribe audio to Simplified Chinese JSON with word-level segmentation.

Usage:
    python chinread.py audio.mp3
    python chinread.py audio.mp3 --vad_filter False  # For long/continuous audio
    python chinread.py audio.mp3 --device cpu        # If no GPU

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
import os
from dotenv import load_dotenv

# Automatically load variables from .env file located in the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

# =============================================================================
# Configuration
# =============================================================================

# Suppress Python warnings globally (torchcodec, transformers, pyannote, etc.)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Chinese punctuation set
PUNCT = set('，。！？、；：""（）【】…—,.:!?;()[]""「」')

# Initialize OpenCC converter (Traditional to Simplified)
# Note: "t2s" is used to ensure consistency for Simplified Chinese learners.
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
    """
    if not characters:
        return characters

    # Step 1: Separate punctuation and content characters
    ordered = []
    clean_chars = []

    for c in characters:
        original_text = c.get("word", "")
        if not original_text:
            continue

        simplified_text = CONVERTER.convert(original_text)

        if simplified_text in PUNCT:
            ordered.append({"type": "punct", "data": {"word": simplified_text}})
        else:
            char_entry = {
                "word": simplified_text,
                "start": c.get("start"),
                "end": c.get("end"),
                "score": c.get("score"),
            }
            ordered.append({"type": "char", "data": char_entry})
            clean_chars.append(char_entry)

    if not clean_chars:
        return [item["data"] for item in ordered]

    # Step 2: Run Jieba segmentation on full text
    full_text = "".join(c["word"] for c in clean_chars)
    words = list(jieba.cut(full_text))

    # Step 3: Map Jieba words back to character timestamps
    word_entries = []
    char_idx = 0

    for word in words:
        w_len = len(word)
        if w_len == 0:
            continue

        chunk = clean_chars[char_idx : char_idx + w_len]
        char_idx += w_len

        if not chunk:
            continue

        # Aggregate timestamps and scores
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

        word_entries.append(entry)

    # Step 4: Reconstruct final list preserving punctuation positions
    result = []
    word_idx = 0
    chars_seen_in_current_word = 0
    char_count_in_current_word = len(word_entries[0]["word"]) if word_entries else 0

    for item in ordered:
        if item["type"] == "punct":
            result.append(item["data"])
        else:
            if word_idx >= len(word_entries):
                result.append(item["data"])
                continue

            chars_seen_in_current_word += 1

            if chars_seen_in_current_word == char_count_in_current_word:
                result.append(word_entries[word_idx])
                word_idx += 1
                chars_seen_in_current_word = 0
                if word_idx < len(word_entries):
                    char_count_in_current_word = len(word_entries[word_idx]["word"])

    # Append any remaining words (safety fallback)
    while word_idx < len(word_entries):
        result.append(word_entries[word_idx])
        word_idx += 1

    return result


def run_transcription(audio_path: str, args: argparse.Namespace) -> str:
    """
    Run WhisperX subprocess and return the path to the generated JSON.
    Handles VAD parameters for long audio files.
    """
    # Determine output directory (same as audio file)
    out_dir = os.path.dirname(os.path.abspath(audio_path)) or os.getcwd()
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    json_path = os.path.join(out_dir, f"{base_name}.json")

    # Get audio duration for logging
    duration = get_audio_duration(audio_path)
    if duration:
        logger.info(f"Audio duration: {duration / 60:.1f} minutes ({duration:.0f}s)")

    logger.info(f"[1/3] Starting WhisperX transcription...")
    logger.info(f"     -> Model: {args.model} | Device: {args.device}")
    logger.info(f"     -> VAD: onset={args.vad_onset} | offset={args.vad_offset}")
    if args.vad_filter is not None:
        logger.info(f"     -> VAD Filter: {args.vad_filter}")
    logger.info(f"     -> Loading model into memory (this may take 1-2 minutes)...")

    # Flush to ensure messages appear before whisperx output
    sys.stdout.flush()
    sys.stderr.flush()

    # Build command
    cmd = [
        "whisperx",
        audio_path,
        "--language",
        "zh",
        "--model",
        args.model,
        "--device",
        args.device,
        "--output_format",
        "json",
        "--output_dir",
        out_dir,
        "--vad_onset",
        str(args.vad_onset),
        "--vad_offset",
        str(args.vad_offset),
    ]

    if args.vad_filter is not None:
        cmd.extend(["--vad_filter", args.vad_filter])
    if args.compute_type:
        cmd.extend(["--compute_type", args.compute_type])
    if args.batch_size:
        cmd.extend(["--batch_size", str(args.batch_size)])

    # Environment variables to suppress warnings
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = (
        "ignore::UserWarning,ignore::DeprecationWarning,ignore::ReproducibilityWarning"
    )
    env["TRANSFORMERS_VERBOSITY"] = "error"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["HF_DATASETS_OFFLINE"] = "1"

    try:
        # Run without capture_output to show real-time progress bars
        subprocess.run(cmd, check=True, stdout=None, stderr=None, env=env)
    except subprocess.CalledProcessError as e:
        logger.error(f"WhisperX failed with return code {e.returncode}")
        logger.error("Check the output above for specific CUDA or memory errors.")
        sys.exit(1)
    except FileNotFoundError:
        logger.error(
            "'whisperx' command not found. Please ensure it is installed and in your PATH."
        )
        logger.error("Install with: pip install whisperx")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nTranscription cancelled by user.")
        sys.exit(0)

    # Verify output file exists
    if not os.path.exists(json_path):
        fallback_path = os.path.join(os.getcwd(), f"{base_name}.json")
        if os.path.exists(fallback_path):
            json_path = fallback_path
            logger.info(f"Found output at fallback location: {json_path}")
        else:
            logger.error(f"Expected output file not found: {json_path}")
            logger.error(
                "WhisperX may have failed silently. Check for disk space or permissions."
            )
            sys.exit(1)

    # Verify transcription coverage
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "segments" in data and len(data["segments"]) > 0:
            last_end = data["segments"][-1].get("end", 0)
            logger.info(
                f"     -> Transcribed duration: {last_end / 60:.1f} minutes ({last_end:.0f}s)"
            )

            if duration and last_end < duration * 0.8:
                coverage = last_end / duration * 100
                logger.warning(
                    f"     -> ⚠️  Only {coverage:.0f}% of audio was transcribed!"
                )
                logger.warning(f"     -> This may be due to VAD filtering silence.")
                logger.warning(
                    f"     -> Try: --vad_onset 0.2 --vad_offset 0.2 --vad_filter False"
                )
    except (json.JSONDecodeError, KeyError, IOError) as e:
        logger.warning(f"Could not verify transcription coverage: {e}")

    return json_path


def run_online_transcription(audio_path: str, args: argparse.Namespace) -> str:
    """
    Run OpenAI Whisper API transcription and return the path to the generated JSON.
    Handles better punctuation for Chinese text.
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

    out_dir = os.path.dirname(os.path.abspath(audio_path)) or os.getcwd()
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    json_path = os.path.join(out_dir, f"{base_name}.json")

    duration = get_audio_duration(audio_path)
    if duration:
        logger.info(f"Audio duration: {duration / 60:.1f} minutes ({duration:.0f}s)")

    logger.info(f"[1/3] Starting online OpenAI transcription...")
    logger.info(f"     -> Attempting to contact API (this may take a minute for larger files)...")

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

    # Convert response to dictionary (handling different openai library versions)
    try:
        data = response.model_dump()
    except AttributeError:
        try:
            data = response.dict()
        except AttributeError:
            data = response if isinstance(response, dict) else vars(response)

    if isinstance(data, dict):
        # OpenAI returns "words", map it to "word_segments" for process_json
        if "words" in data:
            words_arr = data.pop("words")
            # OpenAI's tokenization is highly inconsistent for Chinese (sometimes grouping words, sometimes characters).
            # To normalize this for our robust Jieba engine, we artificially split everything into strictly single characters.
            chars = []
            for w in words_arr:
                word_text = w.get("word", "")
                w_start = w.get("start", 0.0)
                w_end = w.get("end", 0.0)
                duration = w_end - w_start
                char_duration = duration / len(word_text) if len(word_text) > 0 else 0.0
                
                for i, char in enumerate(word_text):
                    chars.append({
                        "word": char,
                        "start": w_start + (i * char_duration),
                        "end": w_start + ((i + 1) * char_duration),
                        "score": 1.0
                    })
            data["word_segments"] = chars

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Failed to write temporary output file: {e}")
        sys.exit(1)

    logger.info(f"     -> Online transcription completed successfully.")
    return json_path


def process_json(json_path: str):
    """
    Load transcription JSON, convert to Simplified Chinese, and segment into words.
    """
    logger.info(f"[2/3] Segmenting words and converting to Simplified Chinese ...")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(f"JSON file not found: {json_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON file: {e}")
        sys.exit(1)

    # Process segments
    segments = data.get("segments", [])
    if not segments:
        logger.warning("No segments found in transcription. Output may be empty.")

    for i, segment in enumerate(segments):
        if "text" in segment:
            segment["text"] = CONVERTER.convert(segment["text"])
        if "words" in segment and isinstance(segment["words"], list):
            segment["words"] = group_chars_into_words(segment["words"])

    # Process root-level word_segments if present (WhisperX specific)
    if "word_segments" in data and isinstance(data["word_segments"], list):
        data["word_segments"] = group_chars_into_words(data["word_segments"])

    # Save processed JSON
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Failed to write output file: {e}")
        sys.exit(1)

    logger.info(f"[3/3] Done — saved as: {os.path.abspath(json_path)}")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio to Simplified Chinese JSON with word-level segmentation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python transcribe.py podcast.mp3
    python transcribe.py lecture.mp3 --vad_filter False
    python transcribe.py audio.mp3 --device cpu --model small
    python transcribe.py speech.mp3 --vad_onset 0.2 --vad_offset 0.2

For long/continuous audio (podcasts, lectures), use --vad_filter False
        """,
    )

    # Required arguments
    parser.add_argument(
        "audio_file", help="Path to the audio file (mp3, wav, m4a, etc.)"
    )

    # Model configuration
    parser.add_argument(
        "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        help="Whisper model size (default: medium). Larger = more accurate but slower.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cuda", "cpu"],
        help="Device to use (default: cuda). Use 'cpu' if no GPU available.",
    )
    parser.add_argument(
        "--compute_type",
        default="int8",
        choices=["int8", "float16", "float32"],
        help="Compute type (default: int8). Use float16/float32 if int8 fails.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=2,
        help="Batch size for transcription (default: 2). Lower if OOM.",
    )

    # VAD configuration (critical for long audio)
    parser.add_argument(
        "--vad_onset",
        type=float,
        default=0.3,
        help="VAD onset threshold (default: 0.3). Lower = more sensitive to speech.",
    )
    parser.add_argument(
        "--vad_offset",
        type=float,
        default=0.3,
        help="VAD offset threshold (default: 0.3). Lower = more sensitive to speech.",
    )
    parser.add_argument(
        "--vad_filter",
        type=str,
        default=None,
        choices=["True", "False"],
        help="Disable VAD filter with 'False' for continuous speech (podcasts, lectures).",
    )

    # Online configuration
    parser.add_argument(
        "--online",
        action="store_true",
        help="Use OpenAI Whisper API for transcription instead of local WhisperX (handles punctuation better).",
    )

    args = parser.parse_args()

    # Validate audio file exists
    if not os.path.exists(args.audio_file):
        logger.error(f"File not found: {args.audio_file}")
        sys.exit(1)

    # Validate file is readable
    if not os.path.isfile(args.audio_file):
        logger.error(f"Not a file: {args.audio_file}")
        sys.exit(1)

    # Check file extension (warning only)
    valid_extensions = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"]
    ext = os.path.splitext(args.audio_file)[1].lower()
    if ext not in valid_extensions:
        logger.warning(f"Uncommon audio format: {ext}. May not be supported.")

    # Run transcription pipeline
    if args.online:
        json_path = run_online_transcription(args.audio_file, args)
    else:
        # Warn about CPU usage for long audio only if running locally
        if args.device == "cpu":
            duration = get_audio_duration(args.audio_file)
            if duration and duration > 300:  # > 5 minutes
                logger.warning(
                    "CPU transcription detected for long audio. This may take a while..."
                )
        json_path = run_transcription(args.audio_file, args)
        
    process_json(json_path)


if __name__ == "__main__":
    main()
