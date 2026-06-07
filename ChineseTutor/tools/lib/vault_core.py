# -*- coding: utf-8 -*-
import os
import sys
import yaml
from datetime import datetime
from .nlp_helper import get_pinyin_slug

# Configuración Beta Fase 3
ENABLE_PHASE_3 = True

# Definiciones de claves según contrato v2
AGENT_KEYS = [
    'word', 'pinyin', 'pinyin_toned', 'char_count', 'category',
    'word_type', 'word_type_alt', 'hsk', 'tocfl', 'frequency',
    'variant', 'stroke_count', 'radical',
    'audio_word', 'audio_word_slow', 'audio_word_male', 'audio_word_female',
    'image_mnemonic', 'image_calligraphy', 'image_etymology',
    'created', 'created_by', 'source_session', 'source_lesson', 'version'
]

USER_SOVEREIGN_KEYS = [
    'srs_status', 'srs_level', 'srs_interval', 'srs_ease',
    'srs_due', 'srs_last_review', 'srs_reviews_count',
    'srs_lapses', 'user_mnemonic', 'user_difficulty', 'user_notes'
]


def resolve_folder(vault_path, char_count, category):
    """Resuelve la ruta física del vocabulario según la longitud o categoría."""
    if category == "chengyu":
        return os.path.join(vault_path, "01_Vocab", "4_Chengyu")
    
    mapping = {1: "1_Monosilabos", 2: "2_Bisilabos"}
    folder_name = mapping.get(char_count, "3_Polisilabos")
    return os.path.join(vault_path, "01_Vocab", folder_name)


def resolve_audio_folder(vault_path, char_count, category):
    """Resuelve la ruta física del audio de la palabra."""
    if category == "chengyu":
        return os.path.join(vault_path, "99_Assets", "Audios", "Palabras", "4_Chengyu")
    
    mapping = {1: "1_Monosilabos", 2: "2_Bisilabos"}
    folder_name = mapping.get(char_count, "3_Polisilabos")
    return os.path.join(vault_path, "99_Assets", "Audios", "Palabras", folder_name)


