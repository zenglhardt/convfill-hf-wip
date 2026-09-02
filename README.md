# Thinking While Speaking: Inference-Time Knowledge Transfer for Responsive and Intelligent Conversational Voice Agents

<p align="center">
  <a href="https://huggingface.co/datasets/zenglhardt/convfill-dataset"><img src="https://img.shields.io/badge/🤗%20HuggingFace-Dataset-yellow?style=flat" alt="HuggingFace Dataset" /></a>&nbsp;
  <a href="https://arxiv.org/abs/2511.07397"><img src="https://img.shields.io/badge/arXiv-2511.07397-b31b1b?style=flat&logo=arxiv" alt="arXiv" /></a>&nbsp;
  <a href="https://github.com/zenglhardt/convfill-dataset"><img src="https://img.shields.io/badge/GitHub-Dataset-blue?style=flat&logo=github" alt="GitHub Dataset" /></a>&nbsp;
  <a href="https://huggingface.co/collections/vysri/convfill-inference-time-knowledge-transfer"><img src="https://img.shields.io/badge/🤗%20HuggingFace-Collection-yellow?style=flat" alt="HuggingFace Collection" /></a>
</p>

**ConvFill** is a system for building voice agents that respond instantly *and* answer accurately — two goals that are normally at odds. It pairs a small, fast language model running locally with a large cloud model that does the heavy reasoning in the background, so the agent can start talking right away and fill in well-grounded answers as they become available. This repository contains the full system, a live voice demo, seven ready-to-use models, and everything needed to train your own.

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
- 🔌 **Model-agnostic and modular.** Train any compatible small model as a Talker, and pair it with any frontier model (Claude, OpenAI, or Gemini) as the Reasoner — swapping the Reasoner needs no retraining.
- ⚡ **Runs on consumer hardware.** Talkers are quantized for laptops and Apple Silicon (via MLX); the system is evaluated on a MacBook with an M2 chip.

## What's in this repo

