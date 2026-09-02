#!/usr/bin/env bash
# Build int8 (Q8_0) GGUF versions of the released ConvFill Talker models.
#
# Converts the *original* fine-tuned bf16 weights straight to Q8_0 GGUF with
# llama.cpp's convert_hf_to_gguf.py. The MLX int8 checkpoints are never used as
# an input: re-quantizing an already-quantized model compounds the error.
#
# Nothing here touches the demo. It does not modify .venv, the configs, or any
# inference code -- it only writes GGUF files you can upload yourself.
#
#   bash scripts/quantize_gguf.sh                 # all seven models
#   bash scripts/quantize_gguf.sh qwen3-0.6b      # just one (repeatable)
#   bash scripts/quantize_gguf.sh --list          # show the model keys
#
# Environment overrides:
#   GGUF_WORK_DIR   where everything lands       (default: <repo>/ggufs)
#   PYTHON          interpreter for the tool env (default: python3.12/3.11)
#   GGUF_OUTTYPE    quantization type            (default: q8_0)
#   LLAMA_CPP_REF   llama.cpp commit to pin      (default: the tested one)
#   FORCE=1         re-convert even if the .gguf already exists
#
# Needs ~12 GB free for the downloaded bf16 weights plus ~6 GB of output.
# Re-running is safe: downloads, the tool env, and finished models are reused.
#
# ---------------------------------------------------------------------------
# STATUS: work in progress.
#
# Verified end to end on smollm-135m only (llama architecture): downloads,
# converts, and the resulting 144 MB Q8_0 file passes the checks below --
# <sil> control token present, chat template present, 49153 vocab tokens.
#
# NOT yet run for the other six models. The remaining architectures (qwen3,
# gemma3) exercise different set_vocab paths in the converter and have not been
# exercised here, so treat the first run of those as unverified. Everything
# shared -- llama.cpp checkout, tool venv, download, tokenizer normalization,
# Q8_0 conversion, verification, model card -- is the same code path that the
# 135M run took, so the risk is per-architecture vocab handling rather than
# the plumbing.
#
# Known quirk worth remembering: the released checkpoints were saved by
# transformers v5 and write "extra_special_tokens" as a list. llama.cpp pins
# transformers 4.57, which requires a mapping and crashes on the list. The
# download step rewrites that key in the local copy; see the note there.
#
# Also note configs/convfill_frontend_configs/convfill_smollmIT_135M_nd.json
# points at the SmolLM 1.7B ConvFill weights, not the 135M ones. That looks
# like a pre-existing typo. It is unrelated to this script (which reads the
# model list below, not the configs) and has been left alone.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WORK_DIR="${GGUF_WORK_DIR:-$REPO_ROOT/ggufs}"
TOOL_DIR="$WORK_DIR/tools"
LLAMA_DIR="$TOOL_DIR/llama.cpp"
VENV_DIR="$TOOL_DIR/venv"
SRC_DIR="$WORK_DIR/hf_source"
OUT_DIR="$WORK_DIR/out"

OUTTYPE="${GGUF_OUTTYPE:-q8_0}"
# Upper-cased tag used in file names, e.g. q8_0 -> Q8_0.
OUTTAG="$(printf '%s' "$OUTTYPE" | tr '[:lower:]' '[:upper:]')"
# Suffix for the output directory, mirroring the "_mlx_q8" naming already used
# for the MLX checkpoints on the Hub.
OUTSUFFIX="_gguf_$(printf '%s' "$OUTTYPE" | tr '[:upper:]' '[:lower:]' | sed 's/_0$//')"

# Pinned so a future upstream refactor cannot silently change the output.
LLAMA_CPP_REF="${LLAMA_CPP_REF:-b96806d96061049a5b574269b049bf6241d63d46}"

# key|huggingface repo id -- the seven released fine-tuned Talkers.
MODELS='qwen3-0.6b|vysri/Qwen-0.6B-ConvFill
smollm-135m|vysri/SmolLM135M-IT-ConvFill
smollm-360m|vysri/SmolLM360M-IT-ConvFill
smollm-1.7b|vysri/SmolLM1.7B-IT-ConvFill
gemma3-270m|vysri/gemma3-270m-IT-ConvFill
gemma3-1b|vysri/gemma3-1b-IT-ConvFill
llama3.2-1b|vysri/Llama-3.2-1B-IT-ConvFill'

list_models() {
  printf '%-14s %s\n' "KEY" "HUGGINGFACE MODEL"
  printf '%s\n' "$MODELS" | while IFS='|' read -r key repo; do
    printf '%-14s %s\n' "$key" "$repo"
  done
}

