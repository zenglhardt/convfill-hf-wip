#!/usr/bin/env bash
# Launch the Hugging Face realtime speech pipeline and its browser interface.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$REPO_ROOT/web_demo/hf_interface"
S2S_PORT="${S2S_PORT:-8765}"
UI_PORT="${UI_PORT:-7860}"
HF_S2S_STT="${HF_S2S_STT:-faster-whisper}"
HF_S2S_TTS="${HF_S2S_TTS:-pocket}"
CONVFILL_CONFIG="${CONVFILL_CONFIG:-configs/demo_mode/convfill_simple_config.json}"
CONVFILL_MODE="${CONVFILL_MODE:-normal}"

cd "$REPO_ROOT"

# Resolve the interpreter: an explicit override, an already-activated venv, or
# the repo-local .venv created by scripts/setup_demo.sh.
if [ -n "${PYTHON_BIN:-}" ]; then
  :
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  echo "[error] No Python environment found for the speech demo." >&2
  echo "Run: bash scripts/setup_demo.sh" >&2
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[error] PYTHON_BIN='$PYTHON_BIN' is not an executable interpreter." >&2
  exit 1
fi

if [ -z "${NLTK_DATA:-}" ]; then
  NLTK_DATA="$("$PYTHON_BIN" -c 'import sys, os; print(os.path.join(sys.prefix, "share", "nltk_data"))')"
fi
export NLTK_DATA

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[error] ANTHROPIC_API_KEY is not set." >&2
  echo "Export it in this shell, then run this script again:" >&2
  echo "  export ANTHROPIC_API_KEY=..." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import speech_to_speech, anthropic, strip_markdown; import web_demo.hf_convfill' >/dev/null 2>&1; then
  echo "[error] ConvFill speech dependencies are not installed in '$("$PYTHON_BIN" -c "import sys; print(sys.prefix)")'." >&2
  echo "Run: bash scripts/setup_demo.sh" >&2
  exit 1
fi

if [ ! -d "$UI_DIR/node_modules" ]; then
  echo "[error] Browser dependencies are missing. Run:" >&2
  echo "  bash scripts/setup_demo.sh" >&2
  echo "or, for the browser interface alone:" >&2
  echo "  npm ci --prefix web_demo/hf_interface" >&2
  exit 1
fi

export SPEECH_TO_SPEECH_URL="${SPEECH_TO_SPEECH_URL:-ws://127.0.0.1:${S2S_PORT}/v1/realtime}"
export STARTUP_GREETING="${STARTUP_GREETING:-}"

S2S_PID=""
UI_PID=""

cleanup() {
  echo
  echo "[shutdown] stopping voice demo..."
  [ -n "$S2S_PID" ] && kill "$S2S_PID" 2>/dev/null || true
  [ -n "$UI_PID" ] && kill "$UI_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[speech] starting Hugging Face speech-to-speech on ${SPEECH_TO_SPEECH_URL}"
echo "[speech] STT=${HF_S2S_STT} LLM=ConvFill(${CONVFILL_CONFIG}:${CONVFILL_MODE}) TTS=${HF_S2S_TTS}"
"$PYTHON_BIN" -m web_demo.hf_convfill.server serve \
  --host 127.0.0.1 \
  --port "$S2S_PORT" \
  --stt "$HF_S2S_STT" \
  --llm_backend convfill \
  --convfill_config_path "$CONVFILL_CONFIG" \
  --convfill_mode "$CONVFILL_MODE" \
  --tts "$HF_S2S_TTS" \
  --enable_live_transcription &
S2S_PID=$!

echo -n "[speech] waiting for :${S2S_PORT}"
for _ in $(seq 1 240); do
  if (echo >/dev/tcp/127.0.0.1/"$S2S_PORT") >/dev/null 2>&1; then
    echo " ready"
    break
  fi
  if ! kill -0 "$S2S_PID" 2>/dev/null; then
    echo
    echo "[error] speech-to-speech exited during startup." >&2
    wait "$S2S_PID"
  fi
  echo -n "."
  sleep 0.5
done

if ! (echo >/dev/tcp/127.0.0.1/"$S2S_PORT") >/dev/null 2>&1; then
  echo
  echo "[error] speech-to-speech did not become ready within 120 seconds." >&2
  exit 1
fi

echo "[interface] starting on http://127.0.0.1:${UI_PORT}"
"$PYTHON_BIN" -m uvicorn --app-dir "$UI_DIR" server:app \
  --host 127.0.0.1 --port "$UI_PORT" &
UI_PID=$!

echo
echo "ConvFill realtime voice demo is running."
echo "  open: http://127.0.0.1:${UI_PORT}"
echo "  press Ctrl+C to stop both processes"
echo

wait
