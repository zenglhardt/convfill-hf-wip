# AGENTS.md

Guidance for coding agents and new contributors working in this repository.

## What this repo is

ConvFill is a voice agent that pairs a small local "Talker" language model with a large cloud
"Reasoner". The Reasoner streams concise knowledge phrases in the background; the Talker turns each
phrase (or a `<sil>` filler signal) into the sentence the user actually hears, so the agent replies
immediately without waiting on the cloud model. This repository now contains only the inference side
and the live browser demo, built on Hugging Face's `speech-to-speech` package pinned at commit
`b21e54d6a845c54308bc62500b57f9a2b2aa93ac`. All training code has been removed, and the environment
is a plain Python virtualenv (no Conda).

## Repository map

| Path | Role |
|------|------|
| `src/inference/convfill_stack/` | The Talker + Reasoner stack. `run_convfill.py` defines `ConvFillConfig` and `ConvFillSystem`; `convfill_backend_multi.py` drives the Reasoner across task modes; `convfill_frontend.py` runs the local Talker (MLX or HF transformers). |
| `src/inference/shared/` | Conversation engine, `dialogue_state_manager.py`, `turn_state_manager.py`, `mcp_client.py`. |
| `src/inference/single_model_stack/` | Library code for running the Reasoner or Talker alone. Used by the engine, not run directly. |
| `src/inference/rag/` | `RunRAG` plus the committed FAISS index and chunk store for `rag` mode. |
| `src/utils/api_keys.py` | The only place API keys are read (from env vars). |
| `web_demo/hf_convfill/` | The active adapter: `server.py` (entry point), `backend.py` (registry), `handler.py` (the LLM-stage handler), `delivery.py` (the output-queue delivery ledger), tests. |
| `web_demo/hf_interface/` | Vendored Hugging Face browser UI plus a local FastAPI static host (`server.py`, `test_server.py`). See `UPSTREAM.md`. |
| `configs/` | Demo configs, Talker configs, Reasoner model names, Reasoner prompt templates. |
| `scripts/` | `setup_demo.sh`, `run_web_demo.sh`. |
| `web_demo/backend/`, `web_demo/frontend/` | **Legacy.** The previous FastAPI + React/Vite demo, kept for reference only. Not installable from the current dependencies, not tested, not run. |
| `src/tts/` | **Legacy.** Only serves the old demo (`piper_tts.py`, `avspeech_tts`). |

## Environment setup

Python 3.11 or 3.12 only (`requires-python = ">=3.11,<3.13"`). Node.js 24 for the browser interface
(`.nvmrc` at the repo root).

```bash
bash scripts/setup_demo.sh
```

The script is idempotent. It picks `python3.12` (falling back to `python3.11`), creates `.venv`,
runs `pip install -e ".[dev]"`, installs the NLTK assets `punkt_tab` and
`averaged_perceptron_tagger_eng` into `.venv/share/nltk_data`, and runs
`npm ci --prefix web_demo/hf_interface`. Override the interpreter with `PYTHON=/path/to/python3.12`.

Manual equivalent:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m nltk.downloader -d .venv/share/nltk_data punkt_tab averaged_perceptron_tagger_eng
npm ci --prefix web_demo/hf_interface
```

Extras: `rag` (faiss-cpu, sentence-transformers), `mcp`, `gemini` (google-generativeai),
`dev` (pytest, httpx). Example: `pip install -e ".[dev,rag,mcp]"`.

Models download from the Hugging Face Hub on first run. The target speech pair for the published
demo is `mlx-community/parakeet-tdt-0.6b-v3` (STT) and
`mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit` (TTS). The Talker is
`vysri/Qwen-0.6B-ConvFill_mlx_q8` (from `configs/convfill_frontend_configs/convfill_qwen3_0.6B_nd.json`).

Temporary local workaround: `scripts/run_web_demo.sh` currently defaults to `faster-whisper` (STT)
and `pocket` (TTS) because they are lighter for debugging on macOS. Those two backends are pulled in
through the `speech-to-speech[faster-whisper,pocket]` extras in `pyproject.toml`. This is not the
configuration intended for the Hugging Face Spaces release; do not build on it, and expect the
defaults to return to `parakeet-tdt` / `qwen3`. Select the target pair explicitly with
`HF_S2S_STT=parakeet-tdt HF_S2S_TTS=qwen3`.

## Running the demo

```bash
export ANTHROPIC_API_KEY="..."
bash scripts/run_web_demo.sh
```

The launcher starts two loopback-only processes and stops both on Ctrl+C:

1. `python -m web_demo.hf_convfill.server serve --llm_backend convfill ...` on 127.0.0.1:8765,
   serving the Hugging Face realtime WebSocket at `ws://127.0.0.1:8765/v1/realtime`.