repo_for_key() {
  # awk rather than a read loop: it always exits 0, so a miss on the last row
  # cannot trip "set -e" at the call site.
  printf '%s\n' "$MODELS" | awk -F'|' -v want="$1" '$1 == want { print $2 }'
}

# --- argument handling -------------------------------------------------------
SELECTED=""
for arg in "$@"; do
  case "$arg" in
    --list|-l)
      list_models
      exit 0
      ;;
    -h|--help)
      sed -n '2,49p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*)
      echo "[error] unknown option: $arg" >&2
      exit 1
      ;;
    *)
      if [ -z "$(repo_for_key "$arg")" ]; then
        echo "[error] unknown model key: $arg" >&2
        echo "Known keys:" >&2
        list_models >&2
        exit 1
      fi
      SELECTED="$SELECTED$arg
"
      ;;
  esac
done

if [ -n "$SELECTED" ]; then
  TARGETS="$(printf '%s' "$SELECTED")"
else
  TARGETS="$(printf '%s\n' "$MODELS" | cut -d'|' -f1)"
fi

# --- interpreter -------------------------------------------------------------
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
  echo "[error] No suitable Python interpreter found (need 3.11 or 3.12)." >&2
  echo "  brew install python@3.12" >&2
  echo "  PYTHON=/opt/homebrew/bin/python3.12 bash scripts/quantize_gguf.sh" >&2
  exit 1
fi

command -v git >/dev/null 2>&1 || { echo "[error] git is required." >&2; exit 1; }

echo "[gguf] work dir: $WORK_DIR"
echo "[gguf] python:   $PYTHON_CMD"
echo "[gguf] outtype:  $OUTTYPE"
mkdir -p "$TOOL_DIR" "$SRC_DIR" "$OUT_DIR"

# --- llama.cpp ---------------------------------------------------------------
# Only the Python converter is used, so there is no C++ build step. Q8_0 is
# produced directly by convert_hf_to_gguf.py.
if [ ! -d "$LLAMA_DIR/.git" ]; then
  echo "[gguf] fetching llama.cpp @ ${LLAMA_CPP_REF:0:12}"
  rm -rf "$LLAMA_DIR"
  mkdir -p "$LLAMA_DIR"
  git -C "$LLAMA_DIR" init -q
  git -C "$LLAMA_DIR" remote add origin https://github.com/ggml-org/llama.cpp.git
fi

if [ "$(git -C "$LLAMA_DIR" rev-parse HEAD 2>/dev/null || true)" != "$LLAMA_CPP_REF" ]; then
  echo "[gguf] checking out llama.cpp ${LLAMA_CPP_REF:0:12}"
  git -C "$LLAMA_DIR" fetch -q --depth 1 origin "$LLAMA_CPP_REF"
  git -C "$LLAMA_DIR" checkout -q FETCH_HEAD
else
  echo "[gguf] llama.cpp already at ${LLAMA_CPP_REF:0:12}"
fi

# --- conversion environment --------------------------------------------------
# Deliberately separate from the demo's .venv: llama.cpp pins numpy 1.26 and
# transformers 4.57, both older than what the demo needs.
STAMP="$VENV_DIR/.installed-$LLAMA_CPP_REF"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[gguf] creating conversion venv at $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"

if [ ! -f "$STAMP" ]; then
  echo "[gguf] installing conversion dependencies (this pulls torch; one time)"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet \
    -r "$LLAMA_DIR/requirements/requirements-convert_hf_to_gguf.txt" \
    "huggingface_hub>=0.34"
  touch "$STAMP"
else
  echo "[gguf] conversion venv ready"
fi

