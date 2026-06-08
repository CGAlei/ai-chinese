#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import argparse
import re

# Asegurar importación de bibliotecas locales
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib.nlp_helper import segment_chinese, to_simplified, get_pinyin_slug
from lib.vault_core import parse_frontmatter_and_body
import history


def find_vocab_file(vault_path, word):
    """Busca recursivamente una palabra en 01_Vocab/ y devuelve su ruta relativa si existe."""
    vocab_dir = os.path.join(vault_path, "01_Vocab")
    if not os.path.exists(vocab_dir):
        return None
        
    filename = f"{word}.md"
    for root, dirs, files in os.walk(vocab_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if filename in files:
            full_path = os.path.join(root, filename)
            return os.path.relpath(full_path, vault_path)
    return None


def main():
    parser = argparse.ArgumentParser(description="Preprocesador de consultas de lenguaje natural para el Tutor de Chino.")
    parser.add_argument("--message", required=True, help="Mensaje enviado por el usuario")
    parser.add_argument("--path", default="/home/alex/Ai-chinese/data/vaults/chinese-tutor", help="Ruta al baúl de notas")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.path):
        print(json.dumps({"error": f"La ruta especificada '{args.path}' no existe."}, ensure_ascii=False))
        sys.exit(1)
        
    message = args.message
    
    # 1. Segmentación y simplificación local (NLP)
    words = segment_chinese(message)
    simplified_words = [to_simplified(w) for w in words]
    
    # Filtrar solo palabras que contengan caracteres chinos
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]+")
    detected_chinese = []
    seen = set()
    for w in simplified_words:
        if chinese_pattern.match(w) and w not in seen:
            detected_chinese.append(w)
            seen.add(w)
            
    # 2. Análisis de intención (KISS)
    intent = "chat"
    entities = []
    
    # Mapear estado de palabras detectadas en el vault
    for word in detected_chinese:
        path = find_vocab_file(args.path, word)
        entities.append({
            "word": word,
            "exists": path is not None,
            "path": path or ""
        })
        
    comparison_info = None
    pattern_info = None
    
    # Si detecta 2 o más palabras chinas, es muy probable que sea una comparación
    is_comparison_query = any(k in message.lower() for k in ["vs", "diferencia", "entre", "comparar", "diferenciar"]) or len(detected_chinese) >= 2
    
    if is_comparison_query and len(detected_chinese) >= 2:
        intent = "comparison"
        sorted_entities = sorted(detected_chinese[:2])
        comp_filename = f"{sorted_entities[0]}_vs_{sorted_entities[1]}.md"
        comp_rel_path = os.path.join("07_Comparisons", comp_filename)
        comp_abs_path = os.path.join(args.path, comp_rel_path)
        
        comparison_info = {
            "entities": sorted_entities,
            "exists": os.path.exists(comp_abs_path),
            "path": comp_rel_path if os.path.exists(comp_abs_path) else ""
        }
        
        # Buscar patrón en base de datos SQLite
        try:
            db_pat = history.find_similar_pattern(sorted_entities, "comparison")
            if db_pat:
                pattern_info = {
                    "exists": True,
                    "id": db_pat['id'],
                    "usage_count": db_pat['usage_count'],
                    "filepath": db_pat['filepath']
                }
            else:
                pattern_info = {
                    "exists": False
                }
        except Exception as e:
            pattern_info = {"error": str(e)}
            
    # Si detecta solo 1 palabra china y palabras clave de etimología/origen
    elif len(detected_chinese) == 1 and any(k in message.lower() for k in ["etimologia", "origen", "diacronia", "evolucion"]):
        intent = "diacronia"
        
    # Si detecta solo 1 palabra china y palabras clave de campo semántico
    elif len(detected_chinese) == 1 and any(k in message.lower() for k in ["campo", "semantico", "asociacion", "relacionadas"]):
        intent = "semantic_field"
        
    # Si detecta solo 1 palabra y ninguna clave anterior, es vocabulario básico
    elif len(detected_chinese) == 1:
        intent = "vocabulary"
        
    # 3. Reporte Consolidado
    report = {
        "intent_detected": intent,
        "chinese_words_detected": detected_chinese,
        "entities_status": entities,
        "comparison": comparison_info,
        "pattern_database": pattern_info,
        "vault_structure": {
            "hsk_directories": ["01_Vocab/1_Monosilabos", "01_Vocab/2_Bisilabos", "01_Vocab/3_Polisilabos", "01_Vocab/4_Chengyu"],
            "layer_directories": ["07_Comparisons", "08_Diacronia", "09_SemanticFields", "10_ErrorPatterns"]
        }
    }
    
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
