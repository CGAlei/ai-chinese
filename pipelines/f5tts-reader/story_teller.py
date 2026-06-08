#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
F5-TTS Chinese Storyteller Pipeline
Optimized for NVIDIA Mobile RTX 3050 Ti (4GB VRAM Max)
"""

import argparse
import json
import os
import re
import sys
import numpy as np
import torch
import torchaudio
import jieba
from pydub import AudioSegment

# F5-TTS Imports
try:
    from f5_tts.api import F5TTS
    from f5_tts.infer.utils_infer import preprocess_ref_audio_text
    from f5_tts.model.utils import convert_char_to_pinyin
except ImportError:
    print("Error: Could not import F5-TTS libraries. Ensure you are running in the correct conda environment where F5-TTS is installed.")
    sys.exit(1)

# Fallback constants in case they change in utils_infer
try:
    from f5_tts.infer.utils_infer import (
        target_sample_rate,
        hop_length,
        n_mel_channels,
        mel_spec_type,
        target_rms,
    )
except ImportError:
    target_sample_rate = 24000
    hop_length = 256
    n_mel_channels = 100
    mel_spec_type = "vocos"
    target_rms = 0.1

# =====================================================================
# 1. Strictly Chinese Text Normalizer
# =====================================================================

def num_to_chinese(num: int) -> str:
    """Converts an integer to standard Chinese place-value representation."""
    if num == 0:
        return "零"
    
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    units = ["", "十", "百", "千"]
    
    if num < 0:
        return "负" + num_to_chinese(-num)
        
    def section_to_chinese(section):
        ans = ""
        zero = False
        for i in range(4):
            v = (section // (10 ** (3 - i))) % 10
            if v == 0:
                if ans != "" and not zero:
                    zero = True
            else:
                if zero:
                    ans += "零"
                    zero = False
                ans += digits[v] + units[3 - i]
        
        # Clean up '一十' at the start (e.g., 15 becomes 十五, not 一十五)
        if ans.startswith("一十"):
            ans = ans[1:]
        # Remove trailing zero
        if ans.endswith("零"):
            ans = ans[:-1]
        return ans

    sections = []
    temp = num
    while temp > 0:
        sections.append(temp % 10000)
        temp //= 10000
        
    big_units = ["", "万", "亿", "万亿"]
    res = ""
    for idx, sec in enumerate(sections):
        if sec == 0:
            if idx > 0 and len(sections) > idx + 1 and sections[idx + 1] > 0 and sections[idx - 1] > 0:
                # Add "零" if we have a zero section between non-zero sections
                if not res.startswith("零"):
                    res = "零" + res
            continue
        
        sec_str = section_to_chinese(sec)
        
        # Check if we need to insert "零" between this section and the previous one
        if idx > 0 and sections[idx - 1] > 0 and sections[idx - 1] < 1000:
            res = sec_str + big_units[idx] + "零" + res
        else:
            res = sec_str + big_units[idx] + res
            
    # Clean up double zeros
    res = re.sub(r'零+', '零', res)
    if res.startswith("零"):
        res = res[1:]
    if res.endswith("零"):
        res = res[:-1]
        
    return res if res else "零"


def float_to_chinese(num: float) -> str:
    """Converts a float number to standard Chinese representation."""
    parts = str(num).split('.')
    whole = int(parts[0])
    dec = parts[1]
    
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    dec_chinese = "".join(digits[int(d)] for d in dec)
    return num_to_chinese(whole) + "点" + dec_chinese


def normalize_text(text: str) -> str:
    """Normalizes Western numbers, years, decimals, and percent in the input string."""
    # 1. Convert percentages (e.g., 25% -> 百分之二十五)
    def replace_percent(match):
        val_str = match.group(1)
        val = float(val_str) if '.' in val_str else int(val_str)
        chinese_val = float_to_chinese(val) if isinstance(val, float) else num_to_chinese(val)
        return "百分之" + chinese_val
    text = re.sub(r'(?<!\d)(\d+(?:\.\d+)?)%', replace_percent, text)
    
    # 2. Convert years: 4 digits starting with 19 or 20 (e.g., 2026 -> 二零二六年)
    def replace_year(match):
        year_str = match.group(1)
        year_map = {'0':'零', '1':'一', '2':'二', '3':'三', '4':'四', '5':'五', '6':'六', '7':'七', '8':'八', '9':'九'}
        chinese_year = "".join(year_map[d] for d in year_str)
        return chinese_year + "年"
    text = re.sub(r'(?<!\d)((?:19|20)\d{2})年?(?!\d)', replace_year, text)
    
    # 3. Convert decimals (e.g., 3.5 -> 三点五)
    def replace_decimal(match):
        whole = int(match.group(1))
        dec = match.group(2)
        digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        dec_chinese = "".join(digits[int(d)] for d in dec)
        return num_to_chinese(whole) + "点" + dec_chinese
    text = re.sub(r'(?<!\d)(\d+)\.(\d+)(?!\d)', replace_decimal, text)
    
    # 4. Convert general numbers
    def replace_number(match):
        val = int(match.group(0))
        return num_to_chinese(val)
    text = re.sub(r'(?<!\d)\d+(?!\d)', replace_number, text)
    
    # 5. Clean up edge symbols/unsupported punctuation while keeping code-switching and pauses
    # Strips mathematical or strange symbols like @, #, $, *, ^, &, etc.
    text = re.sub(r'[@#$*^&_+=\\/|~`<>\[\]\{\}]', '', text)
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# =====================================================================
# 2. Acoustic-Aware NLP Chunker
# =====================================================================

def split_into_chunks(text: str, max_chars: int = 50) -> list:
    """
    Slices the input text at major/secondary Chinese punctuation boundaries.
    Ensures that no individual slice exceeds max_chars.
    """
    # Pattern to capture sentences/clauses alongside their trailing punctuation
    pattern = r'([^。！？；，、.!?;,]+[。！？；，、.!?;,]*|[。！？；，、.!?;,]+)'
    segments = re.findall(pattern, text)
    
    chunks = []
    current_chunk = ""
    
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        
        # If the segment itself is longer than max_chars, split it with jieba
        if len(seg) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # Sub-split long text using word boundaries
            words = jieba.lcut(seg)
            sub_chunk = ""
            for word in words:
                if len(sub_chunk) + len(word) <= max_chars:
                    sub_chunk += word
                else:
                    if sub_chunk:
                        chunks.append(sub_chunk)
                    # If a single word is still longer than max_chars, force character split
                    if len(word) > max_chars:
                        for j in range(0, len(word), max_chars):
                            chunks.append(word[j:j+max_chars])
                        sub_chunk = ""
                    else:
                        sub_chunk = word
            if sub_chunk:
                chunks.append(sub_chunk)
        else:
            # Accumulate normal segments
            if len(current_chunk) + len(seg) <= max_chars:
                current_chunk += seg
            else:
                chunks.append(current_chunk)
                current_chunk = seg
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

# =====================================================================
# 3. Audio Stitching & Conversion Helpers
# =====================================================================

def numpy_to_audiosegment(wav_array: np.ndarray, sample_rate: int) -> AudioSegment:
    """Converts a floating point audio array [-1.0, 1.0] to a mono 16-bit PCM AudioSegment."""
    wav_array = np.clip(wav_array, -1.0, 1.0)
    int_array = (wav_array * 32767).astype(np.int16)
    raw_data = int_array.tobytes()
    return AudioSegment(
        data=raw_data,
        sample_width=2,  # 16-bit (2 bytes)
        frame_rate=sample_rate,
        channels=1  # Mono
    )

# =====================================================================
# 4. Main Storyteller Pipeline
# =====================================================================

def main():
    # 1. Determine configuration file path
    default_config_path = "config.json"
    custom_config_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            custom_config_path = sys.argv[i + 1]
            break
            
    config_file = custom_config_path if custom_config_path else default_config_path
    config_data = {}
    
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            print(f"Loaded config from JSON: {config_file}")
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")
            
    parser = argparse.ArgumentParser(description="F5-TTS Chinese Long-Form Storyteller (Low VRAM optimized)")
    parser.add_argument("--config", type=str, default="config.json", help="Path to configuration JSON file")
    
    # Priority: Command line arguments override JSON configuration values, which override defaults.
    parser.add_argument("--text", type=str, default=config_data.get("text", ""), help="Chinese text block to synthesize or path to a .txt file")
    parser.add_argument("--text_file", type=str, default=config_data.get("text_file", ""), help="Text file containing Chinese block to synthesize")
    parser.add_argument("--ref_audio", type=str, default=config_data.get("ref_audio", "voice.mp3"), help="Path to reference audio file")
    parser.add_argument("--ref_text", type=str, default=config_data.get("ref_text", ""), help="Transcription of the reference audio")
    parser.add_argument("--output", type=str, default=config_data.get("output", "story_teller_output.wav"), help="Path to save stitched output audio")
    parser.add_argument("--model", type=str, default=config_data.get("model", "F5TTS_v1_Base"), help="Model config name")
    parser.add_argument("--ckpt_file", type=str, default=config_data.get("ckpt_file", ""), help="Path to custom model checkpoint")
    parser.add_argument("--vocab_file", type=str, default=config_data.get("vocab_file", ""), help="Path to custom vocab file")
    parser.add_argument("--nfe", type=int, default=config_data.get("nfe", 64), help="Number of Function Evaluations (NFE) to eliminate metallic artifacts")
    parser.add_argument("--sway_coef", type=float, default=config_data.get("sway_coef", -1.0), help="Sway sampling coefficient to force Sway Sampling")
    parser.add_argument("--cfg_strength", type=float, default=config_data.get("cfg_strength", 2.0), help="Classifier-Free Guidance strength")
    parser.add_argument("--speed", type=float, default=config_data.get("speed", 1.0), help="Speech generation speed factor")
    
    args = parser.parse_args()
    
    # Accept .txt file passed in the --text parameter directly
    if args.text and args.text.endswith(".txt") and os.path.exists(args.text):
        args.text_file = args.text
        
    # Read text from file if provided
    if args.text_file:
        if os.path.exists(args.text_file):
            with open(args.text_file, "r", encoding="utf-8") as f:
                args.text = f.read()
        else:
            print(f"Error: Text file not found at {args.text_file}")
            sys.exit(1)
            
    if not args.text.strip():
        print("Error: Please provide text to synthesize via --text or --text_file.")
        sys.exit(1)
        
    if not os.path.exists(args.ref_audio):
        print(f"Error: Reference audio file not found at {args.ref_audio}")
        print("Please place a valid reference audio file or specify its path using --ref_audio.")
        sys.exit(1)
        
    print("\n--- 1. Text Normalization ---")
    print(f"Original Text: {args.text[:100]}...")
    normalized_text = normalize_text(args.text)
    print(f"Normalized Text: {normalized_text[:120]}...")
    
    print("\n--- 2. Acoustic NLP Chunking ---")
    chunks = split_into_chunks(normalized_text, max_chars=50)
    print(f"Split into {len(chunks)} VRAM-safe chunks (max 50 chars each):")
    for idx, chunk in enumerate(chunks):
        print(f"  Chunk {idx+1}: {chunk}")
        
    print("\n--- 3. Loading F5-TTS Models ---")
    # This automatically downloads HF weights to cache if args.ckpt_file is empty
    f5tts = F5TTS(model=args.model, ckpt_file=args.ckpt_file, vocab_file=args.vocab_file)
    model_obj = f5tts.ema_model
    vocoder = f5tts.vocoder
    device = f5tts.device
    mel_type = f5tts.mel_spec_type
    
    print(f"Models loaded successfully. Target Device: {device}")
    
    print("\n--- 4. Preprocessing Reference Audio ---")
    try:
        orig_audio = AudioSegment.from_file(args.ref_audio)
        orig_dur_sec = len(orig_audio) / 1000.0
        if orig_dur_sec > 12.0:
            print("\n" + "="*80)
            print("WARNING: Your reference audio file is too long ({:.2f}s, maximum allowed is 12.0s).".format(orig_dur_sec))
            print("F5-TTS will clip it to 12s, which will cause a MISMATCH with your '--ref_text'.")
            print("Please trim your audio file to be exactly 7-10s long, matching the '--ref_text' exactly.")
            print("="*80 + "\n")
    except Exception as e:
        pass

    ref_audio_file, ref_text_clean = preprocess_ref_audio_text(args.ref_audio, args.ref_text)
    print(f"Reference Audio Path: {ref_audio_file}")
    print(f"Reference Text: {ref_text_clean}")
    
    # Load and clean reference audio
    ref_audio_tensor, ref_sr = torchaudio.load(ref_audio_file)
    if ref_audio_tensor.shape[0] > 1:
        ref_audio_tensor = torch.mean(ref_audio_tensor, dim=0, keepdim=True)
        
    rms = torch.sqrt(torch.mean(torch.square(ref_audio_tensor)))
    if rms < target_rms:
        ref_audio_tensor = ref_audio_tensor * target_rms / rms
    if ref_sr != target_sample_rate:
        resampler = torchaudio.transforms.Resample(ref_sr, target_sample_rate)
        ref_audio_tensor = resampler(ref_audio_tensor)
    ref_audio_tensor = ref_audio_tensor.to(device)
    
    # Select best precision for model inference (bfloat16 is supported on RTX 3050 Ti)
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        autocast_dtype = torch.bfloat16
        precision_str = "bfloat16"
    else:
        autocast_dtype = torch.float16
        precision_str = "float16"
    
    print("\n--- 5. Low-VRAM Inference Loop ---")
    print(f"Inference precision: {precision_str}")
    generated_waves = []
    
    for idx, chunk in enumerate(chunks):
        print(f"Synthesizing chunk {idx+1}/{len(chunks)}: '{chunk}'")
        
        # Free GPU cache before inference step
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        text_list = [ref_text_clean + chunk]
        final_text_list = convert_char_to_pinyin(text_list)
        
        ref_audio_len = ref_audio_tensor.shape[-1] // hop_length
        
        # Dynamic duration scaling
        local_speed = args.speed
        if len(chunk.encode("utf-8")) < 10:
            local_speed = 0.3  # Slow down very short clips to prevent cutoff
            
        ref_text_len = len(ref_text_clean.encode("utf-8"))
        gen_text_len = len(chunk.encode("utf-8"))
        duration = ref_audio_len + int(ref_audio_len / ref_text_len * gen_text_len / local_speed)
        
        # Best-precision Autocast inference for low VRAM
        with torch.inference_mode():
            with torch.autocast(device_type="cuda" if "cuda" in str(device) else "cpu", dtype=autocast_dtype):
                generated, _ = model_obj.sample(
                    cond=ref_audio_tensor,
                    text=final_text_list,
                    duration=duration,
                    steps=args.nfe,
                    cfg_strength=args.cfg_strength,
                    sway_sampling_coef=args.sway_coef,
                )
                del _
                
                # Perform decoding in Float32 to avoid numerical overflow / instability in Vocoder
                generated = generated.to(torch.float32)
                generated = generated[:, ref_audio_len:, :]
                generated = generated.permute(0, 2, 1)
                
                if mel_type == "vocos":
                    generated_wave = vocoder.decode(generated)
                elif mel_type == "bigvgan":
                    generated_wave = vocoder(generated)
                    
                if rms < target_rms:
                    generated_wave = generated_wave * rms / target_rms
                    
                generated_wave = generated_wave.squeeze().cpu().numpy()
                generated_waves.append(generated_wave)
                
        # Free GPU cache immediately after each chunk
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    # Stitch generated waves with 250ms natural breathing pauses
    if not generated_waves:
        print("Error: No audio waves were generated.")
        sys.exit(1)
        
    print("\n--- 6. Stitching Audio segments with 250ms Pauses ---")
    pause = AudioSegment.silent(duration=250, frame_rate=target_sample_rate)
    
    combined_audio = numpy_to_audiosegment(generated_waves[0], target_sample_rate)
    for wave in generated_waves[1:]:
        combined_audio += pause + numpy_to_audiosegment(wave, target_sample_rate)
        
    # Export stitched file
    combined_audio.export(args.output, format="wav")
    print(f"\nSuccess! Storyteller audio saved to: {args.output}")


if __name__ == "__main__":
    main()