def parse_frontmatter_and_body(filepath):
    """Separa la cabecera YAML del cuerpo Markdown en un archivo."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                body = parts[2]
                return fm, body
            except Exception as e:
                import time
                backup_path = f"{filepath}.backup.{int(time.time())}"
                print(f"⚠ Frontmatter corrupto en {filepath}. Guardando backup en {backup_path}", file=sys.stderr)
                with open(backup_path, 'w', encoding='utf-8') as bf:
                    bf.write(content)
                return {}, content
    return {}, content


def write_file(filepath, fm, body):
    """Escribe frontmatter YAML y cuerpo a un archivo."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("---\n")
        yaml.safe_dump(fm, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        f.write("---\n")
        f.write(body)


def get_next_sentence_number(vault_path, slug):
    """Calcula el siguiente número secuencial para una oración satélite."""
    sent_dir = os.path.join(vault_path, "05_Sentences")
    os.makedirs(sent_dir, exist_ok=True)
    
    nn = 1
    while True:
        sent_path = os.path.join(sent_dir, f"sent_{slug}_{nn:02d}.md")
        if not os.path.exists(sent_path):
            return nn
        nn += 1


def generate_default_body(word, pinyin_toned, meaning, notes, audio_name, audio_slow_name):
    """Genera la plantilla Markdown por defecto para el cuerpo de una nueva ficha."""
    body = f"\n# {word} ({pinyin_toned})\n\n"
    body += f"**Audio:** ![[{audio_name}]]"
    if audio_slow_name:
        body += f" | *Lento:* ![[{audio_slow_name}]]"
    body += "\n\n### Definiciones\n"
    body += f"- {meaning}\n\n"
    body += "### Colocaciones\n"
    if notes and notes != "-":
        body += f"- {notes}\n\n"
    else:
        body += "- (Añadir colocaciones comunes)\n\n"
    body += "### Oraciones de ejemplo\n"
    return body


def append_link_to_body(body, sentence_file_title, sentence_text):
    """Agrega un Wikilink de oración satélite al cuerpo del archivo sin duplicidades."""
    link_line = f"- [[{sentence_file_title}|{sentence_text}]]"
    
    if sentence_file_title in body:
        return body
        
    if "### Oraciones de ejemplo" in body:
        parts = body.split("### Oraciones de ejemplo")
        header = "### Oraciones de ejemplo\n"
        if not parts[1].strip():
            parts[1] = "\n" + link_line + "\n"
        else:
            parts[1] = "\n" + link_line + parts[1]
        return parts[0] + header + parts[1]
    else:
        return body + f"\n### Oraciones de ejemplo\n{link_line}\n"


def make_dummy_audio(filepath):
    """Crea un archivo de audio dummy."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, 'wb') as f:
            f.write(b'\xFF\xF3\x44\xC4\x00\x00\x00\x03\x48\x00\x00\x00\x00\x4C\x41\x4D\x45')


def write_sentence_note(vault_path, slug, nn, sentence, pinyin, translation, target_word, hsk_level, register, actor):
    """Escribe la nota satélite individual para la oración."""
    filename = f"sent_{slug}_{nn:02d}.md"
    filepath = os.path.join(vault_path, "05_Sentences", filename)
    
    audio_rel = f"99_Assets/Audios/Oraciones/sent_{slug}_{nn:02d}.mp3"
    audio_abs = os.path.join(vault_path, audio_rel)
    make_dummy_audio(audio_abs)
    
    fm = {
        'sentence': sentence,
        'pinyin': pinyin,
        'translation': translation,
        'target_word': target_word,
        'audio': audio_rel,
        'context': "Ejemplo en tutoría",
        'hsk_level': hsk_level,
        'register': register,
        'tags': ['oracion', f"hsk{hsk_level}" if hsk_level else 'general'],
        'created': datetime.now().strftime("%Y-%m-%d"),
        'created_by': actor
    }
    
    body = f"\n![[sent_{slug}_{nn:02d}.mp3]]\n"
    write_file(filepath, fm, body)
    return filename[:-3]


def write_or_merge_ficha(vault_path, word_data, actor="hermes"):
    """Realiza la creación o fusión idempotente de una ficha de vocabulario."""
    word = word_data['word']
    char_count = int(word_data.get('char_count', len(word)))
    category = word_data.get('category', 'palabra')
    
    folder = resolve_folder(vault_path, char_count, category)
    filepath = os.path.join(folder, f"{word}.md")
    
    slug = get_pinyin_slug(word_data.get('pinyin', word))
    
    audio_dir_rel = os.path.relpath(resolve_audio_folder(vault_path, char_count, category), vault_path)
    audio_word_rel = os.path.join(audio_dir_rel, f"word_{slug}.mp3")
    audio_slow_rel = os.path.join(audio_dir_rel, f"word_{slug}_slow.mp3")
    
    make_dummy_audio(os.path.join(vault_path, audio_word_rel))
    make_dummy_audio(os.path.join(vault_path, audio_slow_rel))
    
    incoming_data = {
        'word': word,
        'pinyin': slug,
        'pinyin_toned': word_data.get('pinyin_toned', word_data.get('pinyin', '')),
        'char_count': char_count,
        'category': category,
        'word_type': word_data.get('word_type', ['verbo'] if isinstance(word_data.get('word_type'), list) else [word_data.get('word_type', 'verbo')]),
        'word_type_alt': word_data.get('word_type_alt', []),
        'hsk': word_data.get('hsk', None),
        'tocfl': word_data.get('tocfl', None),
        'frequency': word_data.get('frequency', 'media'),
        'variant': word_data.get('variant', None),
        'stroke_count': word_data.get('stroke_count', 0),
        'radical': word_data.get('radical', ''),
        'audio_word': audio_word_rel,
        'audio_word_slow': audio_slow_rel,
        'audio_word_male': None,
        'audio_word_female': None,
        'image_mnemonic': None,
        'image_calligraphy': None,
        'image_etymology': None,
        'created_by': actor,
        'version': 1,
        'tags': word_data.get('tags', [f"hsk{word_data.get('hsk')}" if word_data.get('hsk') else 'general'])
    }
    
    existing_fm = {}
    body = ""
    
    if os.path.exists(filepath):
        existing_fm, body = parse_frontmatter_and_body(filepath)
        merged_fm = {}
        
        for key in AGENT_KEYS:
            if key in incoming_data:
                merged_fm[key] = incoming_data[key]
            elif key in existing_fm:
                merged_fm[key] = existing_fm[key]
                
        for key in USER_SOVEREIGN_KEYS:
            if key in existing_fm:
                merged_fm[key] = existing_fm[key]
            else:
                merged_fm[key] = None
                
        existing_tags = set(existing_fm.get('tags', []))
        new_tags = set(incoming_data.get('tags', []))
        merged_fm['tags'] = sorted(list(existing_tags | new_tags))
        
        merged_fm['created'] = existing_fm.get('created', datetime.now().strftime("%Y-%m-%d"))
        merged_fm['created_by'] = existing_fm.get('created_by', actor)
        merged_fm['modified'] = datetime.now().strftime("%Y-%m-%d")
        merged_fm['modified_by'] = actor
    else:
        merged_fm = incoming_data.copy()
        merged_fm['created'] = datetime.now().strftime("%Y-%m-%d")
        merged_fm['modified'] = merged_fm['created']
        merged_fm['modified_by'] = actor
        
        defaults = {
            'srs_status': 'nuevo', 'srs_level': 0, 'srs_interval': 0,
            'srs_ease': 2.5, 'srs_due': None, 'srs_last_review': None,
            'srs_reviews_count': 0, 'srs_lapses': 0,
            'user_mnemonic': None, 'user_difficulty': None, 'user_notes': None
        }
        merged_fm.update(defaults)
        
        body = generate_default_body(
            word=word,
            pinyin_toned=merged_fm['pinyin_toned'],
            meaning=word_data.get('meaning', ''),
            notes=word_data.get('notes', '-'),
            audio_name=f"word_{slug}.mp3",
            audio_slow_name=f"word_{slug}_slow.mp3"
        )
        
    if 'sentences' in word_data:
        for sent_info in word_data['sentences']:
            sentence = sent_info.get('sentence')
            pinyin_s = sent_info.get('pinyin')
            trans = sent_info.get('translation')
            hsk_s = sent_info.get('hsk_level', merged_fm.get('hsk'))
            reg = sent_info.get('register', 'neutral')
            
            nn = get_next_sentence_number(vault_path, slug)
            title_link = write_sentence_note(
                vault_path=vault_path,
                slug=slug,
                nn=nn,
                sentence=sentence,
                pinyin=pinyin_s,
                translation=trans,
                target_word=word,
                hsk_level=hsk_s,
                register=reg,
                actor=actor
            )
            body = append_link_to_body(body, title_link, sentence)
            
    write_file(filepath, merged_fm, body)
    print(f"✓ Ficha de vocabulario procesada con éxito: {filepath}")
    return filepath


def log_error_v2(vault_path, error_desc, correction, explanation, target_word, error_type="general"):
    """Registra un error como nota satélite en 02_Errors/."""
    err_dir = os.path.join(vault_path, "02_Errors")
    os.makedirs(err_dir, exist_ok=True)
    
    slug = get_pinyin_slug(target_word)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"err_{slug}_{date_str}.md"
    filepath = os.path.join(err_dir, filename)
    
    idx = 1
    while os.path.exists(filepath):
        filename = f"err_{slug}_{date_str}_{idx:02d}.md"
        filepath = os.path.join(err_dir, filename)
        idx += 1
        
    fm = {
        'date': datetime.now().strftime("%Y-%m-%d"),
        'target_word': target_word,
        'error_type': error_type,
        'mistake': error_desc,
        'correction': correction,
        'explanation': explanation,
        'created_by': "hermes"
    }
    
    body = f"\n# Error en: {target_word}\n\n"
    body += f"**Intento:** {error_desc}\n"
    body += f"**Corrección:** {correction}\n\n"
    body += f"### Explicación:\n{explanation}\n"
    
    write_file(filepath, fm, body)
    print(f"✓ Error registrado con éxito en nota satélite: {filepath}")
    
    if ENABLE_PHASE_3:
        write_error_pattern(vault_path, target_word)
    return filepath


def add_grammar_v2(vault_path, title, content):
    """Añade o adjunta notas de gramática en 03_Grammar/grammar.md."""
    grammar_file = os.path.join(vault_path, "03_Grammar", "grammar.md")
    
    if not os.path.exists(grammar_file):
        os.makedirs(os.path.dirname(grammar_file), exist_ok=True)
        with open(grammar_file, 'w', encoding='utf-8') as f:
            f.write("# Notas de Gramática y Estructuras\n\nA continuación se registran los apuntes gramaticales:\n")
            
    content = content.replace('\\n', '\n')
    section = f"\n---\n\n## {title}\n{content}\n"
    
    with open(grammar_file, 'a', encoding='utf-8') as f:
        f.write(section)
    print(f"✓ Nota gramatical añadida con éxito a {grammar_file}: {title}")
    return grammar_file


# === CAPAS ESPECIALIZADAS FASE 3 ===

def generate_comparison_body(template_body, entities, details):
    body = template_body
    pA, pB = entities[0], entities[1]
    
    if details:
        lines = body.split("\n")
        new_lines = []
        for line in lines:
            for dim, words_detail in details.items():
                if line.strip().startswith("|") and dim in line:
                    cells = [c.strip() for c in line.split("|")]
                    if len(cells) >= 4:
                        cell_a = words_detail.get(pA, "")
                        cell_b = words_detail.get(pB, "")
                        if not cells[2]:
                            cells[2] = cell_a
                        if not cells[3]:
                            cells[3] = cell_b
                        line = " | ".join(cells).strip()
                        if not line.startswith("|"):
                            line = "|" + line
                        if not line.endswith("|"):
                            line = line + "|"
                        break
            new_lines.append(line)
        body = "\n".join(new_lines)

        lines = body.split("\n")
        new_lines = []
        current_dim = None
        
        header_to_dim = {
            "### 1. 内涵": "内涵",
            "### 2. 用法": "用法",
            "### 3. 感情色彩": "感情色彩",
            "### 1. Estructura Sintáctica": "estructura",
            "### 2. Casos de Uso": "restricciones"
        }
        
        for line in lines:
            for header, dim in header_to_dim.items():
                if line.strip().startswith(header):
                    current_dim = dim
                    break
                    
            if current_dim and current_dim in details:
                stripped = line.strip()
                if "PalabraA" in stripped and (stripped.endswith("PalabraA**:") or stripped.endswith("PalabraA**:")):
                    val = details[current_dim].get(pA, "")
                    line = line.replace("PalabraA", pA) + f" {val}"
                elif "PalabraB" in stripped and (stripped.endswith("PalabraB**:") or stripped.endswith("PalabraB**:")):
                    val = details[current_dim].get(pB, "")
                    line = line.replace("PalabraB", pB) + f" {val}"
                elif "EstructuraA" in stripped and (stripped.endswith("EstructuraA**:") or stripped.endswith("EstructuraA**:")):
                    val = details[current_dim].get(pA, "")
                    line = line.replace("EstructuraA", pA) + f" {val}"
                elif "EstructuraB" in stripped and (stripped.endswith("EstructuraB**:") or stripped.endswith("EstructuraB**:")):
                    val = details[current_dim].get(pB, "")
                    line = line.replace("EstructuraB", pB) + f" {val}"
            new_lines.append(line)
        body = "\n".join(new_lines)

    body = body.replace("PalabraA", pA).replace("PalabraB", pB)
    body = body.replace("EstructuraA", pA).replace("EstructuraB", pB)
    return body


def write_or_merge_comparison(vault_path, entities, comparison_data, actor="hermes"):
    sorted_entities = sorted([str(e).strip() for e in entities if str(e).strip()])
    if len(sorted_entities) < 2:
        raise ValueError("Se requieren al menos 2 entidades para una comparación.")
        
    filename = f"{sorted_entities[0]}_vs_{sorted_entities[1]}.md"
    filepath = os.path.join(vault_path, "07_Comparisons", filename)
    
    comp_type = comparison_data.get('comparison_type', 'semantico_pragmatico')
    incoming_dims = comparison_data.get('dimensions', ["内涵", "用法", "搭配", "感情色彩"] if comp_type == 'semantico_pragmatico' else ["estructura", "particulas", "orden_sintactico"])
    hsk_range = comparison_data.get('hsk_range', [])
    source_session = comparison_data.get('source_session', '')
    source_question_pattern = comparison_data.get('source_question_pattern', '')
    incoming_tags = comparison_data.get('tags', ['comparacion', 'semantico'] if comp_type == 'semantico_pragmatico' else ['comparacion', 'gramatica'])
    details = comparison_data.get('details', {})
    
    existing_fm = {}
    existing_body = ""
    
    if os.path.exists(filepath):
        existing_fm, existing_body = parse_frontmatter_and_body(filepath)
        merged_fm = existing_fm.copy()
        
        existing_dims = existing_fm.get('dimensions', [])
        merged_fm['dimensions'] = sorted(list(set(existing_dims) | set(incoming_dims)))
        
        existing_tags = existing_fm.get('tags', [])
        merged_fm['tags'] = sorted(list(set(existing_tags) | set(incoming_tags)))
        
        existing_hsk = existing_fm.get('hsk_range', [])
        merged_fm['hsk_range'] = sorted(list(set(existing_hsk) | set(hsk_range)))
        
        merged_fm['modified'] = datetime.now().strftime("%Y-%m-%d")
        merged_fm['modified_by'] = actor
        if source_session:
            merged_fm['source_session'] = source_session
        if source_question_pattern:
            merged_fm['source_question_pattern'] = source_question_pattern
        body = existing_body
    else:
        template_name = "comparison_grammatical.md" if comp_type == "gramatical" else "comparison_semantic.md"
        template_path = os.path.join(vault_path, "11_Templates", template_name)
        
        template_fm = {}
        template_body = ""
        if os.path.exists(template_path):
            template_fm, template_body = parse_frontmatter_and_body(template_path)
            
        merged_fm = template_fm.copy()
        merged_fm['comparison_type'] = comp_type
        merged_fm['entities'] = sorted_entities
        merged_fm['dimensions'] = incoming_dims
        merged_fm['hsk_range'] = hsk_range
        merged_fm['created'] = datetime.now().strftime("%Y-%m-%d")
        merged_fm['created_by'] = actor
        merged_fm['modified'] = merged_fm['created']
        merged_fm['modified_by'] = actor
        merged_fm['source_session'] = source_session
        merged_fm['source_question_pattern'] = source_question_pattern
        merged_fm['tags'] = incoming_tags
        
        body = generate_comparison_body(template_body, sorted_entities, details)
        
    write_file(filepath, merged_fm, body)
    print(f"✓ Ficha de comparación procesada con éxito: {filepath}")
    return filepath


def write_error_pattern(vault_path, target_word, error_analysis=None, actor="hermes"):
    """Crawlea los errores y consolida patrones de diagnóstico en 10_ErrorPatterns/."""
    err_dir = os.path.join(vault_path, "02_Errors")
    if not os.path.exists(err_dir):
        return None
        
    matching_errors = []
    for filename in os.listdir(err_dir):
        if filename.startswith("err_") and filename.endswith(".md"):
            filepath = os.path.join(err_dir, filename)
            try:
                fm, body = parse_frontmatter_and_body(filepath)
                if fm.get('target_word') == target_word:
                    matching_errors.append((fm, body))
            except Exception as e:
                print(f"Error parseando {filepath}: {e}", file=sys.stderr)
                
    if len(matching_errors) < 3:
        print(f"Frecuencia de errores para '{target_word}': {len(matching_errors)}. Aún no se genera patrón (mínimo 3).")
        return None
        
    print(f"¡Patrón de error detectado para '{target_word}' (frecuencia: {len(matching_errors)}). Generando diagnóstico...")
    
    matching_errors.sort(key=lambda x: x[0].get('date', ''))
    dates = [x[0].get('date') for x in matching_errors if x[0].get('date')]
    first_seen = min(dates) if dates else datetime.now().strftime("%Y-%m-%d")
    last_seen = max(dates) if dates else datetime.now().strftime("%Y-%m-%d")
    
    if "vs" in target_word:
        entities = sorted([w.strip() for w in target_word.split("vs")])
    elif "," in target_word:
        entities = sorted([w.strip() for w in target_word.split(",")])
    else:
        entities = [target_word.strip()]
        
    entities_str = "_vs_".join(entities)
    pattern_filename = f"err_pattern_{entities_str}.md"
    pattern_filepath = os.path.join(vault_path, "10_ErrorPatterns", pattern_filename)
    
    existing_fm = {}
    existing_body = ""
    if os.path.exists(pattern_filepath):
        existing_fm, existing_body = parse_frontmatter_and_body(pattern_filepath)
        
    template_path = os.path.join(vault_path, "11_Templates", "error_diagnosis.md")
    template_fm = {}
    template_body = ""
    if os.path.exists(template_path):
        template_fm, template_body = parse_frontmatter_and_body(template_path)
        
    merged_fm = template_fm.copy()
    if existing_fm:
        merged_fm.update(existing_fm)
        
    merged_fm['entities'] = entities
    merged_fm['frequency'] = len(matching_errors)
    merged_fm['first_seen'] = first_seen
    merged_fm['last_seen'] = last_seen
    merged_fm['status'] = merged_fm.get('status', 'activo')
    merged_fm['created_by'] = merged_fm.get('created_by', actor)
    
    if error_analysis and 'underlying_cause' in error_analysis:
        merged_fm['underlying_cause'] = error_analysis['underlying_cause']
            
    error_list_md = ""
    for i, (fm, body_err) in enumerate(matching_errors, 1):
        mistake = fm.get('mistake', '')
        correction = fm.get('correction', '')
        explanation = fm.get('explanation', '')
        error_list_md += f"*   **Caso {i}:**\n"
        error_list_md += f"    *   *Error:* {mistake}\n"
        error_list_md += f"    *   *Corrección:* {correction}\n"
        error_list_md += f"    *   *Detalle:* {explanation}\n"
        
    if template_body:
        body = template_body
        if len(entities) > 1:
            body = body.replace("PalabraA y PalabraB", f"{entities[0]} y {entities[1]}")
            body = body.replace("[[PalabraA]] vs [[PalabraB]]", f"[[{entities[0]}]] vs [[{entities[1]}]]")
        else:
            body = body.replace("Confusión entre PalabraA y PalabraB", f"Error recurrente en {entities[0]}")
            body = body.replace("[[PalabraA]] vs [[PalabraB]]", f"[[{entities[0]}]]")
            
        body = body.replace("{underlying_cause}", merged_fm.get('underlying_cause', '(Por analizar)'))
        body = body.replace("{status}", merged_fm.get('status', 'activo'))
        body = body.replace("{frequency}", str(merged_fm.get('frequency', len(matching_errors))))
        
        if "## 2. Ejemplos de Errores Registrados" in body:
            parts = body.split("## 2. Ejemplos de Errores Registrados")
            subparts = parts[1].split("## 3. Plan de Tratamiento Lingüístico")
            middle = "\n" + error_list_md + "\n"
            parts[1] = middle + "## 3. Plan de Tratamiento Lingüístico" + subparts[1]
            body = parts[0] + "## 2. Ejemplos de Errores Registrados" + parts[1]
    else:
        body = f"\n# Diagnóstico de Error: {target_word}\n\n"
        body += f"## Resumen del Diagnóstico\n\n"
        body += f"*   **Palabras Implicadas:** {', '.join(entities)}\n"
        body += f"*   **Causa Raíz Lingüística:** {merged_fm.get('underlying_cause', '')}\n"
        body += f"*   **Frecuencia Registrada:** {len(matching_errors)} veces\n\n"
        body += f"## 2. Ejemplos de Errores Registrados\n\n{error_list_md}\n"
        
    write_file(pattern_filepath, merged_fm, body)
    print(f"✓ Patrón de error escrito con éxito en: {pattern_filepath}")
    return pattern_filepath
