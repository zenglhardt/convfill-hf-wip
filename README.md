# Thinking While Speaking: Inference-Time Knowledge Transfer for Responsive and Intelligent Conversational Voice Agents

<p align="center">
  <a href="https://huggingface.co/datasets/zenglhardt/convfill-dataset"><img src="https://img.shields.io/badge/🤗%20HuggingFace-Dataset-yellow?style=flat" alt="HuggingFace Dataset" /></a>&nbsp;
  <a href="https://arxiv.org/abs/2511.07397"><img src="https://img.shields.io/badge/arXiv-2511.07397-b31b1b?style=flat&logo=arxiv" alt="arXiv" /></a>&nbsp;
  <a href="https://github.com/zenglhardt/convfill-dataset"><img src="https://img.shields.io/badge/GitHub-Dataset-blue?style=flat&logo=github" alt="GitHub Dataset" /></a>&nbsp;
  <a href="https://huggingface.co/collections/vysri/convfill-inference-time-knowledge-transfer"><img src="https://img.shields.io/badge/🤗%20HuggingFace-Collection-yellow?style=flat" alt="HuggingFace Collection" /></a>
</p>

**ConvFill** is a system for building voice agents that respond instantly *and* answer accurately — two goals that are normally at odds. It pairs a small, fast language model running locally with a large cloud model that does the heavy reasoning in the background, so the agent can start talking right away and fill in well-grounded answers as they become available. This repository contains the full system, a live voice demo, and seven ready-to-use models.

<p align="center">
  <img src="assets/teaser.png" width="300" alt="Teaser" />
</p>

## How it works

The capabilities that make large language models useful — multi-step reasoning, searching documents, calling tools — take seconds to run, but natural conversation needs a reply within a fraction of a second. ConvFill resolves this tension by splitting the work across two models:

- A **Talker** — a *small language model* (SLM) of 135M–1.7B parameters, small enough to run locally on a laptop or phone. The user only ever talks to the Talker. It begins responding immediately, producing natural filler such as *"Let me look that up for you…"* to cover the wait, then weaves in real information the moment it arrives.
- A **Reasoner** — a large cloud model (for example Claude, GPT, or Gemini) that works in the background on the slow parts: reasoning, retrieval, and tool calls. It streams concise knowledge to the Talker as it goes.

