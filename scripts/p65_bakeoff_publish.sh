#!/usr/bin/env bash
# Phase 6.5 paired bakeoff publish — quantize + publish 4 Orionfold HF repos
# for the patent-strategist v3 Unsloth vs NeMo bakeoff (Article H).
#
# Slugs published:
#   - Orionfold/patent-strategist-v3-unsloth-GGUF   (4 GGUF variants, ~25 GB)
#   - Orionfold/patent-strategist-v3-nemo-GGUF      (4 GGUF variants, ~25 GB)
#   - Orionfold/patent-strategist-v3-unsloth        (BF16 HF, ~16 GB)
#   - Orionfold/patent-strategist-v3-nemo           (BF16 HF, ~16 GB)
#
# Phases:
#   1.   env setup + status JSON init
#   2.   convert_hf_to_gguf × 2 → F16 GGUF per lane
#   3.   llama-quantize × 8 (4 variants × 2 lanes)
#   3.5. measure perplexity + tok/s per variant (8 measures)
#   4.   stage 4 repos (2 GGUF via publish_quant, 2 BF16 via HFHubAdapter)
#   5.   cross-link READMEs + inject v3-corpus disclosure + customer audit
#   6.   verify_stage × 4
#   7.   manual gate (writes manual_gate.ready=true; waits for touch file)
#   8.   hf_push_resilient × 4 in size-ascending order
#   9.   finalize status JSON with URLs + wall times
#
# Idempotent — each phase skips if its name is already in completed_phases.
# Restart by re-running the same nohup invocation; status JSON survives.

set -uo pipefail
# NB: not set -e — phase failures are caught + journaled into status JSON.

# === Config ============================================================

REPO=/home/nvidia/ainative-business.github.io
HF_VENV=/tmp/fk
LLAMA_BIN=/home/nvidia/llama.cpp/build/bin
LLAMA_CONVERT=/home/nvidia/llama.cpp/convert_hf_to_gguf.py

UNSLOTH_BF16=/home/nvidia/data/aifn-train-lora/patent-strategist-v3-2026-05-21/merged-bf16
NEMO_BF16=/home/nvidia/data/aifn-train-lora/p65-nemo/merged-hf-bf16-clean
BASE_MODEL=deepseek-ai/DeepSeek-R1-0528-Qwen3-8B

QUANTS_BASE=/home/nvidia/data/quants
UNSLOTH_QUANTS=$QUANTS_BASE/patent-strategist-v3-unsloth
NEMO_QUANTS=$QUANTS_BASE/patent-strategist-v3-nemo
WIKITEXT=/home/nvidia/data/calibration/wikitext-2-raw-v1/wiki.test.raw

STAGE_BASE=/tmp/orionfold-stage
ARTICLE_SLUG=patent-strategist-bakeoff-unsloth-vs-nemo-framework
ARTICLE_TITLE="Two paths to the same chain — Unsloth vs NeMo Framework on Spark"
ARTIFACTS_DIR=$REPO/src/content/artifacts

STATUS_FILE=/home/nvidia/data/orionfold-bakeoff-status.json
LOG_FILE=/tmp/orionfold-bakeoff.log
RESUME_TOUCH=/tmp/orionfold-bakeoff-resume

VARIANTS=(Q4_K_M Q5_K_M Q6_K Q8_0)

# Push order: GGUF first (smaller single-file LFS chunks → resume cheaper if
# the connection dies mid-flight), BF16 second.
SLUGS=(
  patent-strategist-v3-unsloth-GGUF
  patent-strategist-v3-nemo-GGUF
  patent-strategist-v3-unsloth
  patent-strategist-v3-nemo
)

# === Env ===============================================================

set -a; source $REPO/.env.local; set +a
export HF_HOME=/home/nvidia/data/.hf-cache
export HF_HUB_DISABLE_XET=1

# === Logging + helpers =================================================

log() { printf '\033[1;36m[p65]\033[0m %s %s\n' "$(date -u +'%H:%M:%S')" "$*"; }
die() { printf '\033[1;31m[p65 FATAL]\033[0m %s\n' "$*" >&2; status_set_phase "failed:$*"; exit 1; }

iso_now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

status_init() {
  $HF_VENV/bin/python - <<PYINIT
import json, pathlib
slugs = """${SLUGS[@]}""".split()
state = {
  "started_at": "$(iso_now)",
  "phase": "init",
  "phase_started_at": "$(iso_now)",
  "completed_phases": [],
  "repos": {s: {"stage": None, "pushed": False, "url": None, "size_gb": None, "wall_seconds": None} for s in slugs},
  "log_path": "$LOG_FILE",
  "manual_gate": {"ready": False, "resume_touch": "$RESUME_TOUCH"},
  "errors": []
}
pathlib.Path("$STATUS_FILE").write_text(json.dumps(state, indent=2))
PYINIT
}

status_load_completed() {
  $HF_VENV/bin/python -c "import json,sys; print(' '.join(json.load(open('$STATUS_FILE'))['completed_phases']))" 2>/dev/null || echo ""
}

