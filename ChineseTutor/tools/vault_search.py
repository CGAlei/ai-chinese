#!/usr/bin/env python3
import os
import sys
import argparse
import re

def search_vault(query, vault_path, search_filenames=True, case_insensitive=True):
    print(f"Buscando '{query}' en el baúl de notas: {vault_path}\n" + "="*60)
    
    query_regex = re.escape(query)
    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(query_regex, flags)
    
    matches_found = 0
    
    # 1. Buscar coincidencia en nombres de archivo
    if search_filenames:
        print("📁 ARCHIVOS COINCIDENTES:")
        for root, dirs, files in os.walk(vault_path):
            # Omitir carpetas ocultas
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith('.md') and pattern.search(file):
                    rel_path = os.path.relpath(os.path.join(root, file), vault_path)
                    print(f"  - {rel_path}")
                    matches_found += 1
        print("")

    # 2. Buscar coincidencia dentro del contenido de los archivos
    print("📝 CONTENIDO COINCIDENTE:")
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, vault_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                clean_line = line.strip()
                                print(f"  {rel_path}:{line_num} -> {clean_line}")
                                matches_found += 1
                except Exception as e:
                    # Silenciar errores de lectura de archivo individuales para no corromper la salida del agente
                    pass
                    
    if matches_found == 0:
        print("  No se encontraron coincidencias para la búsqueda.")
    print("="*60)
    return matches_found

def main():
    parser = argparse.ArgumentParser(description="Busca términos o caracteres en el Vault de notas Markdown del Tutor de Chino.")
    parser.add_argument("query", help="Término o carácter chino a buscar en las notas")
    parser.add_argument("--path", default="/home/alex/Ai-chinese/ChineseTutor/vault", help="Ruta al directorio de notas (default: /home/alex/Ai-chinese/ChineseTutor/vault)")
    parser.add_argument("--no-filenames", action="store_true", help="Desactivar la búsqueda por nombres de archivo")
    parser.add_argument("--case-sensitive", action="store_true", help="Hacer la búsqueda sensible a mayúsculas/minúsculas")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.path):
        print(f"Error: La ruta especificada '{args.path}' no existe.", file=sys.stderr)
        sys.exit(1)
        
    search_vault(
        query=args.query,
        vault_path=args.path,
        search_filenames=not args.no_filenames,
        case_insensitive=not args.case_sensitive
    )

if __name__ == "__main__":
    main()
