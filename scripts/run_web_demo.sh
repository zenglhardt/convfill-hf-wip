#!/usr/bin/env bash
# Launch the Hugging Face realtime speech pipeline and its browser interface.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$REPO_ROOT/web_demo/hf_interface"
S2S_PORT="${S2S_PORT:-8765}"
UI_PORT="${UI_PORT:-7860}"
HF_S2S_STT="${HF_S2S_STT:-parakeet-tdt}"
HF_S2S_TTS="${HF_S2S_TTS:-qwen3}"
CONVFILL_CONFIG="${CONVFILL_CONFIG:-configs/demo_mode/convfill_simple_config.json}"
CONVFILL_MODE="${CONVFILL_MODE:-normal}"
EXPECTED_CONDA_ENV="${HF_DEMO_CONDA_ENV:-hf-demo}"

cd "$REPO_ROOT"

if [ "${CONDA_DEFAULT_ENV:-}" != "$EXPECTED_CONDA_ENV" ]; then
  echo "[error] The speech demo must run in the '$EXPECTED_CONDA_ENV' Conda environment." >&2
  echo "Run: conda activate $EXPECTED_CONDA_ENV" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-$CONDA_PREFIX/bin/python}"
export NLTK_DATA="${NLTK_DATA:-$CONDA_PREFIX/share/nltk_data}"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[error] ANTHROPIC_API_KEY is not set." >&2
  echo "Load ~/.secret manually in this shell, then run this script again." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import speech_to_speech, anthropic, strip_markdown; import web_demo.hf_convfill' >/dev/null 2>&1; then
  echo "[error] ConvFill speech dependencies are not installed in '$EXPECTED_CONDA_ENV'." >&2
  echo "Create or update it from web_demo/environment.yml." >&2
  exit 1
fi

if [ ! -d "$UI_DIR/node_modules" ]; then
  echo "[error] Browser dependencies are missing. Run:" >&2
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
