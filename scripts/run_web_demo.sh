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

# Validate only the selected provider. Self-hosted vLLM needs no commercial key.
"$PYTHON_BIN" - "$CONVFILL_CONFIG" "$CONVFILL_MODE" <<'CHECK'
import sys
from src.inference.convfill_stack.run_convfill import ConvFillConfig
from src.utils.api_keys import get_api_key
config = ConvFillConfig(sys.argv[1], mode=sys.argv[2])
if config.backend_model_mode != "vllm":
    get_api_key(config.backend_model_mode)
CHECK

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

export CONVFILL_PIPELINE_URL="ws://127.0.0.1:${S2S_PORT}/v1/realtime"
export STARTUP_GREETING="${STARTUP_GREETING-Greet the user warmly in one short sentence, then invite them to talk.}"

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

echo "[speech] starting Hugging Face speech-to-speech on port ${S2S_PORT}"
echo "[speech] STT=${HF_S2S_STT} LLM=ConvFill(${CONVFILL_CONFIG}:${CONVFILL_MODE}) TTS=${HF_S2S_TTS}"
speech_args=()
if [ "$HF_S2S_STT" = openai ]; then
  speech_args+=(--openai_stt_base_url "${CONVFILL_STT_URL:?Set CONVFILL_STT_URL including /v1}" --openai_stt_model "${CONVFILL_STT_MODEL:-Qwen/Qwen3-ASR-1.7B}" --openai_stt_timeout 30)
  [ -z "${CONVFILL_STT_API_KEY:-}" ] || speech_args+=(--openai_stt_api_key "$CONVFILL_STT_API_KEY")
fi
if [ "$HF_S2S_TTS" = openai ]; then
  speech_args+=(--openai_tts_base_url "${CONVFILL_TTS_URL:?Set CONVFILL_TTS_URL including /v1}" --openai_tts_model "${CONVFILL_TTS_MODEL:-Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice}" --openai_tts_voice "${CONVFILL_TTS_VOICE:-aiden}" --openai_tts_stream true --openai_tts_timeout 30)
  [ -z "${CONVFILL_TTS_API_KEY:-}" ] || speech_args+=(--openai_tts_api_key "$CONVFILL_TTS_API_KEY")
fi
"$PYTHON_BIN" -m web_demo.hf_convfill.server serve \
  --host 127.0.0.1 \
  --port "$S2S_PORT" \
  --stt "$HF_S2S_STT" \
  --llm_backend convfill \
  --convfill_config_path "$CONVFILL_CONFIG" \
  --convfill_mode "$CONVFILL_MODE" \
  --tts "$HF_S2S_TTS" \
  --num_pipelines 1 \
  --enable_live_transcription "${speech_args[@]}" &
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
  --host "${UI_HOST:-127.0.0.1}" --port "$UI_PORT" --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-access-log &
UI_PID=$!

echo
echo "ConvFill realtime voice demo is running."
echo "  open: http://127.0.0.1:${UI_PORT}"
echo "  press Ctrl+C to stop both processes"
echo

# Supervise both children: a failed pipeline must stop the public UI too.
while kill -0 "$S2S_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do
  sleep 1
done
exit 1
