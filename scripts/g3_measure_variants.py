#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""B4 — Spark-overlay measurement sweep for the Orionfold vertical-curator quant.

Runs four axes per GGUF variant — wikitext-2 perplexity, llama-bench tok/s,
sustained-load minutes, and vertical-eval accuracy via VerticalBench — and
writes `measurements.json` for the dry-run publish step plus appends one
`fieldkit.lineage.Trial` row per variant to the article's lineage TSV.

The vertical eval is selected by `VERTICAL_BENCH`:
    financebench (default)  open-book PatronusAI/financebench, numeric_match scorer
    legalbench              5-task subset of nguha/legalbench, contains scorer

Driven by env vars (matching `scripts/g3_build_first_quant.sh`):

    MODEL_SLUG          finance-Llama3-8B
    QUANTS_DIR          /home/nvidia/data/quants
    QUANT_VARIANTS      Q4_K_M,Q5_K_M,Q6_K,Q8_0,F16   (comma-separated)
    WIKITEXT_CORPUS     /home/nvidia/data/calibration/wikitext-2-raw-v1/wiki.test.raw
    VERTICAL_BENCH      financebench | legalbench | cybermetric | medmcqa (default financebench)
    FINBENCH_JSONL      /home/nvidia/data/eval-benches/financebench/financebench_merged.jsonl
    FINBENCH_SUBSET     metrics-generated  (FinanceBench question_type filter; "all" for all 150)
    FINBENCH_LIMIT      50                  (cap rows after filter)
    LEGALBENCH_JSONL    /home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl
    LEGALBENCH_LIMIT    50                  (cap rows; default = use all merged rows)
    LLAMA_CLI_NGL       99                  (GPU layers)
    LLAMA_CLI_NPREDICT  256                 (max tokens generated per Q)
    LINEAGE_DIR         articles/becoming-a-gguf-publisher-on-spark/evidence/lineage
    SKIP_VERTICAL       set non-empty to skip vertical-eval scoring (faster smoke)
    SKIP_THERMAL        set non-empty to skip the sustained-load sweep (faster smoke)

Each variant's row carries:

    core_metric    = FinanceBench accuracy (numeric_match, rel_tolerance=0.01)
    val_bpb        = wikitext-2 perplexity
    delta_vs_best  = delta of FinanceBench accuracy vs F16 reference row
    train_s        = (left None — quantize wall time logged separately)
    total_s        = measurement-sweep wall time per variant
    notes          = tg/pp tok/s, sustained-load minutes, gguf size, bench source
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "fieldkit" / "src"))

from fieldkit.eval import VerticalBench, contains, numeric_match  # noqa: E402


def _wrap_inst(question: str) -> str:
    """`<s>[INST] {q} [/INST]` — Llama-2-chat AND Mistral-Instruct (Saul) share
    this shape. AdaptLLM/finance-chat doesn't ship a chat_template but the
    README confirms Llama-2-chat lineage; Mistral-7B-Instruct's official format
    is identical. Per-variant scoring uses the same prompt shape as V0's
    preflight gate."""
    return f"<s>[INST] {question.strip()} [/INST]"


def _wrap_zephyr(question: str) -> str:
    """`<|user|>\\n{q}</s>\\n<|assistant|>\\n` — Zephyr DPO chat template.

    ZySec-AI/SecurityLLM and other Zephyr-7B-beta descendants ship this template
    in `tokenizer_config.json`. Mistral-arch eos_token is `</s>`; the trailing
    `<|assistant|>` newline matches the `add_generation_prompt=True` jinja path
    in the model card.
    """
    return f"<|user|>\n{question.strip()}</s>\n<|assistant|>\n"


def _wrap_chatml(question: str) -> str:
    """`<|im_start|>user\\n{q}<|im_end|>\\n<|im_start|>assistant\\n` — ChatML.

    Qwen2/Qwen3 + Hermes/OpenChat/II-Medical-8B all ship this template in
    `tokenizer_config.json`. The trailing `<|im_start|>assistant\\n` matches
    the `add_generation_prompt=True` jinja path so the server starts emitting
    the assistant turn directly.
    """
    return f"<|im_start|>user\n{question.strip()}<|im_end|>\n<|im_start|>assistant\n"


