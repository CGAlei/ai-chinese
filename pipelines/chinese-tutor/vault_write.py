#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import argparse

# Asegurar la ruta de búsqueda de la biblioteca local
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib.nlp_helper import get_pinyin_slug
from lib.vault_core import (
    write_or_merge_ficha,
    log_error_v2,
    add_grammar_v2,
    write_or_merge_comparison,
    write_error_pattern,
    ENABLE_PHASE_3
)


def main():
    parser = argparse.ArgumentParser(description="Permite al Tutor de Chino añadir registros estructurados bajo la arquitectura v2.")
    parser.add_argument("--path", default="/home/alex/Ai-chinese/data/vaults/chinese-tutor", help="Ruta al baúl de notas")
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Comando a ejecutar")
    
    # Subparser para agregar vocabulario
    parser_vocab = subparsers.add_parser("add_vocab", help="Registrar o actualizar una ficha de vocabulario")
    parser_vocab.add_argument("--word", required=True, help="Caracteres de la palabra")
    parser_vocab.add_argument("--pinyin", required=True, help="Pinyin con tonos")
    parser_vocab.add_argument("--meaning", required=True, help="Significado en español")
    parser_vocab.add_argument("--type", required=True, help="Tipo de palabra (ej. verbo, adjetivo, sustantivo)")
    parser_vocab.add_argument("--notes", default="-", help="Ejemplos o aclaraciones de colocación")
    parser_vocab.add_argument("--hsk", type=int, default=None, help="Nivel HSK")
    parser_vocab.add_argument("--radical", default="", help="Radical del carácter principal")
    parser_vocab.add_argument("--strokes", type=int, default=0, help="Cantidad de trazos")
    parser_vocab.add_argument("--sentences-json", default=None, help="JSON con lista de oraciones")
    
    # Subparser para registrar errores
    parser_error = subparsers.add_parser("log_error", help="Registrar un error conceptual de palabra")
    parser_error.add_argument("--error", required=True, help="Intento erróneo del usuario")
    parser_error.add_argument("--correction", required=True, help="Corrección propuesta")
    parser_error.add_argument("--explanation", required=True, help="Explicación gramatical del error")
    parser_error.add_argument("--target-word", required=True, help="Palabra objetivo relacionada con el error")
    parser_error.add_argument("--error-type", default="general", help="Clasificación del error")
    
    # Subparser para notas de gramática
    parser_grammar = subparsers.add_parser("add_grammar", help="Añadir apuntes gramaticales")
    parser_grammar.add_argument("--title", required=True, help="Título del tema gramatical")
    parser_grammar.add_argument("--content", required=True, help="Contenido del apunte (puedes usar Markdown y \\n para saltos)")

    # Subparser para agregar comparaciones
    parser_comp = subparsers.add_parser("add_comparison", help="Registrar o actualizar una ficha de comparación")
    parser_comp.add_argument("--entities", required=True, help="Lista de entidades separadas por coma")
    parser_comp.add_argument("--comp-type", default="semantico_pragmatico", choices=["semantico_pragmatico", "gramatical"], help="Tipo de comparación")
    parser_comp.add_argument("--dimensions", default=None, help="Dimensiones separadas por coma")
    parser_comp.add_argument("--hsk-range", default=None, help="Niveles HSK implicados separados por coma")
    parser_comp.add_argument("--session", default="", help="ID de la sesión de origen")
    parser_comp.add_argument("--pattern", default="", help="ID o patrón de pregunta de origen")
    parser_comp.add_argument("--details-json", default=None, help="JSON con los detalles de las dimensiones")
    parser_comp.add_argument("--tags", default=None, help="Tags separados por coma")

    # Subparser para analizar errores y generar patrón
    parser_analyze_err = subparsers.add_parser("analyze_errors", help="Analizar errores de una palabra y generar/actualizar su patrón si procede")
    parser_analyze_err.add_argument("--target-word", required=True, help="Palabra objetivo para analizar")
    parser_analyze_err.add_argument("--cause", default="", help="Causa raíz lingüística (opcional)")
    
    args = parser.parse_args()
    
    if args.command == "add_vocab":
        word_data = {
            'word': args.word,
            'pinyin': get_pinyin_slug(args.pinyin),
            'pinyin_toned': args.pinyin,
            'char_count': len(args.word),
            'category': 'chengyu' if len(args.word) == 4 and args.type.lower() == 'chengyu' else 'palabra',
            'word_type': [args.type.lower()],
            'hsk': args.hsk,
            'radical': args.radical,
            'stroke_count': args.strokes,
            'meaning': args.meaning,
            'notes': args.notes
        }
        if args.sentences_json:
            import json
            try:
                word_data['sentences'] = json.loads(args.sentences_json)
            except Exception as e:
                print(f"Error al decodificar oraciones JSON: {e}", file=sys.stderr)
        write_or_merge_ficha(args.path, word_data)
        
    elif args.command == "log_error":
        log_error_v2(args.path, args.error, args.correction, args.explanation, args.target_word, args.error_type)
        
    elif args.command == "add_grammar":
        add_grammar_v2(args.path, args.title, args.content)

    elif args.command == "add_comparison":
        entities = [e.strip() for e in args.entities.split(",") if e.strip()]
        dims = [d.strip() for d in args.dimensions.split(",") if d.strip()] if args.dimensions else None
        hsk = [int(h.strip()) for h in args.hsk_range.split(",") if h.strip().isdigit()] if args.hsk_range else []
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        
        details = {}
        if args.details_json:
            import json
            try:
                details = json.loads(args.details_json)
            except Exception as e:
                print(f"Error al decodificar detalles JSON: {e}", file=sys.stderr)
                
        comp_data = {
            'comparison_type': args.comp_type,
            'hsk_range': hsk,
            'source_session': args.session,
            'source_question_pattern': args.pattern,
            'details': details
        }
        if dims:
            comp_data['dimensions'] = dims
        if tags:
            comp_data['tags'] = tags
            
        filepath = write_or_merge_comparison(args.path, entities, comp_data)

        # === [BETA FASE 3: REGISTRO AUTOMÁTICO EN SQLITE] ===
        if ENABLE_PHASE_3:
            try:
                import history
                rel_filepath = os.path.relpath(filepath, args.path)
                history.save_or_update_pattern(
                    pattern_type='comparison',
                    entities=entities,
                    dimensions=dims if dims else ["内涵", "用法", "搭配", "感情色彩"],
                    filepath=rel_filepath,
                    session_id=args.session
                )
            except Exception as e:
                print(f"⚠ Error al registrar patrón en SQLite: {e}", file=sys.stderr)
        # ===================================================

    elif args.command == "analyze_errors":
        analysis = {}
        if args.cause:
            analysis['underlying_cause'] = args.cause
        write_error_pattern(args.path, args.target_word, analysis)


if __name__ == "__main__":
    main()
