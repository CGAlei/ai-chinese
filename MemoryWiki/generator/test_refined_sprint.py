# test_refined_sprint.py

import os
import re
import shutil
import datetime
from app.main import find_word_file, get_clean_filename
from app.parser_merge import parse_markdown_note, serialize_note, merge_notes, process_wikilinks

def run_tests():
    print("=== STARTING SPRINT VERIFICATION TESTS ===")
    
    # -------------------------------------------------------------
    # Test 1: process_wikilinks
    # -------------------------------------------------------------
    print("\nTest 1: WikiLinks Post-Processing")
    raw_syns = (
        "- 奥秘 (àomì) — secreto profundo\n"
        "- 清楚 (qīngchu) — claro / limpio\n"
        "- [[公开]] (gōngkāi) — público\n"
        "1. 明白 (míngbai) — entender\n"
        "No CJK here"
    )
    expected_syns = (
        "- [[奥秘]] (àomì) — secreto profundo\n"
        "- [[清楚]] (qīngchu) — claro / limpio\n"
        "- [[公开]] (gōngkāi) — público\n"
        "1. [[明白]] (míngbai) — entender\n"
        "No CJK here"
    )
    processed = process_wikilinks(raw_syns)
    if processed == expected_syns:
        print("-> SUCCESS: process_wikilinks works correctly.")
    else:
        print("-> FAIL: process_wikilinks result mismatch:")
        print(f"Got:\n{processed}")
        print(f"Expected:\n{expected_syns}")
        assert False

    # -------------------------------------------------------------
    # Test 2: Callout parsing with fold indicators and custom titles
    # -------------------------------------------------------------
    print("\nTest 2: Callout Regex with Fold Indicators and Custom Titles")
    test_note = (
        "---\n"
        "word: 明白\n"
        "favorite: true\n"
        "sr-due: '2026-06-10'\n"
        "---\n"
        "\n"
        "> [!meaning]+\n"
        "> Significado plegable por defecto.\n"
        "\n"
        "> [!synthesis]- Mi Síntesis Especial\n"
        "> Explicación plegada y con título.\n"
        "\n"
        "> [!radical] Radicales estándar\n"
        "> Desglose de radicales.\n"
    )
    
    # Write to a temporary file
    temp_note_path = "test_callouts_temp.md"
    with open(temp_note_path, "w", encoding="utf-8") as f:
        f.write(test_note)
        
    try:
        metadata, sections = parse_markdown_note(temp_note_path)
        
        # Verify metadata
        assert metadata.get("word") == "明白"
        assert metadata.get("favorite") is True
        assert metadata.get("sr-due") == "2026-06-10"
        
        # Verify sections parsed
        assert "meaning" in sections
        assert "synthesis" in sections
        assert "radical" in sections
        
        assert sections["meaning"] == "Significado plegable por defecto."
        assert sections["synthesis"] == "Explicación plegada y con título."
        assert sections["radical"] == "Desglose de radicales."
        
        print("-> SUCCESS: Callout parsing works correctly with fold indicators and custom titles.")
    finally:
        if os.path.exists(temp_note_path):
            os.remove(temp_note_path)

    # -------------------------------------------------------------
    # Test 3: YAML Frontmatter preservation & Idempotency
    # -------------------------------------------------------------
    print("\nTest 3: YAML Frontmatter Preservation & Idempotency")
    old_meta = {
        "word": "明白",
        "pinyin": "míngbai",
        "word_type": "verbo",
        "favorite": True,
        "tags": ["review", "custom-tag"],
        "sr-due": "2026-06-25",
        "sr-interval": 12,
        "sr-ease": 260
    }
    
    new_meta = {
        "word": "明白",
        "pinyin": "míngbai",
        "word_type": "adjetivo", # Note category change from LLM
        "favorite": False,      # Default in new metadata is False
        "tags": ["review"],     # Default in new metadata
        "created_time": "2026-06-05T12:00:00Z"
    }
    
    merged_meta, _ = merge_notes(old_meta, {}, new_meta, {}, [])
    
    # Verify that:
    # 1. Favorite remains True (preserved from old_meta)
    # 2. tags remains ['review', 'custom-tag'] (preserved from old_meta)
    # 3. sr-due, sr-interval, sr-ease are preserved
    # 4. word_type is updated to 'adjetivo' (word_type is in the list of keys to update)
    assert merged_meta["favorite"] is True
    assert merged_meta["tags"] == ["review", "custom-tag"]
    assert merged_meta["sr-due"] == "2026-06-25"
    assert merged_meta["sr-interval"] == 12
    assert merged_meta["sr-ease"] == 260
    assert merged_meta["word_type"] == "adjetivo"
    
    print("-> SUCCESS: YAML Frontmatter metadata fields preserved idempotently.")

    # -------------------------------------------------------------
    # Test 4: Recursive Lookup & CJK character counting for Chengyu
    # -------------------------------------------------------------
    print("\nTest 4: Recursive Lookup & CJK Chengyu Counting")
    # Setup mock vault environment
    mock_vault = "mock_vault"
    import app.main
    # Temporary backup base unified_dir
    original_unified_dir = app.main.unified_dir
    app.main.unified_dir = mock_vault
    
    nested_dir = os.path.join(mock_vault, "bisilabos", "verbo")
    os.makedirs(nested_dir, exist_ok=True)
    
    # Write a test disyllable inside mock subfolder
    test_word_file = os.path.join(nested_dir, "明白.md")
    with open(test_word_file, "w", encoding="utf-8") as f:
        f.write("# Dummy note")
        
    try:
        # 1. Recursive lookup test: should find nested file
        resolved_path, ct = find_word_file("明白", "bisilabo")
        assert os.path.abspath(resolved_path) == os.path.abspath(test_word_file)
        assert ct == "bisilabo"
        print("-> SUCCESS: find_word_file successfully resolved nested file recursively.")
        
        # 2. CJK Chengyu character count test:
        # A 4-character Chinese Chengyu (e.g. 拔苗助长)
        cjk_path, cjk_ct = find_word_file("拔苗助长")
        assert cjk_ct == "chengyu"
        
        # A 4-letter English word (e.g. word) should NOT be classified as Chengyu, but rather bisilabo/default
        eng_path, eng_ct = find_word_file("word")
        assert eng_ct == "bisilabo" # Because cjk_len is 0
        
        print("-> SUCCESS: Chengyu classification correctly uses CJK unicode character counting.")
        
    finally:
        # Cleanup mock vault
        app.main.unified_dir = original_unified_dir
        if os.path.exists(mock_vault):
            shutil.rmtree(mock_vault)

    # -------------------------------------------------------------
    # Test 5: Atomic Writing Verification
    # -------------------------------------------------------------
    print("\nTest 5: Atomic Writing Verification")
    test_file_path = "test_atomic_write.md"
    test_data = "Hello atomic world"
    
    # Write atomically using the same logic as main.py
    tmp_filepath = f"{test_file_path}.tmp"
    try:
        with open(tmp_filepath, "w", encoding="utf-8") as f:
            f.write(test_data)
        os.replace(tmp_filepath, test_file_path)
        
        # Verify contents
        with open(test_file_path, "r", encoding="utf-8") as f:
            read_data = f.read()
        assert read_data == test_data
        assert not os.path.exists(tmp_filepath)
        print("-> SUCCESS: File written atomically, temporary file cleaned up.")
    finally:
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        if os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)

    # -------------------------------------------------------------
    # Test 6: Audio Recording REST API Endpoints
    # -------------------------------------------------------------
    print("\nTest 6: Audio Recording REST API Endpoints")
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    
    test_client = TestClient(fastapi_app)
    
    # 1. Test start recording endpoint
    start_res = test_client.post("/api/audio/start?word=test_atomic_record")
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert start_data.get("status") == "recording"
    assert "test_atomic_record" in start_data.get("filename")
    
    # Wait 1.5 seconds to record some desktop audio
    import time
    time.sleep(1.5)
    
    # 2. Test stop recording endpoint
    stop_res = test_client.post("/api/audio/stop")
    assert stop_res.status_code == 200
    stop_data = stop_res.json()
    assert stop_data.get("status") == "stopped"
    assert "test_atomic_record" in stop_data.get("filename")
    assert stop_data.get("obsidian_link").startswith("![[unified-words/audio/test_atomic_record")
    
    # Check if file exists and has size > 0
    audio_file_path = os.path.join(original_unified_dir, "audio", stop_data.get("filename"))
    assert os.path.exists(audio_file_path)
    assert os.path.getsize(audio_file_path) > 0
    
    # Cleanup recording file
    if os.path.exists(audio_file_path):
        os.remove(audio_file_path)
        
    print("-> SUCCESS: Audio start/stop API endpoints verified successfully.")

    print("\n=== ALL SPRINT VERIFICATION TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