# Promoted to `fieldkit.eval.mcq_letter` after three vertical-bench reuses
# (cyber, medical, patent-strategist) per
# [[feedback_keep_scorer_local_until_reuse]].
from fieldkit.eval import mcq_letter  # noqa: E402
from fieldkit.lineage import FailureLabel, LineageStore, Trial  # noqa: E402
from fieldkit.quant import (  # noqa: E402
    LlamaCppPaths,
    ThermalProbe,
    measure_perplexity_gguf,
    measure_tokens_per_sec_gguf,
)


# --- Vertical-bench selection ----------------------------------------------

VERTICAL_BENCH = os.environ.get("VERTICAL_BENCH", "financebench").lower()
if VERTICAL_BENCH not in ("financebench", "legalbench", "cybermetric", "medmcqa"):
    raise SystemExit(
        f"VERTICAL_BENCH must be 'financebench' / 'legalbench' / 'cybermetric' / 'medmcqa', "
        f"got {VERTICAL_BENCH!r}"
    )


# --- Variant-trial builder (mirrors articles/.../lineage-demo.py) ---------

_DEFAULT_DOMAIN = {
    "financebench": "vertical-curator-finance",
    "legalbench": "vertical-curator-legal",
    "cybermetric": "vertical-curator-cyber",
    "medmcqa": "vertical-curator-medical",
}[VERTICAL_BENCH]
_DEFAULT_BASELINE = {
    "financebench": "AdaptLLM/finance-chat",
    "legalbench": "Equall/Saul-7B-Instruct-v1",
    "cybermetric": "ZySec-AI/SecurityLLM",
    "medmcqa": "Intelligent-Internet/II-Medical-8B",
}[VERTICAL_BENCH]
_DEFAULT_BENCH_DATASET = {
    "financebench": "PatronusAI/financebench",
    "legalbench": "nguha/legalbench",
    "cybermetric": "tihanyin/CyberMetric",
    "medmcqa": "openlifescienceai/medmcqa",
}[VERTICAL_BENCH]

DOMAIN = os.environ.get("LINEAGE_DOMAIN", _DEFAULT_DOMAIN)
BASELINE_HF_REPO = os.environ.get("BASELINE_HF_REPO", _DEFAULT_BASELINE)
BENCH_HF_DATASET = os.environ.get("BENCH_HF_DATASET", _DEFAULT_BENCH_DATASET)


def make_variant_trial(
    *,
    exp_id: str,
    variant: str,
    timestamp: str,
    finance_accuracy: float | None,
    wikitext_perplexity: float | None,
    delta_vs_best_acc: float | None,
    quantize_seconds: float | None,
    total_seconds: float | None,
    gguf_size_bytes: int | None,
    tokens_per_sec_tg: float | None,
    tokens_per_sec_pp: float | None,
    sustained_load_minutes: float | None,
    status: FailureLabel = FailureLabel.KEEP,
) -> Trial:
    notes_bits: list[str] = []
    if tokens_per_sec_tg is not None:
        notes_bits.append(f"tg_tok_per_s={tokens_per_sec_tg:.1f}")
    if tokens_per_sec_pp is not None:
        notes_bits.append(f"pp_tok_per_s={tokens_per_sec_pp:.1f}")
    if sustained_load_minutes is not None:
        notes_bits.append(f"sustained_load_min={sustained_load_minutes:.1f}")
    if gguf_size_bytes is not None:
        notes_bits.append(f"gguf_size_bytes={gguf_size_bytes}")
    notes_bits.append(f"bench={BENCH_HF_DATASET}")
    notes_bits.append("corpus=wikitext-2-raw-v1/wiki.test.raw")
    _bench_label = {
        "financebench": "FinanceBench",
        "legalbench": "LegalBench",
        "cybermetric": "CyberMetric",
        "medmcqa": "MedMCQA",
    }[VERTICAL_BENCH]
    return Trial(
        exp_id=exp_id,
        timestamp=timestamp,
        specialist=f"orionfold-curator/{variant}",
        parent_exp="000",
        baseline_exp="000",
        domain=DOMAIN,
        hypothesis=f"{variant} quant of {BASELINE_HF_REPO} — Spark-tested measurement layer",
        expected_delta=f"{_bench_label} accuracy delta vs F16 baseline",
        status=status,
        core_metric=finance_accuracy,
        val_bpb=wikitext_perplexity,
        delta_vs_best=delta_vs_best_acc,
        train_s=quantize_seconds,
        total_s=total_seconds,
        job_name=f"orionfold-{MODEL_SLUG.lower()}-{variant.lower()}",
        snapshot_path=str(QUANTS_DIR / f"model-{variant}.gguf"),
        notes=" ; ".join(notes_bits),
    )