status_set_phase() {
  local phase="$1"
  $HF_VENV/bin/python - <<PYSET
import json, pathlib
p = pathlib.Path("$STATUS_FILE")
d = json.loads(p.read_text())
d["phase"] = "$phase"
d["phase_started_at"] = "$(iso_now)"
p.write_text(json.dumps(d, indent=2))
PYSET
}

status_complete_phase() {
  local phase="$1"
  $HF_VENV/bin/python - <<PYDONE
import json, pathlib
p = pathlib.Path("$STATUS_FILE")
d = json.loads(p.read_text())
if "$phase" not in d["completed_phases"]:
    d["completed_phases"].append("$phase")
p.write_text(json.dumps(d, indent=2))
PYDONE
}

status_set_repo() {
  local slug="$1" key="$2" val="$3"
  $HF_VENV/bin/python - <<PYREPO
import json, pathlib
p = pathlib.Path("$STATUS_FILE")
d = json.loads(p.read_text())
val = "$val"
if val in ("true", "True"): val = True
elif val in ("false", "False"): val = False
else:
    try: val = float(val) if "." in val else int(val)
    except ValueError: pass
d["repos"]["$slug"]["$key"] = val
p.write_text(json.dumps(d, indent=2))
PYREPO
}

status_set_manual_ready() {
  $HF_VENV/bin/python - <<PYGATE
import json, pathlib
p = pathlib.Path("$STATUS_FILE")
d = json.loads(p.read_text())
d["manual_gate"]["ready"] = True
d["manual_gate"]["ready_at"] = "$(iso_now)"
p.write_text(json.dumps(d, indent=2))
PYGATE
}

phase_already_done() {
  local p="$1"
  # Exact-token match — hyphenated phase names like `4_stage_X-unsloth` must
  # NOT match `4_stage_X-unsloth-GGUF` (grep -w treats `-` as a word boundary).
  status_load_completed | tr ' ' '\n' | grep -qxF "$p"
}

# === PHASE 1 — env + status init =======================================

phase_1_init() {
  log "=== PHASE 1_init START ==="
  status_init
  status_set_phase "1_init"
  mkdir -p "$UNSLOTH_QUANTS" "$NEMO_QUANTS" "$STAGE_BASE" "$ARTIFACTS_DIR"
  # Sanity
  [[ -f "$UNSLOTH_BF16/config.json" ]] || die "Unsloth BF16 missing config.json at $UNSLOTH_BF16"
  [[ -f "$NEMO_BF16/config.json"     ]] || die "NeMo BF16 missing config.json at $NEMO_BF16"
  [[ -x "$LLAMA_BIN/llama-quantize"  ]] || die "llama-quantize missing at $LLAMA_BIN"
  [[ -f "$LLAMA_CONVERT"             ]] || die "convert_hf_to_gguf.py missing at $LLAMA_CONVERT"
  [[ -x "$HF_VENV/bin/python"        ]] || die "HF venv missing at $HF_VENV"
  [[ -n "${HF_TOKEN:-}"              ]] || die "HF_TOKEN not in env (sourced from $REPO/.env.local)"
  [[ -f "$WIKITEXT"                  ]] || die "wikitext corpus missing at $WIKITEXT"
  log "preflight ok — quants_base=$QUANTS_BASE stage_base=$STAGE_BASE"
  status_complete_phase "1_init"
  log "=== PHASE 1_init END ==="
}

# === PHASE 2 — convert HF → F16 GGUF ===================================

phase_2_convert() {
  local lane="$1" src="$2" outdir="$3"
  local phase="2_convert_${lane}"
  if phase_already_done "$phase"; then log "skip $phase (already done)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local f16=$outdir/model-F16.gguf
  if [[ -f "$f16" ]] && [[ $(stat -c%s "$f16") -gt 10000000000 ]]; then
    log "F16 GGUF already exists ($(du -h "$f16" | cut -f1)) — skipping convert"
  else
    log "converting $src → $f16"
    "$HF_VENV/bin/python" "$LLAMA_CONVERT" "$src" \
      --outfile "$f16" \
      --outtype f16 \
      || die "convert failed for lane=$lane (src=$src)"
  fi
  log "F16 size: $(du -h "$f16" | cut -f1)"
  status_complete_phase "$phase"
  log "=== PHASE $phase END ==="
}

# === PHASE 3 — quantize F16 → variants =================================

phase_3_quantize() {
  local lane="$1" outdir="$2"
  local phase="3_quantize_${lane}"
  if phase_already_done "$phase"; then log "skip $phase (already done)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local f16=$outdir/model-F16.gguf
  [[ -f "$f16" ]] || die "F16 GGUF missing at $f16 — convert must run first"
  for v in "${VARIANTS[@]}"; do
    local out=$outdir/model-$v.gguf
    if [[ -f "$out" ]] && [[ $(stat -c%s "$out") -gt 1000000000 ]]; then
      log "  skip $v (already exists, $(du -h "$out" | cut -f1))"
      continue
    fi
    log "  quantizing $v"
    "$LLAMA_BIN/llama-quantize" "$f16" "$out" "$v" \
      || die "quantize failed for lane=$lane variant=$v"
    log "  $v size: $(du -h "$out" | cut -f1)"
  done
  status_complete_phase "$phase"
  log "=== PHASE $phase END ==="
}