2. A uvicorn static host for the browser UI on http://127.0.0.1:7860.

It resolves the interpreter from `PYTHON_BIN`, then an activated `VIRTUAL_ENV`, then `.venv`.

| Variable | Default | Effect |
|----------|---------|--------|
| `CONVFILL_CONFIG` | `configs/demo_mode/convfill_simple_config.json` | Demo config passed to `ConvFillConfig`. |
| `CONVFILL_MODE` | `normal` | Task mode: `normal`, `rag`, `mcp`, or `web_search`. |
| `HF_S2S_STT` | `faster-whisper` (temporary; target is `parakeet-tdt`) | Speech recognition stage. |
| `HF_S2S_TTS` | `pocket` (temporary; target is `qwen3`) | Speech synthesis stage. |
| `S2S_PORT` | `8765` | Realtime WebSocket port. |
| `UI_PORT` | `7860` | Browser interface port. |
| `PYTHON_BIN` | unset | Explicit interpreter override. |
| `NLTK_DATA` | `<venv>/share/nltk_data` | Where NLTK assets are found. |
| `SERPER_API_KEY` | unset | Enables the optional web search endpoint in the UI. |
| `STARTUP_GREETING` | empty | Greeting published to the UI via `/api/config`. |

`rag` mode additionally needs `OPENAI_API_KEY` (query embeddings); a Gemini Reasoner needs
`GEMINI_API_KEY`. `web_search` mode needs a Claude Reasoner and web search enabled for the
Anthropic organization; it uses no extra key.

## Tests

```bash
.venv/bin/python -m pytest
npm test --prefix web_demo/hf_interface
```

Pytest `testpaths` is limited to `web_demo/hf_convfill` and `web_demo/hf_interface`: 37 tests, no
network, driven by a fake ConvFill system and a fake Anthropic stream. The JS suite has 1 test. The legacy
`web_demo/backend/test_tts_markdown.py` is intentionally outside `testpaths` and must stay excluded.
Run both suites before declaring work finished.

## Configuration

- `configs/demo_mode/*.json` are the runtime configs read by both the engine and the realtime
  adapter. `convfill_simple_config.json` defines the `normal` and `web_search` modes;
  `convfill_full_config.json` adds `rag` and `mcp`. Both default the Reasoner to `claude-haiku-4-5-20251001`.
- Top-level keys: `frontend_model_config_path` (which Talker to load), `backend_model_name`,
  `backend_model_mode` (`claude`, `openai`, `gemini`), `num_history_turns`, `tts_mode`. Per-mode
  keys live under `modes.<mode>` and are merged over the top level by `ConvFillConfig`.
- `configs/convfill_frontend_configs/*.json` are the Talker configs, one per released model. Key
  fields: `model_name`, `backend` (`mlx` on Apple Silicon, `hf` elsewhere),
  `convfill_hf_pretrained_path`, `convfill_hf_mlx_pretrained_path`, and the `<sil>` special token
  plus `boundary_tokens` the prompt format depends on.
- `configs/backend_model_configs/<provider>/model_names.json` lists the Reasoner names available per
  provider. `configs/convfill_backend_prompts/` holds the ConvFill Reasoner prompt templates;
  `configs/backend_only_prompts/` holds the Reasoner-only ones.
- `rag` mode config points at `src/inference/rag/uw_phd.index` and `uw_chunks.json`; `mcp` mode
  lists servers under `modes.mcp.task_specific_config.mcp_servers` with `max_tool_iterations`; `web_search` mode takes `tool_type`, `max_uses`,
  `max_continuations`, and an optional `user_location` under
  `modes.web_search.task_specific_config`.
- Note the legacy naming: `frontend` means Talker, `backend` means Reasoner.

## Architecture notes and invariants