# --- convert -----------------------------------------------------------------
CONVERTED=""
for key in $TARGETS; do
  repo="$(repo_for_key "$key")"
  name="${repo#*/}"
  model_src="$SRC_DIR/$name"
  model_out="$OUT_DIR/${name}${OUTSUFFIX}"
  gguf_file="$model_out/${name}-${OUTTAG}.gguf"

  echo
  echo "=== $key  ($repo)"

  if [ -f "$gguf_file" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "[gguf] already built: $gguf_file (FORCE=1 to rebuild)"
    CONVERTED="$CONVERTED$gguf_file
"
    continue
  fi

  echo "[gguf] downloading original bf16 weights"
  REPO_ID="$repo" DEST="$model_src" "$VENV_PY" - <<'PY'
import os
import json
import re
from pathlib import Path

from huggingface_hub import snapshot_download

dest = Path(os.environ["DEST"])
snapshot_download(
    repo_id=os.environ["REPO_ID"],
    local_dir=str(dest),
    # Everything the converter reads: weights, config, tokenizer, chat template.
    allow_patterns=["*.safetensors", "*.json", "*.jinja", "*.model", "*.txt"],
    # A training-time snapshot of the config that must not shadow config.json.
    ignore_patterns=["config.snapshot.json"],
)

# The released checkpoints were saved by transformers v5, which writes
# "extra_special_tokens" as a list. llama.cpp pins transformers 4.57, where the
# key must be a mapping -- the list form crashes AutoTokenizer before the vocab
# is ever read. Rewrite it in our local copy only; <sil> itself is declared in
# tokenizer.json and is not touched here. Idempotent, so re-runs are fine.
cfg_path = dest / "tokenizer_config.json"
if cfg_path.is_file():
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    extra = cfg.get("extra_special_tokens")
    if isinstance(extra, list):
        mapping = {}
        for i, tok in enumerate(extra):
            key = re.sub(r"\W+", "_", str(tok).strip("<>|")).strip("_").lower()
            mapping[key or f"extra_special_token_{i}"] = tok
        cfg["extra_special_tokens"] = mapping
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print(f"[prep] normalized extra_special_tokens for transformers 4.x: {mapping}")
PY

  mkdir -p "$model_out"
  echo "[gguf] converting -> $(basename "$gguf_file")"
  "$VENV_PY" "$LLAMA_DIR/convert_hf_to_gguf.py" \
    "$model_src" \
    --outtype "$OUTTYPE" \
    --outfile "$gguf_file"

  # Sanity check: the file loads, and the fine-tuned <sil> control token that
  # the whole ConvFill prompt format depends on survived the conversion.
  GGUF_PATH="$gguf_file" PYTHONPATH="$LLAMA_DIR/gguf-py" "$VENV_PY" - <<'PY'
import os
import sys
from gguf import GGUFReader

reader = GGUFReader(os.environ["GGUF_PATH"])


def field(name):
    f = reader.fields.get(name)
    return f.contents() if f is not None else None


arch = field("general.architecture")
tokens = reader.fields.get("tokenizer.ggml.tokens")
n_tokens = len(tokens.data) if tokens is not None else 0
has_sil = any(tokens.contents(i) == "<sil>" for i in range(n_tokens))
has_template = reader.fields.get("tokenizer.chat_template") is not None

print(f"[check] architecture   : {arch}")
print(f"[check] tensors        : {len(reader.tensors)}")
print(f"[check] vocab tokens   : {n_tokens}")
print(f"[check] <sil> token    : {'present' if has_sil else 'MISSING'}")
print(f"[check] chat template  : {'present' if has_template else 'missing'}")

if not has_sil:
    print("[check] ERROR: <sil> is absent; the Talker prompt format needs it.", file=sys.stderr)
    raise SystemExit(1)
PY

  CONVERTED="$CONVERTED$gguf_file
"

  # Minimal model card so the directory is ready to push as-is.
  cat > "$model_out/README.md" <<EOF
---
base_model: $repo
tags:
  - gguf
  - convfill
library_name: gguf
---

# ${name}-${OUTTAG}

$OUTTAG (int8) GGUF build of [\`$repo\`](https://huggingface.co/$repo),
a ConvFill \`Talker\` model.

Quantized directly from the original bf16 fine-tuned weights with
\`llama.cpp\` \`convert_hf_to_gguf.py --outtype $OUTTYPE\`
(llama.cpp \`$LLAMA_CPP_REF\`).

The model uses the added \`<sil>\` control token for the conversational-infill
prompt format. See [ConvFill](https://github.com/vysri/conversational-infill)
and the [paper](https://arxiv.org/abs/2511.07397).
EOF
done

# --- summary -----------------------------------------------------------------
echo
echo "Done. Q8_0 GGUF files under $OUT_DIR:"
printf '%s' "$CONVERTED" | while read -r f; do
  if [ -n "$f" ]; then
    printf '  %6s  %s\n' "$(du -h "$f" | cut -f1)" "$f"
  fi
done

echo
echo "Upload one with the HuggingFace CLI (from the conversion venv):"
echo "  $VENV_PY -m pip install -U 'huggingface_hub[cli]'"
echo "  $VENV_DIR/bin/hf auth login"
echo "  $VENV_DIR/bin/hf upload <your-org>/<name>${OUTSUFFIX} $OUT_DIR/<name>${OUTSUFFIX} ."