# --- Config ----------------------------------------------------------------

MODEL_SLUG = os.environ.get("MODEL_SLUG", "finance-chat")
QUANTS_DIR = Path(os.environ.get("QUANTS_DIR", "/home/nvidia/data/quants")) / MODEL_SLUG
WIKITEXT_CORPUS = Path(
    os.environ.get("WIKITEXT_CORPUS", "/home/nvidia/data/calibration/wikitext-2-raw-v1/wiki.test.raw")
)
FINBENCH_JSONL = Path(
    os.environ.get(
        "FINBENCH_JSONL",
        "/home/nvidia/data/eval-benches/financebench/financebench_merged.jsonl",
    )
)
FINBENCH_SUBSET = os.environ.get("FINBENCH_SUBSET", "metrics-generated")
FINBENCH_LIMIT = int(os.environ.get("FINBENCH_LIMIT", "50"))
LEGALBENCH_JSONL = Path(
    os.environ.get(
        "LEGALBENCH_JSONL",
        "/home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl",
    )
)
LEGALBENCH_LIMIT = int(os.environ.get("LEGALBENCH_LIMIT", "50"))
CYBERBENCH_JSONL = Path(
    os.environ.get(
        "CYBERBENCH_JSONL",
        "/home/nvidia/data/eval-benches/cybermetric/cybermetric_merged.jsonl",
    )
)
CYBERBENCH_LIMIT = int(os.environ.get("CYBERBENCH_LIMIT", "50"))
MEDMCQA_JSONL = Path(
    os.environ.get(
        "MEDMCQA_JSONL",
        "/home/nvidia/data/eval-benches/medmcqa/medmcqa_merged.jsonl",
    )
)
MEDMCQA_LIMIT = int(os.environ.get("MEDMCQA_LIMIT", "50"))
LLAMA_CLI_NGL = int(os.environ.get("LLAMA_CLI_NGL", "99"))
LLAMA_CLI_NPREDICT = int(os.environ.get("LLAMA_CLI_NPREDICT", "256"))
LINEAGE_DIR = Path(
    os.environ.get(
        "LINEAGE_DIR",
        str(
            REPO_ROOT
            / "articles"
            / "becoming-a-gguf-publisher-on-spark"
            / "evidence"
            / f"lineage-{MODEL_SLUG}"
        ),
    )
)
QUANT_VARIANTS = tuple(os.environ.get("QUANT_VARIANTS", "Q4_K_M,Q5_K_M,Q6_K,Q8_0,F16").split(","))
SKIP_VERTICAL = bool(os.environ.get("SKIP_VERTICAL"))
SKIP_THERMAL = bool(os.environ.get("SKIP_THERMAL"))

LLAMA_CLI = Path(os.environ.get("LLAMA_CPP_BIN", "/home/nvidia/llama.cpp/build/bin")) / "llama-cli"


# --- Thermal probe in a background thread ---------------------------------