Do not break these without understanding why they exist.

- **Only Talker output reaches TTS.** `web_demo/hf_convfill/handler.py` yields `LLMResponseChunk`s
  solely from the `on_response_fragment` callback. Reasoner knowledge goes to `on_thought`, which
  only logs. Never route thoughts into the response stream.
- **`<sil>` filler scheduling depends on the delivery ledger.** `_attach_audio_state` in
  `web_demo/hf_convfill/server.py` monkeypatches `s2s_pipeline.build_pipeline` and swaps each
  pipeline unit's audio output queue (and the matching handler `queue_out`) for a
  `DeliveryLedgerQueue` (`web_demo/hf_convfill/delivery.py`). Overriding `get` lets the ledger record
  every assistant text event Hugging Face dispatches and advance a playhead by the duration of each
  24 kHz int16 audio chunk, so the handler answers `ConvFillSystem.set_audio_in_flight_fn` from real
  delivery. `backend_fn` in `src/inference/convfill_stack/run_convfill.py` emits `<sil>` only when no
  thought is queued, no Talker inference is in flight, and no audio is in flight. Removing any of the
  three probes makes the agent talk over itself or go silent. The ledger only overrides `get`, so
  Hugging Face's barge-in flushes of `q.queue` under `q.mutex` still work.
- **Backend registration order.** `register_convfill_backend()` in `web_demo/hf_convfill/backend.py`
  must run before `speech_to_speech.s2s_pipeline` is imported, because Hugging Face builds its
  argument dataclasses from the registry at import time. `server.py` enforces this ordering; keep
  the import sequence intact.
- **NLTK `find` shim.** `server.py` temporarily redirects
  `tokenizers/averaged_perceptron_tagger_eng` to `taggers/...` while the pinned upstream modules
  import, so a locally installed asset is found instead of triggering a download. It restores
  `nltk.data.find` afterwards.
- **`DialogueStateManager` owns conversation history**
  (`src/inference/shared/dialogue_state_manager.py`). The Hugging Face chat object only supplies the
  newest user text (`latest_user_text`) and receives the final assistant text. Do not treat the HF
  chat as the transcript.
- **Cancellation and barge-in** go through `ConvFillSystem.cancel_turn()`, then exactly one of
  `commit_interrupted_turn` or `discard_pending_turn`. The rule: if the ledger recorded any delivered
  text for the response key, the turn is committed as the joined delivered sentences plus
  `[interrupted by the user]`, which the Reasoner prompt templates explain; if nothing was delivered
  the turn is rolled back, which is also what a speculative reopen needs since it replays the same
  words under a new revision. Every other failure path in `handler.process` still rolls back through
  `DialogueStateManager.rollback_turn`, so a dropped turn never lands in history.
- **Lazy imports keep the base install slim.** The Gemini SDK
  (`src/inference/convfill_stack/model_inference_functions_conversational.py`), faiss and
  sentence-transformers (`convfill_backend_multi.py` -> `src/inference/rag/retreive.py`), and the
  `mcp` client (`src/inference/shared/mcp_client.py`) are imported inside functions. Keep them
  there.
- **API keys come only from the environment** via `src/utils/api_keys.py`: `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY`.

## Conventions

- Use `.venv` and the setup script. Do not reintroduce Conda, environment YAMLs, or activation
  scripts.
- Python 3.11 or 3.12 only. Do not widen `requires-python` without testing.
- Never commit API keys, tokens, or `.env` files. Keys are read from the environment at runtime.
- Keep `web_demo/hf_interface` pristine so it can be re-synced with upstream. Only `index.html`,
  `main.js`, `package.json`, `tests/helpers.mjs` were lightly edited, plus the local `server.py` and
  `test_server.py`. Record any further divergence in `UPSTREAM.md`.
- Keep the `speech-to-speech` pin in `pyproject.toml` and the commit in `UPSTREAM.md` in sync.
- Do not reintroduce training dependencies (trainers, dataset tooling, wandb). This repo is
  inference and demo only.
- Treat `web_demo/backend`, `web_demo/frontend`, and `src/tts` as legacy. Do not add features there
  and do not wire them into the current demo.
- Run `pytest` and `npm test --prefix web_demo/hf_interface` before finishing any change.
