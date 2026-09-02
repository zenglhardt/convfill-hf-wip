#!/usr/bin/env bash
# Create the local Python virtual environment for the ConvFill speech demo.
#
# Idempotent: re-running refreshes the installed packages, the NLTK assets and
# the browser dependencies without recreating anything that already works.
#
#   bash scripts/setup_demo.sh
#   PYTHON=/opt/homebrew/bin/python3.12 bash scripts/setup_demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"
UI_DIR="$REPO_ROOT/web_demo/hf_interface"

cd "$REPO_ROOT"

# --- pick an interpreter -----------------------------------------------------
PYTHON_CMD="${PYTHON:-}"
if [ -z "$PYTHON_CMD" ]; then
  for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_CMD="$(command -v "$candidate")"
      break
    fi
  done
fi

if [ -z "$PYTHON_CMD" ] || ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "[error] No suitable Python interpreter found." >&2
  echo "The demo needs Python 3.11 or 3.12. Install one, for example:" >&2
  echo "  brew install python@3.12" >&2
  echo "Then re-run this script, optionally pointing at it explicitly:" >&2
  echo "  PYTHON=/opt/homebrew/bin/python3.12 bash scripts/setup_demo.sh" >&2
  exit 1
fi

if ! "$PYTHON_CMD" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)'; then
  echo "[error] $PYTHON_CMD is $("$PYTHON_CMD" -c 'import platform; print(platform.python_version())'), but the demo requires >=3.11,<3.13." >&2
  echo "Set PYTHON to a 3.11 or 3.12 interpreter and re-run." >&2
  exit 1
fi

echo "[setup] python: $PYTHON_CMD ($("$PYTHON_CMD" -c 'import platform; print(platform.python_version())'))"

# --- virtual environment -----------------------------------------------------
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[setup] creating virtual environment at $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
else
  echo "[setup] reusing existing virtual environment at $VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

echo "[setup] upgrading pip"
"$VENV_PY" -m pip install --upgrade pip

echo "[setup] installing convfill (editable) with dev extras"
"$VENV_PY" -m pip install -e ".[dev]"

# --- NLTK assets -------------------------------------------------------------
# The pinned Hugging Face pipeline looks up punkt_tab and
# averaged_perceptron_tagger_eng at import time (the latter under
# ``tokenizers/``; web_demo/hf_convfill/server.py redirects that lookup to the
# ``taggers/`` directory NLTK actually installs it into). Installing both into
# the venv keeps startup offline.
NLTK_TARGET="$("$VENV_PY" -c 'import sys, os; print(os.path.join(sys.prefix, "share", "nltk_data"))')"
echo "[setup] installing NLTK assets into $NLTK_TARGET"
mkdir -p "$NLTK_TARGET"
"$VENV_PY" -m nltk.downloader -d "$NLTK_TARGET" punkt_tab averaged_perceptron_tagger_eng

NLTK_DATA="$NLTK_TARGET" "$VENV_PY" - <<'PY'
import nltk

for resource in ("tokenizers/punkt_tab", "taggers/averaged_perceptron_tagger_eng"):
    nltk.data.find(resource)
print("[setup] NLTK assets verified")
PY

# --- browser dependencies ----------------------------------------------------
if ! command -v npm >/dev/null 2>&1; then
  echo "[warn] npm was not found on PATH; skipping the browser interface install." >&2
  echo "[warn] Install Node.js 24 (see .nvmrc in the repository root) and run:" >&2
  echo "[warn]   npm ci --prefix web_demo/hf_interface" >&2
else
  NODE_MAJOR="$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')"
  if [ "${NODE_MAJOR:-}" != "24" ]; then
    echo "[warn] node $(node -v 2>/dev/null || echo '?') detected; the interface is pinned to Node 24." >&2
    echo "[warn] Continuing anyway; run 'nvm install && nvm use' from the repository root if the install fails." >&2
  fi
  echo "[setup] installing browser dependencies (npm ci)"
  npm ci --prefix "$UI_DIR"
fi

echo
echo "Setup complete."
echo "  run the demo:  export ANTHROPIC_API_KEY=...  &&  bash scripts/run_web_demo.sh"
echo "  run the tests: $VENV_PY -m pytest"
