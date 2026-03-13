#!/usr/bin/env bash
# run-evals.sh — Run all models against all transcripts and templates.
#
# Usage:
#   ./evals/run-evals.sh                    # run all (sequential)
#   ./evals/run-evals.sh --parallel         # run 3 templates in parallel
#   ./evals/run-evals.sh --template soap    # run one template only
#   ./evals/run-evals.sh --model gemma3n-e2b --transcript 01  # single test run
#   ./evals/run-evals.sh --dry-run          # show what would run

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-detect Python: prefer sidecar venv, fall back to system
SIDECAR_PYTHON="$REPO_ROOT/sidecar/.venv/bin/python3"
if [ -x "$SIDECAR_PYTHON" ] && "$SIDECAR_PYTHON" -c "import mlx_lm" &>/dev/null; then
  PYTHON="$SIDECAR_PYTHON"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "ERROR: No python3 found. Run: cd sidecar && uv sync"
  exit 1
fi

echo "Using Python: $PYTHON"

# Check models are downloaded
MODEL_COUNT=$(find "$SCRIPT_DIR/models" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$MODEL_COUNT" -eq 0 ]; then
  echo "ERROR: No models found. Run ./evals/download-models.sh first."
  exit 1
fi
echo "Found $MODEL_COUNT local models."

# Parse args: extract --parallel, pass everything else through
PARALLEL=false
HAS_TEMPLATE=false
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--parallel" ]; then
    PARALLEL=true
  else
    ARGS+=("$arg")
    if [ "$arg" = "--template" ]; then
      HAS_TEMPLATE=true
    fi
  fi
done

# If --parallel is used with --template, warn and fall back to sequential
if [ "$PARALLEL" = true ] && [ "$HAS_TEMPLATE" = true ]; then
  echo "WARNING: --parallel and --template are incompatible. Running sequentially."
  PARALLEL=false
fi

if [ "$PARALLEL" = true ]; then
  echo ""
  echo "Running 3 templates in parallel..."
  echo ""

  $PYTHON "$SCRIPT_DIR/scripts/run-models.py" --template soap ${ARGS[@]+"${ARGS[@]}"} &
  PID1=$!
  $PYTHON "$SCRIPT_DIR/scripts/run-models.py" --template hp ${ARGS[@]+"${ARGS[@]}"} &
  PID2=$!
  $PYTHON "$SCRIPT_DIR/scripts/run-models.py" --template dap ${ARGS[@]+"${ARGS[@]}"} &
  PID3=$!

  # Wait for all and report
  FAILED=0
  wait $PID1 || FAILED=$((FAILED + 1))
  wait $PID2 || FAILED=$((FAILED + 1))
  wait $PID3 || FAILED=$((FAILED + 1))

  echo ""
  if [ "$FAILED" -gt 0 ]; then
    echo "WARNING: $FAILED template run(s) failed. Check output above."
    exit 1
  fi
  echo "All templates complete."
else
  $PYTHON "$SCRIPT_DIR/scripts/run-models.py" ${ARGS[@]+"${ARGS[@]}"}
fi
