#!/bin/bash
# Start the generator server

# Determine script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Cargar variables de entorno del archivo .env si existe
if [ -f .env ]; then
  echo "Cargando variables de entorno desde el archivo .env..."
  export $(cat .env | grep -v '^#' | xargs)
fi

export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "WARNING: OPENROUTER_API_KEY está vacío. Recuerda configurarla en la interfaz web o en el archivo .env."
fi

echo "Iniciando MemoryWiki Vocabulary Generator en http://127.0.0.1:8000 ..."
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