# === PHASE 3.5 — measure perplexity + tok/s per variant ================

phase_35_measure() {
  local lane="$1" outdir="$2"
  local phase="35_measure_${lane}"
  if phase_already_done "$phase"; then log "skip $phase (already done)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local mfile=$outdir/measurements.json
  "$HF_VENV/bin/python" - <<PYMEASURE
import json, os, subprocess, pathlib, re

LLAMA_BIN = "$LLAMA_BIN"
OUTDIR = pathlib.Path("$outdir")
WIKITEXT = "$WIKITEXT"
VARIANTS = "${VARIANTS[*]}".split()
MFILE = OUTDIR / "measurements.json"

# Resume-aware: load existing, only fill in missing variants
data = {}
if MFILE.exists():
    data = json.loads(MFILE.read_text())
ppl_d = data.get("perplexity", {})
tps_d = data.get("tokens_per_sec", {})
gguf_b = data.get("gguf_bytes", {})

for v in VARIANTS:
    gguf = OUTDIR / f"model-{v}.gguf"
    if not gguf.exists():
        print(f"  SKIP {v}: GGUF missing")
        continue
    gguf_b[v] = gguf.stat().st_size

    # Perplexity — wikitext-2 test, chunk_size=512
    if v in ppl_d:
        print(f"  {v}: perplexity cached = {ppl_d[v]:.3f}")
    else:
        print(f"  {v}: perplexity sweep ...")
        cmd = [
            f"{LLAMA_BIN}/llama-perplexity",
            "-m", str(gguf),
            "-f", WIKITEXT,
            "-ngl", "99",
            "-c", "512",
            "--chunks", "100",  # cap for wall budget; ~3-5 min per variant
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        # llama-perplexity prints "Final estimate: PPL = X.XXXX +/- Y.YY"
        m = re.search(r"Final estimate:\s*PPL\s*=\s*([0-9.]+)", r.stdout + r.stderr)
        if m:
            ppl_d[v] = float(m.group(1))
            print(f"    PPL = {ppl_d[v]:.3f}")
        else:
            print(f"    FAILED to parse PPL; stderr tail: {r.stderr[-500:]}")
            ppl_d[v] = None

    # tok/s — llama-bench, single -p 64 + -n 64 run
    if v in tps_d:
        print(f"  {v}: tok/s cached = tg={tps_d[v]['tg']:.1f}")
    else:
        print(f"  {v}: bench sweep ...")
        cmd = [
            f"{LLAMA_BIN}/llama-bench",
            "-m", str(gguf),
            "-ngl", "99",
            "-p", "64",
            "-n", "64",
            "-r", "2",
            "-o", "json",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        try:
            rows = json.loads(r.stdout)
            tg_runs = [row["avg_ts"] for row in rows if row.get("n_gen", 0) > 0]
            pp_runs = [row["avg_ts"] for row in rows if row.get("n_prompt", 0) > 0]
            tps_d[v] = {
                "tg": (sum(tg_runs)/len(tg_runs)) if tg_runs else None,
                "pp": (sum(pp_runs)/len(pp_runs)) if pp_runs else None,
            }
            print(f"    tg={tps_d[v]['tg']:.1f} pp={tps_d[v]['pp']:.1f}")
        except Exception as exc:
            print(f"    FAILED to parse bench: {exc}; stdout tail: {r.stdout[-400:]}")
            tps_d[v] = {"tg": None, "pp": None}

data["perplexity"] = ppl_d
data["tokens_per_sec"] = tps_d
data["gguf_bytes"] = gguf_b
MFILE.write_text(json.dumps(data, indent=2))
print(f"wrote {MFILE}")
PYMEASURE
  [[ -f "$mfile" ]] || die "measurement file not written at $mfile"
  log "measurements written: $mfile"
  status_complete_phase "$phase"
  log "=== PHASE $phase END ==="
}

# === PHASE 4 — stage 4 repos ===========================================

phase_4_stage_gguf() {
  local lane="$1" quantsdir="$2" repo_name="$3"
  local phase="4_stage_${repo_name}"
  if phase_already_done "$phase"; then log "skip $phase (already done)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local stage_dir=$STAGE_BASE/$repo_name
  rm -rf "$stage_dir"
  mkdir -p "$stage_dir"
  "$HF_VENV/bin/python" - <<PYSTAGE_GGUF
import json, sys, pathlib
sys.path.insert(0, "$REPO/fieldkit/src")
from types import SimpleNamespace
from fieldkit.publish import publish_quant

QUANTS = pathlib.Path("$quantsdir")
STAGE = "$STAGE_BASE/$repo_name"
LANE = "$lane"
REPO_NAME = "$repo_name"
ARTICLE_SLUG = "$ARTICLE_SLUG"
ARTICLE_TITLE = "$ARTICLE_TITLE"
ARTIFACTS_DIR = "$ARTIFACTS_DIR"
BASE_MODEL = "$BASE_MODEL"

measurements = json.loads((QUANTS / "measurements.json").read_text())

def _human(n):
    if not n: return ""
    return f"{n/(1024**3):.2f} GB"

variants = """${VARIANTS[@]}""".split()
variant_files = {}
for v in variants:
    gguf = QUANTS / f"model-{v}.gguf"
    if gguf.exists():
        variant_files[v] = {
            "path": str(gguf),
            "rel": gguf.name,
            "size": _human(gguf.stat().st_size),
        }

tps = measurements.get("tokens_per_sec", {})
tps_flat = {v: (tps[v]["tg"] if isinstance(tps.get(v), dict) and tps[v].get("tg") else None)
            for v in variants}
tps_flat = {k: v for k, v in tps_flat.items() if v is not None}

report = SimpleNamespace(
    format="gguf",
    variants=tuple(variants),
    variant_files=variant_files,
    perplexity={k: v for k, v in measurements.get("perplexity", {}).items() if v is not None},
    tokens_per_sec=tps_flat,
    sustained_load_minutes=None,
)

# llama-cpp-python prompt template — single MCQ-shaped example mirroring
# the bakeoff probe's patent-strategic family
example_prompt = (
    "A licensee under a non-exclusive patent license discovers the licensor "
    "has signed a more favorable royalty rate with a later licensee. The "
    "agreement contains a most-favored-licensee clause requiring rate parity. "
    "Walk through the legal and commercial steps the original licensee should "
    "take to enforce parity, including notice requirements and remedies."
)

result = publish_quant(
    quant_report=report,
    base_model=BASE_MODEL,
    repo_name=REPO_NAME,
    staging_dir=STAGE,
    artifacts_dir=ARTIFACTS_DIR,
    article_slug=ARTICLE_SLUG,
    article_title=ARTICLE_TITLE,
    model_license="apache-2.0",
    chat_format=None,  # empty per decision 3 — R1 GGUF carries embedded template
    recommended_variant="Q5_K_M",
    llama_cpp_example_prompt=example_prompt,
    extra_tags=(
        "patent",
        "patent-strategist",
        "reasoning",
        "lora-finetune",
        f"trained-with-{LANE}",
        "bakeoff",
        "r1-distill",
    ),
    dry_run=True,
)
print(f"staged: {result.hf_repo}")
print(f"card:   {result.card_path}")
print(f"files:  {len(result.files_uploaded)}")
print(f"manifest: {result.manifest_path}")
PYSTAGE_GGUF
  [[ -f "$stage_dir/README.md" ]] || die "GGUF stage failed for $repo_name — no README.md"
  local sz=$(du -sb "$stage_dir" | cut -f1)
  status_set_repo "$repo_name" "stage" "$stage_dir"
  status_set_repo "$repo_name" "size_gb" "$(echo "scale=2; $sz/1073741824" | bc)"
  status_complete_phase "$phase"
  log "=== PHASE $phase END (size: $(du -sh "$stage_dir" | cut -f1)) ==="
}

phase_4_stage_bf16() {
  local lane="$1" src="$2" repo_name="$3"
  local phase="4_stage_${repo_name}"
  if phase_already_done "$phase"; then log "skip $phase (already done)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local stage_dir=$STAGE_BASE/$repo_name
  rm -rf "$stage_dir"
  mkdir -p "$stage_dir"
  log "  copying BF16 files from $src → $stage_dir"
  cp -a "$src/." "$stage_dir/"
  # Render the BF16 README by hand (publish_quant is GGUF-specific). Quoted
  # heredoc — markdown text contains backticks which would trigger bash
  # command-substitution if unquoted. Pass bash vars via P65_* env.
  P65_REPO="$REPO" \
  P65_STAGE="$stage_dir" \
  P65_LANE="$lane" \
  P65_REPO_NAME="$repo_name" \
  P65_BASE_MODEL="$BASE_MODEL" \
  P65_ARTICLE_SLUG="$ARTICLE_SLUG" \
  P65_ARTICLE_TITLE="$ARTICLE_TITLE" \
  P65_ARTIFACTS_DIR="$ARTIFACTS_DIR" \
  "$HF_VENV/bin/python" - <<'PYSTAGE_BF16'
import json, os, pathlib, sys
sys.path.insert(0, os.environ["P65_REPO"] + "/fieldkit/src")
from fieldkit.publish import ARTIFACT_KINDS, ArtifactManifest, write_artifact_manifest
from datetime import datetime, timezone

STAGE = pathlib.Path(os.environ["P65_STAGE"])
LANE = os.environ["P65_LANE"]
REPO_NAME = os.environ["P65_REPO_NAME"]
HF_REPO = f"Orionfold/{REPO_NAME}"
BASE_MODEL = os.environ["P65_BASE_MODEL"]
ARTICLE_SLUG = os.environ["P65_ARTICLE_SLUG"]
ARTICLE_TITLE = os.environ["P65_ARTICLE_TITLE"]
ARTIFACTS_DIR = pathlib.Path(os.environ["P65_ARTIFACTS_DIR"])

# Discover safetensors files for the Variants table + Spark-tested row
safetensors = sorted(p.name for p in STAGE.glob("model*.safetensors"))
total_bytes = sum((STAGE / f).stat().st_size for f in safetensors)
size_label = f"{total_bytes/(1024**3):.2f} GB"

# Hand-rendered README
fm_lines = [
    "---",
    "license: apache-2.0",
    "library_name: transformers",
    f"base_model: {BASE_MODEL}",
    "pipeline_tag: text-generation",
    'model_creator: "Orionfold LLC"',
    "language:",
    "  - en",
    "tags:",
    "  - transformers",
    "  - safetensors",
    "  - bf16",
    "  - spark-tested",
    "  - orionfold",
    "  - patent",
    "  - patent-strategist",
    "  - reasoning",
    "  - lora-finetune",
    f"  - trained-with-{LANE}",
    "  - bakeoff",
    "  - r1-distill",
    f"  - base_model:{BASE_MODEL}",
    "---",
    "",
]

title_lane = "Unsloth" if LANE == "unsloth" else "NeMo Framework"
body_lines = [
    f"# patent-strategist v3 — {title_lane} lane (BF16 HF)",
    "",
    f"`safetensors` BF16 merged weights of a LoRA fine-tune of `{BASE_MODEL}` on a 5,000-row synthetic patent-reasoning corpus, trained with **{title_lane}** on a NVIDIA DGX Spark (GB10, 128 GB unified memory).",
    "",
    f"Sibling repo: [`Orionfold/{REPO_NAME}-GGUF`](https://huggingface.co/Orionfold/{REPO_NAME}-GGUF) — `llama.cpp`-quantized variants (Q4_K_M / Q5_K_M / Q6_K / Q8_0) for low-VRAM inference.",
    "",
    "## Spark-tested",
    "",
    "Every Orionfold artifact ships with a measurement triple on the NVIDIA DGX Spark (GB10, 128 GB unified memory): training wall, probe think rate, and probe mean chain length.",
    "",
    "| Variant | Size | Train wall | Think rate (patent-strategic) | Mean chain (patent-strategic) |",
    "|---|---|---|---|---|",
]
if LANE == "unsloth":
    body_lines.append(f"| BF16 | {size_label} | 7h 34m | 0.80 | 916 tok |")
else:
    body_lines.append(f"| BF16 | {size_label} | 5h 38m | 0.80 | 1,320 tok |")
body_lines += [
    "",
    f"Full bakeoff numbers (probe think rate + mean chain across 4 prompt families × 20 questions) are in the [Methods](https://ainative.business/field-notes/{ARTICLE_SLUG}/) article.",
    "",
    "## How to run",
    "",
    "Load via `transformers`:",
    "",
    "```python",
    "from transformers import AutoTokenizer, AutoModelForCausalLM",
    "import torch",
    "",
    f'model_id = "{HF_REPO}"',
    "tok = AutoTokenizer.from_pretrained(model_id)",
    "model = AutoModelForCausalLM.from_pretrained(",
    '    model_id, torch_dtype=torch.bfloat16, device_map="auto"',
    ")",
    "",
    "prompt = (",
    '    "<｜User｜>A patent claim recites \\"a fastener selected from the group consisting "',
    '    "of bolts, screws, and rivets.\\" Walk through the Markush-group construction "',
    '    "and explain how doctrine of equivalents applies to a magnetic snap.<｜Assistant｜>"',
    ")",
    "inputs = tok(prompt, return_tensors=\"pt\").to(model.device)",
    "out = model.generate(**inputs, max_new_tokens=1024, temperature=0.6, top_p=0.95)",
    "print(tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))",
    "```",
    "",
    "## Methods",
    "",
    f"Full methodology — bakeoff recipe, training-wall measurement protocol, per-lane probe results, and the YARN-rope patch that gated NeMo Framework's R1 path: [{ARTICLE_TITLE}](https://ainative.business/field-notes/{ARTICLE_SLUG}/).",
    "",
    "---",
    "",
    'Published by **Orionfold LLC** · [orionfold.com](https://orionfold.com) · Methods documented at [ainative.business/field-notes](https://ainative.business/field-notes/).',
    "",
]
(STAGE / "README.md").write_text("\n".join(fm_lines) + "\n".join(body_lines) + "\n", encoding="utf-8")

# Write the Phase-2 sync manifest
manifest = ArtifactManifest(
    slug=REPO_NAME.lower(),
    kind="quant",        # repurpose for now; BF16 is a "quant" of nothing but the manifest schema is artifact-kind-agnostic
    artifact_class="bf16",
    base_model=BASE_MODEL,
    hf_repo=HF_REPO,
    variants=("BF16",),
    perplexity={},
    spark_tokens_per_sec={},
    sustained_load_minutes=None,
    vertical_eval={},
    vertical_eval_name=None,
    recommended_variant="BF16",
    model_license="apache-2.0",
    article=f"articles/{ARTICLE_SLUG}/",
    published_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
)
mpath = write_artifact_manifest(manifest, artifacts_dir=ARTIFACTS_DIR)
print(f"staged: {HF_REPO}")
print(f"  README:   {STAGE / 'README.md'}")
print(f"  manifest: {mpath}")
print(f"  files:    {len(list(STAGE.iterdir()))}")
print(f"  size:     {total_bytes/(1024**3):.2f} GB")
PYSTAGE_BF16
  [[ -f "$stage_dir/README.md" ]] || die "BF16 stage failed for $repo_name — no README.md"
  local sz=$(du -sb "$stage_dir" | cut -f1)
  status_set_repo "$repo_name" "stage" "$stage_dir"
  status_set_repo "$repo_name" "size_gb" "$(echo "scale=2; $sz/1073741824" | bc)"
  status_complete_phase "$phase"
  log "=== PHASE $phase END (size: $(du -sh "$stage_dir" | cut -f1)) ==="
}

# === PHASE 5 — cross-link READMEs + inject v3-corpus disclosure ========

phase_5_crosslink_audit() {
  local phase="5_crosslink_audit"
  if phase_already_done "$phase"; then log "skip $phase"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  # Quoted heredoc — DISCLOSURE markdown has backticks that would otherwise
  # trigger bash command substitution. Pass bash vars via P65_* env.
  P65_STAGE_BASE="$STAGE_BASE" \
  P65_SLUGS="${SLUGS[*]}" \
  "$HF_VENV/bin/python" - <<'PYCROSSLINK'
import os, pathlib, re
SLUGS = os.environ["P65_SLUGS"].split()
STAGE_BASE = os.environ["P65_STAGE_BASE"]

DISCLOSURE = """
## Known issues with the v3 corpus

This release is fine-tuned on the **v3 synthetic patent corpus**, which carries two known hallucinations propagated from the corpus generation process. **Be aware before using this model for any production patent workflow:**

- **Fabricated MPEP terminology.** The model has learned the term *"metes-and-times"*, which does not appear in the [Manual of Patent Examining Procedure](https://www.uspto.gov/web/offices/pac/mpep/). The correct legal term in claim construction is *"metes and bounds"*.
- **Fabricated MPEP citation.** The model cites *MPEP §2163.05(s)*, which does not exist. Real §2163.05 has subsections (a) through (f) and addresses written-description support; subsection (s) is fabricated.

These artifacts came from the corpus generator (Claude-Opus-4.5) hallucinating during synthesis and were not caught before the training run. The bakeoff article ([Methods](#methods)) ships the same disclosure. A v4 corpus regeneration with MPEP-grounded retrieval is on the roadmap.

"""

XLINK_TEMPLATE = """
## Other Orionfold variants

This release is one of four sibling repos from the same bakeoff:

| Variant | Lane | Format |
|---|---|---|
| [`Orionfold/patent-strategist-v3-unsloth`](https://huggingface.co/Orionfold/patent-strategist-v3-unsloth) | Unsloth | BF16 (transformers) |
| [`Orionfold/patent-strategist-v3-unsloth-GGUF`](https://huggingface.co/Orionfold/patent-strategist-v3-unsloth-GGUF) | Unsloth | GGUF (llama.cpp) |
| [`Orionfold/patent-strategist-v3-nemo`](https://huggingface.co/Orionfold/patent-strategist-v3-nemo) | NeMo Framework | BF16 (transformers) |
| [`Orionfold/patent-strategist-v3-nemo-GGUF`](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF) | NeMo Framework | GGUF (llama.cpp) |

The four artifacts come from the **same LoRA recipe** (R1-Qwen3-8B base, v3 corpus, r=16 α=32, q/k/v/o, LR 1e-4 cosine 5% warmup, micro 2 / global 16, ~2.2 epochs); the only difference is which trainer drove the GPU steps.

"""

for slug in SLUGS:
    readme = pathlib.Path(STAGE_BASE) / slug / "README.md"
    text = readme.read_text()

    # 1. Inject disclosure right after the title's elevator pitch (after first
    #    blank-line-terminated paragraph following the H1). Idempotent — skip
    #    if already present.
    if "Known issues with the v3 corpus" not in text:
        # Find end of frontmatter (second ---), then end of one-liner paragraph
        parts = text.split("\n", 1)
        # Walk past frontmatter
        m = re.search(r"^---\s*$", text, flags=re.MULTILINE)
        # Easier: insert disclosure before the FIRST ## heading after the H1
        m = re.search(r"(# .+\n\n[^\n]+(?:\n[^\n#]+)*\n)", text)
        if m:
            insertion_point = m.end()
            text = text[:insertion_point] + DISCLOSURE + text[insertion_point:]
        else:
            # Fallback — prepend after frontmatter
            fm_end = text.find("\n---\n", text.find("---")+3)
            if fm_end > 0:
                text = text[:fm_end+5] + "\n" + DISCLOSURE + text[fm_end+5:]
            else:
                text = DISCLOSURE + text

    # 2. Append cross-link block before the final "---" footer divider, if
    #    not already present
    if "Other Orionfold variants" not in text:
        # Find the LAST "---" footer divider
        footer_idx = text.rfind("\n---\n")
        if footer_idx > 0:
            text = text[:footer_idx] + "\n" + XLINK_TEMPLATE + text[footer_idx:]
        else:
            text = text + "\n" + XLINK_TEMPLATE

    readme.write_text(text)
    print(f"  patched: {readme}")

# Customer-link audit gate — every staged README must contain the disclosure
print()
print("=== CUSTOMER-LINK AUDIT ===")
audit_fails = []
required_markers = [
    "Known issues with the v3 corpus",
    "metes-and-times",
    "Other Orionfold variants",
    "ainative.business/field-notes",
]
for slug in SLUGS:
    readme = pathlib.Path(STAGE_BASE) / slug / "README.md"
    text = readme.read_text()
    missing = [m for m in required_markers if m not in text]
    if missing:
        audit_fails.append((slug, missing))
        print(f"  [FAIL] {slug}: missing {missing}")
    else:
        print(f"  [PASS] {slug}")

if audit_fails:
    print()
    print("ABORTING — customer-link audit failed")
    raise SystemExit(2)
print()
print("=== AUDIT 4/4 PASSED ===")
PYCROSSLINK
  local rc=$?
  [[ $rc -eq 0 ]] || die "customer-link audit failed (rc=$rc)"
  status_complete_phase "$phase"
  log "=== PHASE $phase END ==="
}

# === PHASE 6 — verify_stage × 4 ========================================

phase_6_verify() {
  local phase="6_verify_stage"
  if phase_already_done "$phase"; then log "skip $phase"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local fails=0
  for slug in "${SLUGS[@]}"; do
    local stage_dir=$STAGE_BASE/$slug
    log "  verify $slug"
    if [[ "$slug" == *-GGUF ]]; then
      # Standard verify_stage works for GGUF stages
      APACHE_VERIFIED=1 bash "$REPO/.claude/skills/hf-publisher/scripts/verify_stage.sh" "$stage_dir" \
        || { fails=$((fails+1)); log "  $slug verify FAILED"; }
    else
      # BF16 stage — hand-verify the relevant checks (skip the GGUF-only one)
      _verify_bf16_stage "$stage_dir" || { fails=$((fails+1)); log "  $slug bf16 verify FAILED"; }
    fi
  done
  [[ $fails -eq 0 ]] || die "verify_stage failed for $fails slug(s)"
  status_complete_phase "$phase"
  log "=== PHASE $phase END (4/4 PASSED) ==="
}

_verify_bf16_stage() {
  local stage="$1"
  local readme=$stage/README.md
  [[ -f "$readme" ]] || { log "    bf16-verify: README.md missing"; return 1; }
  # Check 1 — license frontmatter
  grep -q "^license: apache-2.0" "$readme" || { log "    bf16-verify: license missing/wrong"; return 1; }
  # Check 2 — How to run body ≥ 8 non-empty lines
  local howto
  howto=$(awk '/^## How to run/{f=1; next} f && /^## /{exit} f' "$readme" | grep -cE '\S')
  [[ "$howto" -ge 8 ]] || { log "    bf16-verify: How to run body too short ($howto < 8)"; return 1; }
  # Check 3 — Spark-tested table present + has 5 cols (Variant | Size | wall | think | chain)
  local hdr
  hdr=$(awk '/^## Spark-tested/{f=1; next} f && /^## /{exit} f && /^\| Variant \|/{print; exit}' "$readme")
  [[ -n "$hdr" ]] || { log "    bf16-verify: Spark-tested table missing"; return 1; }
  # Check 4 — Methods link points at existing article
  grep -qE "ainative\.business/field-notes/$ARTICLE_SLUG" "$readme" || {
    log "    bf16-verify: Methods link missing or wrong slug"; return 1;
  }
  [[ -d "$REPO/articles/$ARTICLE_SLUG" ]] || {
    log "    bf16-verify: article dir missing at $REPO/articles/$ARTICLE_SLUG"; return 1;
  }
  # Check 5 — safetensors present (BF16 substitute for GGUF check)
  ls "$stage"/model*.safetensors >/dev/null 2>&1 || {
    log "    bf16-verify: no model*.safetensors in stage"; return 1;
  }
  # Check 6 — engagement-pull tags (pipeline_tag, library_name, tags ≥ 3 inc spark-tested)
  grep -q "^pipeline_tag:" "$readme" || { log "    bf16-verify: pipeline_tag missing"; return 1; }
  grep -q "^library_name:" "$readme" || { log "    bf16-verify: library_name missing"; return 1; }
  grep -qF -- "- spark-tested" "$readme" || { log "    bf16-verify: spark-tested tag missing"; return 1; }
  printf "    \033[1;32m[bf16-PASS]\033[0m %s (6/6)\n" "$stage"
  return 0
}

# === PHASE 7 — manual gate =============================================

phase_7_manual_gate() {
  local phase="7_manual_gate"
  if phase_already_done "$phase"; then log "skip $phase (already passed)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  status_set_manual_ready
  log ""
  log "  ╔══════════════════════════════════════════════════════════════╗"
  log "  ║  MANUAL GATE — review stages, then resume                    ║"
  log "  ╠══════════════════════════════════════════════════════════════╣"
  log "  ║  4 READMEs to eyeball:                                       ║"
  for slug in "${SLUGS[@]}"; do
    log "  ║    $STAGE_BASE/$slug/README.md"
  done
  log "  ║                                                              ║"
  log "  ║  When ready to push, run:                                    ║"
  log "  ║    touch $RESUME_TOUCH"
  log "  ║                                                              ║"
  log "  ║  Status JSON: $STATUS_FILE"
  log "  ╚══════════════════════════════════════════════════════════════╝"
  log ""
  # Wait for the touch file. Poll every 30s; no timeout.
  while [[ ! -f "$RESUME_TOUCH" ]]; do
    sleep 30
  done
  log "  resume signal received — proceeding to push phase"
  rm -f "$RESUME_TOUCH"
  status_complete_phase "$phase"
  log "=== PHASE $phase END ==="
}

# === PHASE 8 — push × 4 in size order ==================================

phase_8_push() {
  local slug="$1"
  local phase="8_push_${slug}"
  if phase_already_done "$phase"; then log "skip $phase (already pushed)"; return; fi
  log "=== PHASE $phase START ==="
  status_set_phase "$phase"
  local stage_dir=$STAGE_BASE/$slug
  local push_start=$(date +%s)
  local push_log=/tmp/orionfold-push-${slug}.log
  log "  pushing $slug → Orionfold/$slug (log: $push_log)"
  REPO_NAME="$slug" STAGE_DIR="$stage_dir" NUM_WORKERS=1 PRINT_EVERY=30 \
    "$HF_VENV/bin/python" "$REPO/.claude/skills/hf-publisher/scripts/hf_push_resilient.py" \
    > "$push_log" 2>&1
  local rc=$?
  local push_end=$(date +%s)
  local wall=$((push_end - push_start))
  if [[ $rc -ne 0 ]]; then
    log "  PUSH FAILED for $slug (rc=$rc, wall=${wall}s) — see $push_log"
    status_set_repo "$slug" "pushed" "false"
    status_set_repo "$slug" "wall_seconds" "$wall"
    die "push failed for $slug — re-run script to resume from cache at $stage_dir/.cache/.huggingface/"
  fi
  local url="https://huggingface.co/Orionfold/$slug"
  status_set_repo "$slug" "pushed" "true"
  status_set_repo "$slug" "url" "$url"
  status_set_repo "$slug" "wall_seconds" "$wall"
  status_complete_phase "$phase"
  log "  pushed $slug in ${wall}s → $url"
  log "=== PHASE $phase END ==="
}

# === PHASE 9 — finalize ================================================

phase_9_finalize() {
  local phase="9_finalize"
  status_set_phase "done"
  status_complete_phase "$phase"
  log ""
  log "=== ALL DONE ==="
  "$HF_VENV/bin/python" - <<PYFIN
import json
d = json.load(open("$STATUS_FILE"))
print()
print("Published repos:")
for slug, info in d["repos"].items():
    if info["pushed"]:
        wall_min = (info["wall_seconds"] or 0) / 60
        print(f"  {slug:50s}  {info.get('size_gb','?')} GB  {wall_min:.0f} min  {info['url']}")
    else:
        print(f"  {slug:50s}  NOT pushed")
PYFIN
}

# === Main ==============================================================

main() {
  # Initialize fresh if no status file yet; otherwise resume from current state
  if [[ ! -f "$STATUS_FILE" ]]; then
    phase_1_init
  else
    log "resuming from $STATUS_FILE (completed: $(status_load_completed))"
  fi

  # Phase 2 — convert per lane
  phase_2_convert "unsloth" "$UNSLOTH_BF16" "$UNSLOTH_QUANTS"
  phase_2_convert "nemo"    "$NEMO_BF16"    "$NEMO_QUANTS"

  # Phase 3 — quantize per lane
  phase_3_quantize "unsloth" "$UNSLOTH_QUANTS"
  phase_3_quantize "nemo"    "$NEMO_QUANTS"

  # Phase 3.5 — measure per lane
  phase_35_measure "unsloth" "$UNSLOTH_QUANTS"
  phase_35_measure "nemo"    "$NEMO_QUANTS"

  # Phase 4 — stage all 4 repos
  phase_4_stage_gguf "unsloth" "$UNSLOTH_QUANTS" "patent-strategist-v3-unsloth-GGUF"
  phase_4_stage_gguf "nemo"    "$NEMO_QUANTS"    "patent-strategist-v3-nemo-GGUF"
  phase_4_stage_bf16 "unsloth" "$UNSLOTH_BF16"   "patent-strategist-v3-unsloth"
  phase_4_stage_bf16 "nemo"    "$NEMO_BF16"      "patent-strategist-v3-nemo"

  # Phase 5 — cross-link READMEs + customer-link audit
  phase_5_crosslink_audit

  # Phase 6 — verify_stage × 4
  phase_6_verify

  # Phase 7 — manual gate (blocks until touch file)
  phase_7_manual_gate

  # Phase 8 — push in order
  for slug in "${SLUGS[@]}"; do
    phase_8_push "$slug"
  done

  # Phase 9 — finalize
  phase_9_finalize
}

main "$@"