Because the user interacts only with the fast local Talker, the agent stays responsive in real time while approaching the accuracy of the cloud model used on its own. We call this task *conversational infill*; the [paper](https://arxiv.org/abs/2511.07397) has the full story, including a 290k-example dataset, results across seven models, and a user study.

> Note: some configuration files and directories still use the earlier `frontend`/`backend` names for the Talker and Reasoner, respectively.

## Highlights

- 💡 **A new task: conversational infill.** A small on-device model carries the conversation while a large cloud model supplies knowledge in the background — keeping voice agents responsive without giving up the capabilities of frontier models. The full formulation, evaluation, and a user study are in the [paper](https://arxiv.org/abs/2511.07397).
- 📊 **A dataset built for the task.** The [ConvFill dataset](https://huggingface.co/datasets/zenglhardt/convfill-dataset) ([GitHub](https://github.com/zenglhardt/convfill-dataset)) contains 290k validated training examples across six domains, produced and verified by our synthetic data pipeline.
- 🤗 **Seven ready-to-use models.** Fine-tuned Talkers spanning the Qwen, Llama, Gemma, and SmolLM families (135M–1.7B parameters) are published in the [HuggingFace collection](https://huggingface.co/collections/vysri/convfill-inference-time-knowledge-transfer).
- 🔌 **Model-agnostic and modular.** Pair any of the released Talkers with any frontier model (Claude, OpenAI, or Gemini) as the Reasoner — swapping the Reasoner needs no retraining.
- ⚡ **Runs on consumer hardware.** Talkers are quantized for laptops and Apple Silicon (via MLX); the system is evaluated on a MacBook with an M2 chip.

## What's in this repo

- **A live voice demo** — an end-to-end, browser-based speech-to-speech agent (speech recognition → `Talker` + `Reasoner` → text-to-speech), with optional document retrieval (RAG) and external tool use over [MCP](https://modelcontextprotocol.io).
- **The full inference stack** — the code that runs the `Talker` + `Reasoner` system at inference time, including the conversation engine, knowledge streaming, and the RAG and MCP integrations.

## Where to go next

- [Python Environment Setup](#python-environment-setup) — create the virtual environment and install the demo.
- [Live Demo Instructions](#live-demo-instructions) — run the Hugging Face realtime voice demo with Claude Haiku.
- [Details for Developers or Tinkerers](#details-for-developers-or-tinkerers) — code/config structure, adding models, and advanced demo setup (RAG, MCP, custom Reasoner APIs).
- [Citation & License](#citation--license) — how to cite ConvFill and licensing.

# Python Environment Setup

The demo runs in a plain Python virtual environment (Python 3.11 or 3.12) plus
Node.js 24 for the browser interface. No Conda is required.

One-shot setup from the repository root:

```bash
bash scripts/setup_demo.sh
```

The script creates `.venv`, installs this project in editable mode together with
the pinned Hugging Face [speech-to-speech](https://github.com/huggingface/speech-to-speech)
package, downloads the NLTK assets the speech pipeline needs, and runs `npm ci`
for the browser interface. It is safe to re-run. Set `PYTHON=/path/to/python3.12`
to pick a specific interpreter.

The manual equivalent is:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m nltk.downloader -d .venv/share/nltk_data punkt_tab averaged_perceptron_tagger_eng
npm ci --prefix web_demo/hf_interface
```

Optional extras add the non-default task modes and providers:

| Extra | Enables |
|-------|---------|
| `rag` | FAISS retrieval (`rag` task mode) |
| `mcp` | Tool use over [MCP](https://modelcontextprotocol.io) (`mcp` task mode) |
| `gemini` | Gemini as the `Reasoner` |
| `dev` | `pytest` for the adapter and interface tests |

For example, `python -m pip install -e ".[dev,rag,mcp]"`.

The browser interface expects Node.js 24 (`.nvmrc`). With `nvm`, run `nvm install`
then `nvm use` from the repository root.

The first launch downloads the local STT, TTS, and `Talker` models from the
Hugging Face Hub. On Apple Silicon the speech package automatically selects its
MLX implementations. See the upstream
[installation notes](https://github.com/huggingface/speech-to-speech#installation)
for Linux/CUDA-specific Qwen3-TTS wheels.

# Live Demo Instructions

The browser demo is built on Hugging Face's realtime
[speech-to-speech](https://github.com/huggingface/speech-to-speech) interface and
audio pipeline:

1. Silero VAD detects turns.
2. Parakeet TDT transcribes speech locally.
3. Claude Haiku streams concise knowledge as the background `Reasoner`.
4. The local, fine-tuned ConvFill `Talker` turns each knowledge update (or a
   `<sil>` filler signal) into the phrase the user actually hears.
5. Qwen3-TTS synthesizes and streams each Talker phrase locally.

The browser sends and receives 24 kHz PCM audio over the project's
OpenAI-Realtime-compatible WebSocket protocol. An in-repo Hugging Face backend
adapter reuses `ConvFillSystem`; it does not send STT output directly to Claude.

## API keys

The launcher requires `ANTHROPIC_API_KEY` in the environment. No key is stored
in the repository. Export it in the shell you launch from, ideally using a
secure method such as those in OpenAI's
[API key safety guidance](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety):

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

`rag` mode additionally needs `OPENAI_API_KEY` (query embeddings), and a Gemini
`Reasoner` needs `GEMINI_API_KEY`.

## Starting the demo

```bash
bash scripts/run_web_demo.sh
```

The launcher uses `.venv` automatically. It also honors an already activated
virtual environment, or an explicit interpreter in `PYTHON_BIN`.

Open `http://127.0.0.1:7860` in Chrome or Edge, click the orb, and allow
microphone access. The launcher binds both services to loopback only and stops
them together on Ctrl+C.

Defaults can be overridden without editing code:

```bash
CONVFILL_CONFIG=configs/demo_mode/convfill_simple_config.json \
CONVFILL_MODE=normal \
HF_S2S_STT=parakeet-tdt \
HF_S2S_TTS=qwen3 \
bash scripts/run_web_demo.sh
```

The interface source and its Apache-2.0 attribution are documented in
`web_demo/hf_interface/UPSTREAM.md`.

# Details for Developers or Tinkerers

## Available `Talker` Models

These are the configs in `configs/convfill_frontend_configs`, each pointing at a released fine-tuned `Talker` and the HuggingFace base model it was trained from. Reference one from the top-level `frontend_model_config_path` in `configs/demo_mode/*.json` to select the `Talker` the demo runs.

| Config | HuggingFace model |
|--------|-------------------|
| `convfill_smollmIT_135M_nd.json` | `HuggingFaceTB/SmolLM2-135M-Instruct` |
| `convfill_smollmIT_360M_nd.json` | `HuggingFaceTB/SmolLM2-360M-Instruct` |
| `convfill_smollmIT_1.7B_nd.json` | `HuggingFaceTB/SmolLM2-1.7B-Instruct` |
| `convfill_gemma3IT_270M_nd.json` | `google/gemma-3-270m-it` |
| `convfill_gemma3IT_1B_nd.json` | `google/gemma-3-1b-it` |
| `convfill_llama3.2IT_1B_nd.json` | `meta-llama/Llama-3.2-1B-Instruct` |
| `convfill_qwen3_0.6B_nd.json` | `Qwen/Qwen3-0.6B` |

These are the models we have tested as ConvFill `Talker`s.

## Inference Code Structure

* `src/inference/convfill_stack` contains the full ConvFill stack — the small local ```Talker``` model running alongside a large ```Reasoner``` model.
* `src/inference/convfill_stack/run_convfill.py` defines the original system configuration and core classes (`ConvFillConfig`, `ConvFillSystem`).
* `src/inference/convfill_stack/convfill_backend_multi.py` drives the `Reasoner` across the `normal`, `rag`, and `mcp` task modes.
* `src/inference/shared` contains components shared across stacks — the conversation engine (`convfill_engine.py`), dialogue/turn state managers, and the MCP client (`mcp_client.py`).
* `src/inference/single_model_stack` contains library code for running a single model on its own — `large_model_only/` (cloud `Reasoner`) and `small_model_only/` (local `Talker`). These are used by the engine; they are not run directly.
* `src/inference/rag` contains the retrieval module (`retreive.py`, exposing `RunRAG`) plus the committed FAISS index (`uw_phd.index`) and chunk store (`uw_chunks.json`) used in `rag` task mode.
* `web_demo/hf_interface` contains the active Hugging Face realtime browser interface and its small FastAPI static host. `web_demo/backend` and `web_demo/frontend` retain the previous custom demo for reference.


## Configs

* `configs/convfill_frontend_configs` — `Talker` (local) model inference configs, one per model size (see the table above).
* `configs/demo_mode` — runtime configs consumed by both the ConvFill engine and the Hugging Face realtime adapter. They select the Talker, Reasoner, prompt, and task mode.
* `configs/backend_model_configs` — available cloud `Reasoner` model names per provider (`claude/`, `openai/`, `gemini/`).
* `configs/convfill_backend_prompts` — `Reasoner` prompt templates for the ConvFill stack (the `*_conv.txt` files).
* `configs/backend_only_prompts` — prompt templates for `Reasoner`-only single-model runs.

### Adding New Model(s)

Each `Talker` config file (e.g., `convfill_gemma3IT_270M_nd.json`) specifies the model and its inference weight paths. Model parameters for inference can be adjusted by editing these files. To add a new model, copy one of the existing configs and update the metadata to match the new model. 

The key fields for inference are:

| Field | Description |
|-------|-------------|
| `model_name` | HuggingFace model ID (used for downloading base weights) |
| `backend` | Inference backend: `"hf"` (HuggingFace/PyTorch) or `"mlx"` (MLX/Apple Silicon) |
| `convfill_hf_pretrained_path` | HuggingFace model ID or local path to ConvFill-trained weights for HuggingFace backend (bf16 precision) |
| `convfill_hf_mlx_pretrained_path` | HuggingFace model ID or local path to ConvFill-trained weights for MLX backend (int8 quantized) |

The weight paths can be either HuggingFace model IDs (e.g., `"vysri/gemma3-270m-IT-ConvFill"`) or local filesystem paths (e.g., `"/path/to/local/weights"`).

## Advanced Demo Setup

The default `normal` task mode needs no extra setup. Select another mode with
`CONVFILL_MODE=rag` or `CONVFILL_MODE=mcp` when launching, together with
`CONVFILL_CONFIG=configs/demo_mode/convfill_full_config.json`.

### RAG mode

RAG mode retrieves context from a vector index before each `Reasoner` response.
Install the `rag` extra and export `OPENAI_API_KEY`, since queries are embedded
with OpenAI's `text-embedding-3-large` even when the `Reasoner` is Claude. The
retrieval assets are committed under `src/inference/rag/` (`uw_phd.index` and
`uw_chunks.json`), and the local reranker downloads on first use.

### MCP mode

MCP mode lets the `Reasoner` call tools exposed by external
[Model Context Protocol](https://modelcontextprotocol.io) servers. Install the
`mcp` extra, run the servers yourself, and list them under
`modes.mcp.task_specific_config.mcp_servers` in the full config. The checked-in
example launches the [`mail-mcp`](https://github.com/tecnologicachile/mail-mcp)
server through Docker:

```json
"mcp_servers": [
  {
    "name": "mail",
    "transport": "stdio",
    "command": "docker",
    "args": ["exec", "-i", "gmail-mcp", "mail-mcp"],
    "env": {}
  }
]
```

`max_tool_iterations` caps how many tool calls the `Reasoner` may chain per turn.

### Customizing the `Reasoner`

Set `backend_model_name` and `backend_model_mode` at the top level of the demo
config. Available names per provider live in
`configs/backend_model_configs/<provider>/model_names.json`:

| Provider (`backend_model_mode`) | Model names |
|---------------------------------|-------------|
| `claude` | `claude-haiku-4-5-20251001`, `claude-opus-4-7`, `claude-sonnet-4-6` |
| `openai` | `gpt-4o`, `gpt-4-turbo`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt5.4-nano` |
| `gemini` | `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `gemini-3.1-pro-preview` |

Gemini requires the `gemini` extra and `GEMINI_API_KEY`; OpenAI requires
`OPENAI_API_KEY`.

## Realtime ConvFill Adapter

`web_demo/hf_convfill` registers a `convfill` LLM-stage backend with the pinned
Hugging Face speech package. That adapter passes final Parakeet transcripts into
the existing `ConvFillSystem`, forwards only Talker phrases to Qwen3-TTS, and
uses Hugging Face's response-playing signal to preserve ConvFill's `<sil>`
filler scheduling.

Both demo configs default the Reasoner to `claude-haiku-4-5-20251001`. The
previous FastAPI/React demo remains under `web_demo/backend` and
`web_demo/frontend` for comparison, but the active interface and transport are
the Hugging Face versions.

# Citation & License

If you use ConvFill, the dataset, or the released models in your work, please cite:

```bibtex
@misc{srinivas2026thinkingspeakinginferencetimeknowledge,
      title={Thinking While Speaking: Inference-Time Knowledge Transfer for Responsive and Intelligent Conversational Voice Agents},
      author={Vidya Srinivas and Zachary Englhardt and Vikram Iyer and Shwetak Patel},
      year={2026},
      eprint={2511.07397},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2511.07397},
}
```

ConvFill code is released under the MIT License — see [`LICENSE`](LICENSE). The vendored Hugging Face browser interface is Apache-2.0; see [`web_demo/hf_interface/UPSTREAM.md`](web_demo/hf_interface/UPSTREAM.md) and its retained license.