- **A live voice demo** — an end-to-end, browser-based speech-to-speech agent (speech recognition → `Talker` + `Reasoner` → text-to-speech), with optional document retrieval (RAG) and external tool use over [MCP](https://modelcontextprotocol.io).
- **The full inference stack** — the code that runs the `Talker` + `Reasoner` system at inference time, including the conversation engine, knowledge streaming, and the RAG and MCP integrations.
- **A training pipeline** — scripts and configs to fine-tune your own `Talker` model(s), plus tooling to preprocess raw conversations into the training format.

## Where to go next

- [Python Environment Setup](#python-environment-setup) — install dependencies for training and inference.
- [Live Demo Instructions](#live-demo-instructions) — run the Hugging Face realtime voice demo with Claude Haiku.
- [Training a `Talker` Model](#training-a-talker-model) — prepare data, fine-tune, and the list of supported models.
- [Details for Developers or Tinkerers](#details-for-developers-or-tinkerers) — code/config structure, adding models, and advanced demo setup (RAG, MCP, custom Reasoner APIs).
- [Citation & License](#citation--license) — how to cite ConvFill and licensing.

# Python Environment Setup

Run the following commands from the root of the repository to get the necessary packages set up. ConvFill expects Python 3.11. Use either a Conda environment or a virtual environment. This environment works for training and the original ConvFill inference stack. The realtime speech demo uses a separate environment because Hugging Face's speech package owns a newer set of audio/model dependency pins.

```bash
# Option A: create and activate a Conda environment
conda create -n convfill python=3.11
conda activate convfill
```
OR
```bash
# Option B: create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate
```
After creating/activating your environment, run:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

# Live Demo Instructions

On this branch, the browser demo is replaced by Hugging Face's realtime
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

## Speech demo environment

Create the dedicated `hf-demo` Conda environment from the checked-in definition.
This keeps the speech package's Torch, Transformers, MLX, and audio pins separate
from the `convfill` training environment:

```bash
conda env create -f web_demo/environment.yml
conda activate hf-demo
npm ci --prefix web_demo/hf_interface
```

After the YAML changes, update the existing environment with:

```bash
conda env update -n hf-demo -f web_demo/environment.yml --prune
```

The first launch downloads the selected local STT and TTS models from the
Hugging Face Hub. On Apple Silicon, the package automatically selects its MLX
implementations. See the upstream
[installation notes](https://github.com/huggingface/speech-to-speech#installation)
for Linux/CUDA-specific Qwen3-TTS wheels.

## API key

The launcher requires `ANTHROPIC_API_KEY` in the environment. It never reads
`~/.secret` and no key is stored in the repository. If `~/.secret` is a
shell-compatible file that exports the key, load it manually before starting:

```bash
conda activate hf-demo
source ~/.secret
test -n "$ANTHROPIC_API_KEY"
```

Alternatively, export `ANTHROPIC_API_KEY` directly in the current shell.

## Starting the demo

```bash
conda activate hf-demo
bash scripts/run_web_demo.sh
```

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

# Training a `Talker` Model

## Prepare the dataset
`dataset_gen/dataset_preprocess.py` converts a folder of raw conversations (from the synthetic data pipeline) into the single formatted JSONL file used to train the `Talker` models — the same format as the examples in `data`.

It reads **every file** in `--base_data_dir`, where each file is JSONL and each line is one conversation of the form `{"conversation": [turn, turn, ...]}`. Each turn holds the user message plus *lists* of paired thought/response phrases (the keys are configurable via the `--*_tag` flags). The script validates each turn (it skips conversations with missing fields, empty turns, or mismatched thought/response list lengths), unrolls every turn into its sequence of streaming phrases, and appends the formatted turns to a single output JSONL.

The easiest way to run it is the wrapper script `scripts/data_preprocess.sh`, which invokes `dataset_preprocess.py` with our standard arguments. Edit the input/output paths in that script to point at your own data, then run it from inside `scripts/` (its paths are relative):

```bash
cd scripts
bash data_preprocess.sh
```

The script is just the following call — set `--base_data_dir` to your folder of raw JSONL files and `--output_path` to where you want the formatted dataset:

```bash
python3 ../dataset_gen/dataset_preprocess.py \
  --user_tag user \
  --thoughts_tag thoughts \
  --responder_tag response \
  --base_data_dir <your raw data folder> \
  --output_path <your output .jsonl> \
  --include_history
```

Arguments:

| Flag | Meaning |
|------|---------|
| `--base_data_dir` | Folder whose files (each JSONL) are all read as input |
| `--output_path` | Output JSONL path (created/overwritten, then appended to) |
| `--user_tag` | Per-turn key holding the user message (we use `user`) |
| `--thoughts_tag` | Per-turn key holding the list of thought phrases (we use `thoughts`) |
| `--responder_tag` | Per-turn key holding the list of response phrases (we use `response`) |
| `--include_history` | When set, each phrase also carries the running text of the turn's previous responses |

## Model Fine-Tuning

`src/training/finetune_convfill.py` finetunes a HuggingFace model for the ConvFill task using a config from `configs/convfill_frontend_configs`. Run from the repo root:

```bash
python src/training/finetune_convfill.py \
  --config configs/convfill_frontend_configs/convfill_gemma3IT_270M_nd.json \
  --run_name my_experiment \
  --output_dir ./runs
```

| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--config` | yes | — | Path to a `Talker` training config JSON |
| `--run_name` | yes | — | Name for this run (used for logging/checkpoints) |
| `--output_dir` | no | `./runs` | Base directory for outputs |
| `--resume_from_scratch` | no | off | Ignore `latest.ckpt` and start fresh |

The easiest way to run it is the wrapper script `scripts/train_convfill.sh`:

```bash
bash scripts/train_convfill.sh
```

Multi-GPU training is handled automatically through Lightning's DDP when multiple GPUs are available, they will be auto-detected in the current configuration; CPU vs GPU is set by the `"platform"` field in the config.

## Supported Local Models

These are the configs in `configs/convfill_frontend_configs`, each pointing at a HuggingFace model. Pass one to `--config` when training, or reference it from `configs/demo_mode/convfill_overall_config.json` under the top-level `frontend_model_config_path` for inference.

| Config | HuggingFace model |
|--------|-------------------|
| `convfill_smollmIT_135M_nd.json` | `HuggingFaceTB/SmolLM2-135M-Instruct` |
| `convfill_smollmIT_360M_nd.json` | `HuggingFaceTB/SmolLM2-360M-Instruct` |
| `convfill_smollmIT_1.7B_nd.json` | `HuggingFaceTB/SmolLM2-1.7B-Instruct` |
| `convfill_gemma3IT_270M_nd.json` | `google/gemma-3-270m-it` |
| `convfill_gemma3IT_1B_nd.json` | `google/gemma-3-1b-it` |
| `convfill_llama3.2IT_1B_nd.json` | `meta-llama/Llama-3.2-1B-Instruct` |
| `convfill_qwen3_0.6B_nd.json` | `Qwen/Qwen3-0.6B` |

These are the models we have tested as ConvFill `Talker`s, but they are not the only options — you can train any compatible HuggingFace model as a `Talker` using our training scripts and dataset (see [Training a `Talker` Model](#training-a-talker-model)).

# Details for Developers or Tinkerers

## Training Code Structure

* `configs` contains the model training and inference configurations for ConvFill `Talker` models
* `data` contains clean JSONL training data that is already formatted and can be used to train the `Talker` models
* `dataset` contains the torch Dataset and Collators used in `Talker` model training
* `dataset_gen` contains the data preprocessing script needed to take a folder of raw JSONL data generated by our synthetic data pipeline and convert it to a format like the example in `data`. You can use this to preprocess your own custom dataset
* `src/training` contains files to train the `Talker` models
* `src/training/convfill_pl_module.py` contains the code for a Lightning Module that is used to structure training and validation steps
* `src/training/finetune_convfill.py` contains the code to finetune an existing model for the ConvFill task. It supports logging through WandB and accepts configuration files of the form in `configs`. It has been tested for multi-GPU training and integrates DDP through Lightning's trainer.
* `src/training/metrics.py` contains metrics for logging. You can use this file to add your own scalar metric logging.

## Inference Code Structure

* `src/inference/convfill_stack` contains the full ConvFill stack — the small local ```Talker``` model running alongside a large ```Reasoner``` model.
* `src/inference/convfill_stack/run_convfill.py` defines the original system configuration and core classes (`ConvFillConfig`, `ConvFillSystem`).
* `src/inference/convfill_stack/convfill_backend_multi.py` drives the `Reasoner` across the `normal`, `rag`, and `mcp` task modes.
* `src/inference/shared` contains components shared across stacks — the conversation engine (`convfill_engine.py`), dialogue/turn state managers, and the MCP client (`mcp_client.py`).
* `src/inference/single_model_stack` contains library code for running a single model on its own — `large_model_only/` (cloud `Reasoner`) and `small_model_only/` (local `Talker`). These are used by the engine; they are not run directly.
* `src/inference/rag` contains the retrieval module (`retreive.py`, exposing `RunRAG`) plus the committed FAISS index (`uw_phd.index`) and chunk store (`uw_chunks.json`) used in `rag` task mode.
* `web_demo/hf_interface` contains the active Hugging Face realtime browser interface and its small FastAPI static host. `web_demo/backend` and `web_demo/frontend` retain the previous custom demo for reference.


## Configs

* `configs/convfill_frontend_configs` — `Talker` (local) model training/inference configs, one per model size (see the table below).
* `configs/demo_mode` — runtime configs consumed by both the ConvFill engine and the Hugging Face realtime adapter. They select the Talker, Reasoner, prompt, and task mode.
* `configs/backend_model_configs` — available cloud `Reasoner` model names per provider (`claude/`, `openai/`, `gemini/`).
* `configs/convfill_backend_prompts` — `Reasoner` prompt templates for the ConvFill stack (the `*_conv.txt` files).
* `configs/backend_only_prompts` — prompt templates for `Reasoner`-only single-model runs.

### Adding New Model(s)

Each `Talker` config file (e.g., `convfill_gemma3IT_270M_nd.json`) specifies the model, training hyperparameters, and inference weight paths. Model parameters for training and inference can be adjusted by editing these files. To add a new model, copy one of the existing configs and update the metadata to match the new model. 

The key fields for inference are:

| Field | Description |
|-------|-------------|
| `model_name` | HuggingFace model ID (used for downloading base weights) |
| `backend` | Inference backend: `"hf"` (HuggingFace/PyTorch) or `"mlx"` (MLX/Apple Silicon) |
| `convfill_hf_pretrained_path` | HuggingFace model ID or local path to ConvFill-trained weights for HuggingFace backend (bf16 precision) |
| `convfill_hf_mlx_pretrained_path` | HuggingFace model ID or local path to ConvFill-trained weights for MLX backend (int8 quantized) |

The weight paths can be either HuggingFace model IDs (e.g., `"vysri/gemma3-270m-IT-ConvFill"`) or local filesystem paths (e.g., `"/path/to/local/weights"`).

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