def _probe_loop(probe: ThermalProbe, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            probe.sample()
        except Exception:
            # nvidia-smi may transiently fail mid-load; keep polling.
            pass
        stop_event.wait(probe.interval_s)


class _NullCtx:
    """No-op context manager used when SKIP_THERMAL is set."""

    def __enter__(self) -> "_NullCtx":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class BackgroundThermal:
    """`with BackgroundThermal(probe): …` — samples every `interval_s` until exit."""

    def __init__(self, probe: ThermalProbe) -> None:
        self.probe = probe
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "BackgroundThermal":
        self._thread = threading.Thread(target=_probe_loop, args=(self.probe, self._stop), daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


# --- llama-server session — load once per variant, HTTP per question --------

import socket
import urllib.error
import urllib.request

LLAMA_SERVER = Path(os.environ.get("LLAMA_CPP_BIN", "/home/nvidia/llama.cpp/build/bin")) / "llama-server"


def _free_port() -> int:
    """Bind 0 and let the OS pick — avoids `--port` collisions across variants."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


class LlamaServerSession:
    """`with LlamaServerSession(gguf, ngl=99): ...` — server up for the block.

    Loads the GGUF once, exposes `model_fn(prompt) -> str` via the `/completion`
    HTTP endpoint, and tears the server down on exit. Per-question overhead
    drops from ~35-70s (subprocess reload) to ~2-5s (HTTP only).
    """

    def __init__(
        self,
        gguf_path: Path,
        *,
        n_gpu_layers: int = 99,
        ctx_size: int = 4096,
        n_predict: int = 256,
        threads: int = 8,
        startup_timeout_s: float = 180.0,
    ) -> None:
        self.gguf_path = gguf_path
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        self.n_predict = n_predict
        self.threads = threads
        self.startup_timeout_s = startup_timeout_s
        self.port = _free_port()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_fh = None

    def __enter__(self) -> "LlamaServerSession":
        log_path = Path("/tmp/g3-logs") / f"server-{self.gguf_path.stem}-{self.port}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(log_path, "wb")
        cmd = [
            str(LLAMA_SERVER),
            "-m",
            str(self.gguf_path),
            "-c",
            str(self.ctx_size),
            "-ngl",
            str(self.n_gpu_layers),
            "-t",
            str(self.threads),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=self._log_fh, stderr=subprocess.STDOUT
        )
        # Poll /health until ready (or startup_timeout_s elapses).
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"llama-server died during startup (rc={self._proc.returncode});"
                    f" see {log_path}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1.0
                ) as resp:
                    if resp.status == 200:
                        return self
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(0.5)
        raise RuntimeError(
            f"llama-server failed to come up within {self.startup_timeout_s}s"
        )

    def __exit__(self, *_exc: object) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        if self._log_fh is not None:
            self._log_fh.close()

    def model_fn(self, prompt: str) -> str:
        """Send `prompt` to /completion and return the generated text."""
        payload = json.dumps(
            {
                "prompt": prompt,
                "n_predict": self.n_predict,
                "stream": False,
                "cache_prompt": False,
                "temperature": 0.0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/completion",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return ""
        return str(body.get("content") or "").strip()


# --- One variant ------------------------------------------------------------


def measure_variant(
    variant: str,
    paths: LlamaCppPaths,
    *,
    store: LineageStore,
    f16_accuracy_ref: float | None,
    exp_counter: int,
) -> dict:
    """Run the four-axis sweep for one GGUF variant and append a lineage row."""
    gguf = QUANTS_DIR / f"model-{variant}.gguf"
    if not gguf.exists():
        print(f"  [skip] {variant}: {gguf} not present (run quantize step first)", flush=True)
        return {}

    print(f"\n=== {variant} ===", flush=True)
    t_start = time.perf_counter()

    # --- 1. wikitext-2 perplexity
    print(f"  [1/4] wikitext-2 perplexity …", flush=True)
    ppl = measure_perplexity_gguf(
        gguf_path=gguf,
        corpus_path=WIKITEXT_CORPUS,
        paths=paths,
    )
    print(f"        ppl = {ppl}", flush=True)

    # Thermal probe spans phases 2+3 so sustained_load_minutes reflects the
    # actual time under generation load, not just the <2-min llama-bench window.
    if SKIP_THERMAL:
        thermal_ctx: BackgroundThermal | _NullCtx = _NullCtx()
        probe = None
    else:
        probe = ThermalProbe(interval_s=10.0, throttle_temp_c=87.0)
        thermal_ctx = BackgroundThermal(probe)

    with thermal_ctx:
        # --- 2. llama-bench tok/s
        print(f"  [2/4] llama-bench tok/s …", flush=True)
        tps = measure_tokens_per_sec_gguf(gguf_path=gguf, paths=paths) or {}
        tg = tps.get("tg")
        pp = tps.get("pp")
        print(f"        tg={tg} pp={pp}", flush=True)

        # --- 3. Vertical-bench accuracy — [INST]-wrapped, llama-server once per variant
        fb_acc: float | None = None
        fb_n = 0
        if SKIP_VERTICAL:
            print(f"  [3/4] vertical-eval [skipped — SKIP_VERTICAL set]", flush=True)
        else:
            if VERTICAL_BENCH == "financebench":
                bench_label = f"FinanceBench (subset={FINBENCH_SUBSET}, limit={FINBENCH_LIMIT})"
                vb = VerticalBench.from_jsonl(
                    FINBENCH_JSONL,
                    format="financebench",
                    open_book=True,
                    subset=None if FINBENCH_SUBSET == "all" else FINBENCH_SUBSET,
                    limit=FINBENCH_LIMIT,
                )
                scorer = lambda pred, exp: numeric_match(pred, exp, rel_tolerance=0.01)
                wrapper = _wrap_inst
            elif VERTICAL_BENCH == "legalbench":
                bench_label = f"LegalBench (limit={LEGALBENCH_LIMIT})"
                vb = VerticalBench.from_jsonl(
                    LEGALBENCH_JSONL,
                    format="legalbench",
                    limit=LEGALBENCH_LIMIT,
                )
                scorer = contains
                wrapper = _wrap_inst
            elif VERTICAL_BENCH == "cybermetric":
                bench_label = f"CyberMetric (limit={CYBERBENCH_LIMIT})"
                vb = VerticalBench.from_jsonl(
                    CYBERBENCH_JSONL,
                    format="legalbench",
                    limit=CYBERBENCH_LIMIT,
                )
                scorer = mcq_letter
                wrapper = _wrap_zephyr
            else:  # medmcqa
                bench_label = f"MedMCQA (limit={MEDMCQA_LIMIT})"
                vb = VerticalBench.from_jsonl(
                    MEDMCQA_JSONL,
                    format="legalbench",
                    limit=MEDMCQA_LIMIT,
                )
                scorer = mcq_letter
                wrapper = _wrap_chatml
            print(
                f"  [3/4] {bench_label} via llama-server (load once per variant) …",
                flush=True,
            )
            t0 = time.perf_counter()
            scores: list[float] = []
            with LlamaServerSession(
                gguf,
                n_gpu_layers=LLAMA_CLI_NGL,
                n_predict=LLAMA_CLI_NPREDICT,
                ctx_size=int(os.environ.get("LLAMA_SERVER_CTX", "4096")),
                threads=8,
            ) as server:
                for q in vb.questions:
                    prompt = wrapper(q.question)
                    predicted = server.model_fn(prompt)
                    scores.append(scorer(predicted, q.expected))
            fb_n = len(scores)
            fb_acc = (sum(scores) / fb_n) if fb_n else None
            elapsed = time.perf_counter() - t0
            print(
                f"        {VERTICAL_BENCH} accuracy = {fb_acc} (n={fb_n}, {elapsed:.0f}s)",
                flush=True,
            )

    sustained_min = probe.sustained_load_minutes() if probe is not None else None

    # --- 4. lineage row
    delta_vs_f16 = (
        round(fb_acc - f16_accuracy_ref, 4)
        if (fb_acc is not None and f16_accuracy_ref is not None)
        else None
    )
    total_s = round(time.perf_counter() - t_start, 1)
    trial = make_variant_trial(
        exp_id=f"{exp_counter:03d}",
        variant=variant,
        timestamp=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        finance_accuracy=fb_acc,
        wikitext_perplexity=ppl,
        delta_vs_best_acc=delta_vs_f16,
        quantize_seconds=None,
        total_seconds=total_s,
        gguf_size_bytes=gguf.stat().st_size,
        tokens_per_sec_tg=tg,
        tokens_per_sec_pp=pp,
        sustained_load_minutes=sustained_min,
        status=FailureLabel.KEEP,
    )
    store.append(trial)
    print(f"  [4/4] lineage row {trial.exp_id} appended", flush=True)

    return {
        "variant": variant,
        "perplexity": ppl,
        "tg_tok_per_s": tg,
        "pp_tok_per_s": pp,
        "sustained_load_min": sustained_min,
        "financebench_accuracy": fb_acc,
        "financebench_n": fb_n,
        "gguf_bytes": gguf.stat().st_size,
        "total_s": total_s,
    }


# --- Main ------------------------------------------------------------------


def main() -> int:
    paths = LlamaCppPaths().resolve()
    LINEAGE_DIR.mkdir(parents=True, exist_ok=True)
    store = LineageStore(LINEAGE_DIR, lower_is_better=False)

    # Pull F16 first if present so the delta_vs_best for other variants is meaningful.
    ordered = sorted(QUANT_VARIANTS, key=lambda v: 0 if v == "F16" else 1)
    f16_acc: float | None = None
    results: list[dict] = []
    for i, variant in enumerate(ordered):
        # exp_ids 001..N (000 is the baseline row, see lineage-demo.py)
        out = measure_variant(
            variant,
            paths,
            store=store,
            f16_accuracy_ref=f16_acc,
            exp_counter=i + 1,
        )
        if out and variant == "F16":
            f16_acc = out.get("financebench_accuracy")
        if out:
            results.append(out)

    # --- Compatibility shim: also write the measurements.json shape the
    # existing publish-dryrun step expects (perplexity dict + tok/s dict).
    measurements_path = QUANTS_DIR / "measurements.json"
    QUANTS_DIR.mkdir(parents=True, exist_ok=True)
    fb_n_first = next(
        (r.get("financebench_n", 0) for r in results if r.get("financebench_n")),
        0,
    )
    if VERTICAL_BENCH == "financebench":
        vertical_eval_name = (
            f"FinanceBench (n={fb_n_first}, numeric_match)" if fb_n_first else None
        )
    elif VERTICAL_BENCH == "legalbench":
        vertical_eval_name = (
            f"LegalBench (n={fb_n_first}, contains)" if fb_n_first else None
        )
    elif VERTICAL_BENCH == "cybermetric":
        vertical_eval_name = (
            f"CyberMetric (n={fb_n_first}, mcq_letter)" if fb_n_first else None
        )
    else:  # medmcqa
        vertical_eval_name = (
            f"MedMCQA (n={fb_n_first}, mcq_letter)" if fb_n_first else None
        )
    payload = {
        "perplexity": {r["variant"]: r["perplexity"] for r in results if r.get("perplexity") is not None},
        "tokens_per_sec": {
            r["variant"]: {"tg": r.get("tg_tok_per_s"), "pp": r.get("pp_tok_per_s")}
            for r in results
        },
        "sustained_load_minutes": {
            r["variant"]: r.get("sustained_load_min") for r in results
        },
        "financebench_accuracy": {
            r["variant"]: r.get("financebench_accuracy") for r in results
        },
        "financebench_n": {r["variant"]: r.get("financebench_n", 0) for r in results},
        "vertical_eval_name": vertical_eval_name,
        "gguf_bytes": {r["variant"]: r.get("gguf_bytes", 0) for r in results},
    }
    measurements_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {measurements_path}")
    print(f"wrote {LINEAGE_DIR}/results.tsv  ({len(results)} variant rows appended)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
