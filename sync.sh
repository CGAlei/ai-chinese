#!/usr/bin/env bash
# =============================================================================
# sync.sh — Unified script to run Dictionary Enrichment and Audio SRS Pipeline
# =============================================================================

set -e  # Exit on error

# Resolve project root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 1. Run dictionary enrichment
echo "========================================="
echo "🔄 Step 1: Running Dictionary Enrichment"
echo "========================================="
./pipelines/enrich.sh

echo ""

# 2. Run audio generation pipeline
echo "========================================="
echo "🎙️ Step 2: Running Audio & SRS Generator"
echo "========================================="
uv run pipelines/audio-srs-pipeline/pipeline_azure.py "$@"

echo ""
echo "========================================="
echo "✅ All steps completed successfully!"
echo "========================================="
