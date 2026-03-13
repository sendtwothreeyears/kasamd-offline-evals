#!/usr/bin/env bash
# download-models.sh — Download all candidate models for clinical note generation evals.
#
# Downloads MLX-community 4-bit quantized versions where available,
# falls back to converting from HF originals via mlx-lm.
#
# Models are stored in evals/models/ and gitignored (too large to commit).
# Anyone cloning the repo can run this script to populate them.
#
# Usage:
#   ./evals/download-models.sh          # download all
#   ./evals/download-models.sh --list   # just print model list
#   ./evals/download-models.sh 3        # download only model #3

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODELS_DIR="$SCRIPT_DIR/models"

# Auto-detect Python with mlx-lm: prefer sidecar venv, fall back to system python3
SIDECAR_PYTHON="$REPO_ROOT/sidecar/.venv/bin/python3"
if [ -x "$SIDECAR_PYTHON" ] && "$SIDECAR_PYTHON" -c "import mlx_lm" &>/dev/null; then
  PYTHON="$SIDECAR_PYTHON"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "ERROR: No python3 found."
  exit 1
fi

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
# Format: "INDEX|HF_ID|LOCAL_DIR|DISPLAY_NAME|METHOD"
#   METHOD: "download" = already MLX 4-bit quantized, just pull
#           "convert"  = download original weights, convert to MLX 4-bit locally

MODELS=(
  "1|google/medgemma-1.5-4b-it|medgemma-1.5-4b-it-4bit|MedGemma 1.5 4B IT|convert"
  "2|mlx-community/medgemma-4b-it-4bit|medgemma-4b-it-4bit|MedGemma 4B IT (MLX 4-bit)|download"
  "3|alpha-ai/LLAMA3-3B-Medical-COT|llama3-3b-medical-cot-4bit|LLAMA3-3B-Medical-COT|convert"
  "4|mlx-community/Llama-3.2-3B-Instruct-4bit|llama-3.2-3b-instruct-4bit|Llama 3.2 3B Instruct (MLX 4-bit)|download"
  "5|mlx-community/gemma-3n-E2B-it-lm-4bit|gemma-3n-e2b-4bit|Gemma3N E2B baseline (MLX 4-bit)|download"
  "6|mlx-community/Phi-4-mini-instruct-4bit|phi-4-mini-instruct-4bit|Phi-4 Mini (MLX 4-bit)|download"
  "7|mlx-community/Qwen3.5-4B-MLX-4bit|qwen3.5-4b-4bit|Qwen3.5 4B (MLX 4-bit)|download"
)

TOTAL=${#MODELS[@]}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

check_deps() {
  local missing=0

  info "Using Python: $PYTHON"

  if ! "$PYTHON" -c "import huggingface_hub" &>/dev/null; then
    error "huggingface_hub not installed. Run: pip install huggingface-hub"
    missing=1
  fi

  if ! "$PYTHON" -c "import mlx_lm" &>/dev/null; then
    warn "mlx-lm not installed. Models requiring conversion will fail."
    warn "Install with: pip install mlx-lm"
  fi

  if [[ $missing -eq 1 ]]; then
    exit 1
  fi
}

list_models() {
  echo ""
  echo "Clinical Note Generation — Eval Models"
  echo "========================================"
  echo "Download dir: $MODELS_DIR"
  echo ""
  printf "  %-4s %-46s %-10s %s\n" "#" "HF ID" "Method" "Name"
  printf "  %-4s %-46s %-10s %s\n" "---" "------" "------" "----"
  for entry in "${MODELS[@]}"; do
    IFS='|' read -r idx hf_id local_dir name method <<< "$entry"
    local status="  "
    if [ -d "$MODELS_DIR/$local_dir" ] && [ "$(ls -A "$MODELS_DIR/$local_dir" 2>/dev/null)" ]; then
      status="✓ "
    fi
    printf "  %s%-2s %-46s %-10s %s\n" "$status" "$idx" "$hf_id" "$method" "$name"
  done
  echo ""
  echo "  ✓  = already downloaded"
  echo "  download = pre-quantized MLX 4-bit, pulled from HF"
  echo "  convert  = download original weights, convert to MLX 4-bit locally"
  echo ""
}

download_model() {
  local hf_id="$1"
  local dest="$2"
  local name="$3"

  if [ -d "$dest" ] && [ "$(ls -A "$dest" 2>/dev/null)" ]; then
    info "Already downloaded: $name"
    info "  Path: $dest"
    return 0
  fi

  info "Downloading: $name"
  info "  Source: $hf_id"
  info "  Dest:   $dest"
  "$PYTHON" -c "
from huggingface_hub import snapshot_download
snapshot_download(
    '${hf_id}',
    local_dir='${dest}',
    resume_download=True,
)
print('  Done.')
"
}

convert_model() {
  local hf_id="$1"
  local dest="$2"
  local name="$3"

  if [ -d "$dest" ] && [ "$(ls -A "$dest" 2>/dev/null)" ]; then
    info "Already converted: $name"
    info "  Path: $dest"
    return 0
  fi

  info "Converting to MLX 4-bit: $name"
  info "  Source: $hf_id"
  info "  Dest:   $dest"
  "$PYTHON" -m mlx_lm.convert \
    --hf-path "$hf_id" \
    --mlx-path "$dest" \
    --quantize \
    --q-bits 4

  info "Converted: $name → $dest"
}

process_model() {
  local entry="$1"
  IFS='|' read -r idx hf_id local_dir name method <<< "$entry"
  local dest="$MODELS_DIR/$local_dir"

  echo ""
  step "[$idx/$TOTAL] $name"

  case "$method" in
    download) download_model "$hf_id" "$dest" "$name" ;;
    convert)  convert_model "$hf_id" "$dest" "$name" ;;
    *)        error "Unknown method: $method" ;;
  esac
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--list" ]]; then
  list_models
  exit 0
fi

if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
  echo "Usage:"
  echo "  ./evals/download-models.sh          # download all models"
  echo "  ./evals/download-models.sh --list   # list models (✓ = downloaded)"
  echo "  ./evals/download-models.sh 3        # download model #3 only"
  echo "  ./evals/download-models.sh --help    # this help"
  echo ""
  echo "Models are saved to: evals/models/ (gitignored)"
  exit 0
fi

check_deps
mkdir -p "$MODELS_DIR"

# Single model by index
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  target="$1"
  for entry in "${MODELS[@]}"; do
    IFS='|' read -r idx _ _ _ _ <<< "$entry"
    if [[ "$idx" == "$target" ]]; then
      process_model "$entry"
      echo ""
      info "Done."
      exit 0
    fi
  done
  error "No model with index $target. Use --list to see available models."
  exit 1
fi

# Download all
echo ""
info "Downloading all $TOTAL eval models..."
info "Destination: $MODELS_DIR"

for entry in "${MODELS[@]}"; do
  process_model "$entry"
done

echo ""
info "=========================================="
info "All $TOTAL models downloaded."
info "=========================================="
echo ""
info "Models saved to: $MODELS_DIR"
echo ""
ls -1d "$MODELS_DIR"/*/ 2>/dev/null | while read -r dir; do
  size=$(du -sh "$dir" 2>/dev/null | cut -f1)
  echo "  $size  $(basename "$dir")"
done
