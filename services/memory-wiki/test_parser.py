# test_parser.py

import os
from app.parser_merge import parse_markdown_note, serialize_note

def run_test():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    note_path = os.path.join(base_dir, "vault", "nemotecnia", "unified-words", "神秘.md")
    
    # Check if file exists relative to parent
    if not os.path.exists(note_path):
        note_path = os.path.join(os.path.dirname(base_dir), "vault", "nemotecnia", "unified-words", "神秘.md")
        
    print(f"Reading note from: {note_path}")
    if not os.path.exists(note_path):
        print("ERROR: Test note not found!")
        return
        
    metadata, sections = parse_markdown_note(note_path)
    
    print("\n--- METADATA ---")
    for k, v in metadata.items():
        print(f"{k}: {v}")
        
    print("\n--- SECTIONS FOUND ---")
    for k in sections.keys():
        print(f"- {k} ({len(sections[k])} bytes)")
        
    # Serialize back and compare lengths
    serialized = serialize_note(metadata, sections)
    print("\n--- SERIALIZATION TEST ---")
    print(f"Original file exists. Serialized content length: {len(serialized)} bytes")
    
    if len(sections) == 0:
        print("FAIL: No sections found! Check the parser regex pattern.")
    else:
        print("SUCCESS: Parser read and serialized note correctly!")

if __name__ == "__main__":
    run_test()
