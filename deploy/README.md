# Hosted ConvFill speech demo

Only Talker text goes to TTS. Browser PCM audio runs through Silero VAD,
remote STT, concurrent Reasoner/Talker generation, and remote TTS. The gateway
holds one browser session and resets ConvFill history on disconnect. Camera,
search, MCP, and RAG are disabled in the hosted normal-mode UI.

## Models and serving arrangement

The Reasoner is our existing **quantized Gemma 4 31B**:
`nvidia/Gemma-4-31B-IT-NVFP4` at
`4135a98a9b728a548947683219633b25682223ac`, derived from
`google/gemma-4-31B-it`. Keep the quantized checkpoint: replacing it with the
original weights is not required. Thinking is disabled per request; enabling
`reasoner.enable_thinking` is optional. The stream ignores reasoning fields and
filters serialized thought channels before sentence parsing.

The Talker is **`vysri/Qwen-0.6B-ConvFill`** at
`9195fc16f0ba56743d956f0fab5eed2386665aff`. Its tokenizer has
`<|im_start|>=151644`, `<|im_end|>=151645`, and `<sil>=151669`.
The client loads this exact tokenizer without adding or resizing tokens,
serializes the original user/assistant/knowledge prompt, and sends its token
IDs to `/v1/completions`. No serving chat template is involved. The server
stops on the fine-tuned EOS ID. Sentence fragments update the existing turn
state only after successful inference. Existing `mlx` and `hf` paths remain
available through their original frontend config.

