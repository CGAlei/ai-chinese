#!/usr/bin/env bash
# =============================================================================
# enrich.sh — One-command dictionary enrichment (in-place)
#
# Usage:
#   ./enrich.sh                          # enriches Dict/maindata.json in-place
#   ./enrich.sh Dict/other_file.json     # enriches a different file in-place
#   ./enrich.sh --dry-run                # preview only (no API calls)
#
# Workflow:
#   1. Export a backup from Mo-Reader or Mo-Cards → save as Dict/maindata.json
#   2. Run ./enrich.sh
#   3. Import the enriched maindata.json back into any app
#
# Setup (first time only):
#   1. Edit .env and set your OPENAI_API_KEY
#   2. chmod +x enrich.sh
# =============================================================================

set -e  # Exit immediately on any error

# ── Resolve script directory so it works from any location ───────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load API key from .env ────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[ERROR] .env file not found at: $ENV_FILE"
    echo "        Create it with: echo 'OPENAI_API_KEY=sk-...' > .env"
    exit 1
fi

# Export variables from .env (ignores comments and blank lines)
set -o allexport
source "$ENV_FILE"
set +o allexport

if [[ -z "$OPENAI_API_KEY" || "$OPENAI_API_KEY" == *"replace-with"* ]]; then
    echo "[ERROR] OPENAI_API_KEY is not set or still placeholder in .env"
    echo "        Edit .env and paste your real key."
    exit 1
fi

# ── Input file (default or from argument) ────────────────────────────────────
DEFAULT_FILE="Dict/maindata.json"
INPUT_FILE="${1:-$DEFAULT_FILE}"

# If a path was given, shift so remaining args ($2, $3...) are passed through
if [[ $# -ge 1 ]]; then
    shift
fi

# Resolve to absolute path if relative
if [[ ! "$INPUT_FILE" = /* ]]; then
    INPUT_FILE="$SCRIPT_DIR/$INPUT_FILE"
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "[ERROR] File not found: $INPUT_FILE"
    echo "        Create it by exporting a backup from Mo-Reader or Mo-Cards."
    exit 1
fi

# ── Run inside the unified uv environment ─────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔤  Dictionary Enrichment"
echo "  📁  File   : $INPUT_FILE"
echo "  🐍  Python : uv run python"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

uv run python "$SCRIPT_DIR/endict.py" "$INPUT_FILE" --in-place "$@"

