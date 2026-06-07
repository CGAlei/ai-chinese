# app/parser_merge.py

import os
import re
import frontmatter

def parse_markdown_note(filepath: str) -> tuple[dict, dict[str, str]]:
    """
    Parses a unified markdown vocabulary file.
    Returns (metadata_dict, sections_dict)
    """
    if not os.path.exists(filepath):
        return {}, {}
        
    post = frontmatter.load(filepath)
    metadata = post.metadata
    content = post.content
    
    # Match Obsidian callouts: line starting with `> [!key]` (with optional fold indicator + or - and custom title) followed by lines starting with `>`
    pattern = r'^>\s*\[!([a-zA-Z0-9_\-]+)\][+\-]?[^\n]*\n((?:^>.*\n?)*)'
    matches = re.findall(pattern, content, re.MULTILINE)
    
    sections = {}
    for key, val in matches:
        section_key = key.lower().strip()
        lines = []
        for line in val.splitlines():
            # Strip the leading '>' and optional space
            cleaned_line = re.sub(r'^>\s?', '', line)
            lines.append(cleaned_line)
        sections[section_key] = "\n".join(lines).strip()
        
    return metadata, sections

TEMPLATES_SECTIONS = {
    "bisilabo": [
        "meaning", "synthesis", "radical", "etymology", "mnemonics", 
        "errors", "usage", "collocations", "synonyms", "antonyms", 
        "examples", "notebooklm", "pinyin"
    ],
    "polisilabo": [
        "concept", "morphology", "contextual_logic", "register_and_nuance",
        "spanish_interference", "collocations", "synonyms", "antonyms",
        "examples", "notebooklm", "pinyin"
    ],
    "chengyu": [
        "definition", "classical_origin", "structural_logic", "colloquial_frequency",
        "pragmatic_errors", "collocations", "synonyms", "antonyms",
        "examples", "notebooklm", "pinyin"
    ],
    "comparacion": [
        "shared_core", "semantic_divergence", "syntactic_distinction",
        "collocation_matrix", "interference_warning", "comparative_examples",
        "notebooklm", "pinyin"
    ],
    "estructura": [
        "formula", "logical_connection", "syntactic_constraints",
        "spanish_mismatch", "progressive_examples", "notebooklm", "pinyin"
    ],
    "correccion_alocucion": [
        "veredicto_optimizacion", "interferencia_sintactica", "conectores_muletillas",
        "registro_colocaciones", "aspecto_particulas", "prosodia_ritmo"
    ]
}

def process_wikilinks(text: str) -> str:
    """
    Scans synonyms/antonyms text lines and wraps the leading Chinese word in [[WikiLinks]]
    for Obsidian Graph View integration, if not already wrapped.
    """
    lines = []
    for line in text.splitlines():
        m = re.match(r'^(\s*(?:[-\*]|\d+\.)?\s*)([\u4e00-\u9fff]+)(.*)$', line)
        if m:
            prefix, chinese, suffix = m.group(1), m.group(2), m.group(3)
            # Verify it's not already wrapped in [[ ]]
            if not (prefix.rstrip().endswith("[[") and suffix.lstrip().startswith("]]")):
                lines.append(f"{prefix}[[{chinese}]]{suffix}")
                continue
        lines.append(line)
    return "\n".join(lines)

def serialize_note(metadata: dict, sections: dict[str, str], card_type: str = "bisilabo") -> str:
    """
    Assembles frontmatter metadata and sections into a single markdown string.
    """
    body_parts = []
    
    # Retrieve specific callout sequence for the card type
    order = TEMPLATES_SECTIONS.get(card_type, TEMPLATES_SECTIONS["bisilabo"])
    
    for section_key in order:
        content = sections.get(section_key, "")
        if not content:
            # Check common singular/plural variations
            if section_key == "mnemonics" and "mnemonic" in sections:
                content = sections["mnemonic"]
            elif section_key == "errors" and "error" in sections:
                content = sections["error"]
            elif section_key == "examples" and "example" in sections:
                content = sections["example"]
                
        if content:
            if section_key in ["synonyms", "antonyms"]:
                content = process_wikilinks(content)
            part = f"> [!{section_key}]\n"
            for line in content.splitlines():
                part += f"> {line}\n"
            body_parts.append(part.strip())
            
    body_content = "\n\n".join(body_parts)
    
    # Recreate the post object and dump it
    post = frontmatter.Post(body_content, **metadata)
    return frontmatter.dumps(post)

def merge_notes(old_metadata: dict, old_sections: dict[str, str],
                new_metadata: dict, new_sections: dict[str, str],
                regenerate_sections: list[str]) -> tuple[dict, dict[str, str]]:
    """
    Merges old note content with new generated content.
    Only updates sections specified in `regenerate_sections` or sections that are missing in the old note.
    Preserves other old sections completely (idempotency).
    """
    merged_metadata = {}
    
    # 1. Merge metadata
    # Keep old metadata first, then overwrite with new keys where appropriate
    merged_metadata.update(old_metadata)
    for k, v in new_metadata.items():
        if k not in merged_metadata or k in ["word", "pinyin", "word_type", "hsk_level"]:
            merged_metadata[k] = v
            
    # 2. Merge sections
    merged_sections = {}
    
    # Generate standard_keys dynamically from TEMPLATES_SECTIONS keys
    standard_keys = {k.lower(): k.lower() for tpl in TEMPLATES_SECTIONS.values() for k in tpl}
    # Add manual mappings for singular/plural variations to avoid duplication
    for k, v in [("mnemonic", "mnemonics"), ("error", "errors"), ("example", "examples")]:
        standard_keys[k] = v

    # Normalize existing sections to standard keys
    normalized_old_sections = {}
    for k, v in old_sections.items():
        std_key = standard_keys.get(k.lower(), k.lower())
        normalized_old_sections[std_key] = v
        
    normalized_new_sections = {}
    for k, v in new_sections.items():
        std_key = standard_keys.get(k.lower(), k.lower())
        normalized_new_sections[std_key] = v

    # List of all possible standard sections to merge
    all_keys = set(normalized_old_sections.keys()) | set(normalized_new_sections.keys())
    
    # Standardize the list of sections the user wants to overwrite
    normalized_regen = [standard_keys.get(k.lower(), k.lower()) for k in regenerate_sections]

    for key in all_keys:
        old_val = normalized_old_sections.get(key, "")
        new_val = normalized_new_sections.get(key, "")
        
        # We overwrite with new value if:
        # a) The section is empty or missing in the old note, OR
        # b) The section is explicitly requested for regeneration
        if not old_val or key in normalized_regen:
            merged_sections[key] = new_val if new_val else old_val
        else:
            # Keep the old custom text (idempotent)
            merged_sections[key] = old_val

    return merged_metadata, merged_sections