The live smolagents vLLM version is `0.32.1rc1.dev36+ge68efc685`.
Both engines use image digest
`vllm/vllm-openai@sha256:1ff6716fe240a922d0d518b8884261e25b0c02eda8e2ce90888e364978249cad`.
[Current vLLM documentation](https://docs.vllm.ai/en/latest/usage/faq/)
still requires separate instances for independent models. LoRA aliases and
speculative draft models do not provide independent concurrent Talker/Reasoner
serving. No model swapping or shared generation lock is used.

| Service | smolagents resource | Hardware |
| --- | --- | --- |
| Reasoner | `reachy-s2s-llm-01` | RTX Pro 6000, 96 GB, AWS us-east-2 |
| Talker | `convfill-talker` | L4, 24 GB, AWS us-east-1 |
| STT | existing `reachy-s2s-stt-proxy` / `reachy-s2s-stt-01` | Qwen3-ASR 1.7B on A10G |
| TTS | existing `reachy-s2s-tts-proxy` / `reachy-s2s-tts-01` | Qwen3-TTS 1.7B CustomVoice on A10G |
| Browser / VAD / adapter | private `smolagents/convfill-speech-demo` Space | CPU |

The baseline reuses the existing supported Linux Qwen3-ASR and Qwen3-TTS
services. Parakeet TDT is an alternative local Linux STT backend; it is not
claimed as the tested hosted baseline. Faster Whisper and Pocket remain local
debug choices only. No HuggingFaceM4 resources are used.

The first new Talker allocation on A10G failed because AWS us-east-1 had no
capacity; L4 was used instead. Separate hosts isolate GPU contention and keep
both models resident, at the cost of network round trips. Same-host placement
and shared-GPU contention have not been benchmarked. Do not use default 90%
reservations for two processes on one GPU.

## Configuration and budgets

`configs/demo_mode/convfill_hosted_config.json` explicitly configures Reasoner
URL, served model name, credential environment variable, thinking, sampling,
connect/read/request deadlines, and the whole-turn deadline. Environment URL
and model overrides are documented in `.env.example`. Inference credentials
are optional for private-network vLLM and are never returned by `/api/config`.

The standalone `compose.yaml` uses an 8192-token Reasoner context, four active
sequences and a 90% GPU budget; the Talker uses 4096 tokens, two sequences,
160 requested output tokens and a 35% GPU budget. The existing shared test
Gemma endpoint retains its original 131072 context / 256 sequence / 90%
settings and MTP assistant. The demo requests at most 256 Reasoner tokens.
The gateway uses CPU only, so STT/TTS weights do not compete with either LLM.

Default timeouts: Reasoner connect 10s, idle read 15s, total request 45s;
Talker 10s / 15s / 30s; entire turn 90s; worker shutdown 3s. Cancellation
sets a per-turn event and closes active HTTP responses. A timed-out worker
that refuses to stop quarantines that pipeline; it cannot service another
turn with stale state. Stream EOF without `[DONE]`, HTTP failures, malformed
SSE and background-thread errors fail the turn and roll back its history.

## Start and stop

Python 3.11/3.12 and Node 24 are supported. For local development:

```bash
bash scripts/setup_demo.sh
# Configure URLs and server-side keys using deploy/.env.example.
# Export them in the shell; never commit a populated .env.
CONVFILL_CONFIG=configs/demo_mode/convfill_hosted_config.json \
HF_S2S_STT=openai HF_S2S_TTS=openai bash scripts/run_web_demo.sh
# Ctrl+C stops both processes.
```

For dedicated Linux GPUs plus the existing remote speech services:

```bash
cp deploy/.env.example deploy/.env
# Fill endpoint URLs/keys and install NVIDIA Container Toolkit.
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build -d
# Configure DEMO_HOST and run Caddy with deploy/Caddyfile on the gateway host.
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f demo
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

Compose does not expose inference ports publicly. Caddy terminates HTTPS and
proxies WebSockets; put the demo behind your organization's access control.
The browser derives `wss://<page-host>/v1/realtime` from the request origin.
Use one gateway worker: session admission is process-local. Trust forwarded
headers only from your ingress; the Space container trusts its HF ingress.

For the approved private Space, set `HF_TOKEN` locally and export the four
`CONVFILL_*_URL` values from the smolagents test deployment, then run:

```bash
.venv/bin/python deploy/hf_space.py
```

The script requires the exact approved private Space, checks privacy before
uploading, and stores endpoint keys in Space secrets. It excludes caches,
local environments and real `.env` files. Pause/restart the private Space:

```bash
.venv/bin/python -c "from huggingface_hub import HfApi; HfApi().pause_space('smolagents/convfill-speech-demo')"
.venv/bin/python -c "from huggingface_hub import HfApi; HfApi().restart_space('smolagents/convfill-speech-demo')"
```

Stop only the new Talker when retiring this demo with
`HfApi().pause_inference_endpoint('convfill-talker', namespace='smolagents')`;
resume it with `resume_inference_endpoint`. Keep the shared test Reasoner,
STT and TTS lifecycle under their existing deployment controller.

`/healthz` reports gateway liveness. `/readyz` checks the initialized pipeline
pool and both remote model services. vLLM health is `/health`, served model
identity is `/v1/models`. A second browser session is rejected while one is
active. Disconnect closes the downstream session; reconnect gets clean history.

## Validation and observability

```bash
.venv/bin/python -m pytest
npm test --prefix web_demo/hf_interface
PYTHONPATH=. .venv/bin/python scripts/validate_models.py
.venv/bin/python scripts/measure_gpu.py --seconds 60
# A generated 24 kHz mono PCM16 WAV exercises the real speech transport:
.venv/bin/python scripts/validate_realtime.py --audio /path/to/synthetic.wav
.venv/bin/python scripts/validate_bargein.py --audio /path/to/synthetic.wav
```

`validate_models.py` uses actual configured models and writes timings without
transcripts. GPU measurements use the smolagents OpenMetrics API and report
maximum sampled whole-replica memory, not an allocator high-water mark.
See `VALIDATION.md` for completed checks and limits.

Full LLM prompts, knowledge and transcripts are not logged by default.
`CONVFILL_LOG_CONTENT=1` explicitly enables ConvFill content diagnostics;
upstream transcript logging is also opt-in. Keep these disabled for a hosted
session. Do not add keys to command output, browser config, committed files,
or model URLs.

The delivery ledger observes output dequeued for dispatch and estimates a
playback clock from PCM duration. **It has no browser playback acknowledgement.**
Interrupted history uses a best-effort dispatched text prefix and interruption
marker. It must not be described as an exact transcript of what a person heard;
network delay, buffered playback and partial sentences can differ. Cancellation
and stale-generation filtering prevent future old-turn fragments from being
submitted, but already dispatched audio is dropped by the browser's barge-in
playback handling. Actual interruption results are recorded separately from
fake-model tests.

For controlled live faults, run `scripts.fault_proxy:app` on loopback port
18766 with `CONVFILL_REAL_REASONER_URL` and `CONVFILL_REASONER_API_KEY` set,
then run `PYTHONPATH=. .venv/bin/python scripts/validate_faults.py`. This
helper delays/interrupts real model streaming; it must never be exposed publicly.
