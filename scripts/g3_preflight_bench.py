#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""V0 preflight gate — score 5 vertical-bench questions on FP-source weights.

Runs *before* the B4 quantize+measure sweep to catch the
chat-vs-continued-pretrain trap (per `feedback_chat_vs_continued_pretrain_trap`
+ `feedback_preflight_bench_before_quant`). Produces an F16 GGUF via
`convert_hf_to_gguf.py` (which IS the FP source representation in the GGUF
ecosystem — no quantization happens here), spins up llama-server on GPU, runs
5 vertical-bench questions, scores per-bench (`numeric_match` for finance,
`contains` for legal, `mcq_letter` for cyber), exits 0 on
≥ PREFLIGHT_MIN/PREFLIGHT_N or 1 on fewer correct.

The F16 GGUF this step produces is the same file B4 emits for the `F16`
variant — so V0 is a strict subset of B4 work, not extra overhead. On failure
we abort before the multi-hour `Q4_K_M/Q5_K_M/Q6_K/Q8_0` quantization sweep.

Why GGUF instead of `transformers`: GB10 has unified memory + GPU. Loading
the FP16 source via transformers on CPU is ~3 tok/s (single-question wall
~30s for 256 toks). Loading the F16 GGUF on GPU is ~10 tok/s (single-question
~25s) plus a one-time ~5min convert. For five questions the GGUF path is
already cheaper, and for the next retry (when the GGUF is cached) it's
~30 sec end-to-end vs ~30 minutes on CPU fp32.

Inputs (env, mirrors `g3_build_first_quant.sh` defaults):

    MODELS_DIR      /home/nvidia/data/models
    MODEL_SLUG      basename of MODEL_ID
    QUANTS_DIR      /home/nvidia/data/quants
    LLAMA_CPP_BIN   /home/nvidia/llama.cpp/build/bin
    LLAMA_CPP_CONVERT
                    /home/nvidia/llama.cpp/convert_hf_to_gguf.py
    BASE_MODEL_ARG  HF repo id (for GGUF metadata only)
    VERTICAL_BENCH  financebench (default) | legalbench | cybermetric | medmcqa
    FINBENCH_JSONL  /home/nvidia/data/eval-benches/financebench/financebench_merged.jsonl
    FINBENCH_SUBSET metrics-generated
    LEGALBENCH_JSONL
                    /home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl
    CYBERBENCH_JSONL
                    /home/nvidia/data/eval-benches/cybermetric/cybermetric_merged.jsonl
    MEDMCQA_JSONL
                    /home/nvidia/data/eval-benches/medmcqa/medmcqa_merged.jsonl
    PREFLIGHT_N     5
    PREFLIGHT_MIN   1
    PREFLIGHT_N_PREDICT
                    256
    PREFLIGHT_NGL   99    (GPU layers; 99 = all)
    PREFLIGHT_CTX   4096

Exit codes:
    0 — pass (≥ PREFLIGHT_MIN correct out of PREFLIGHT_N)
    1 — fail (model + format pairing broken — re-pick)
    2 — preflight could not run (missing weights / bench / llama.cpp)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "fieldkit" / "src"))

from fieldkit.eval import VerticalBench, contains, numeric_match  # noqa: E402


# --- MCQ-letter scorer (cybermetric, MCQ-shape verticals) ---------------
# Promoted to `fieldkit.eval.mcq_letter` after three vertical-bench reuses
# (cyber, medical, patent-strategist) per
# [[feedback_keep_scorer_local_until_reuse]]. The fieldkit version has a
# `strip_think=True` default that no-ops on text without `<think>` tags, so
# this import is byte-for-byte compatible with the previous local copy.

from fieldkit.eval import mcq_letter  # noqa: E402


def _log(msg: str) -> None:
    print(f"[preflight] {msg}", flush=True)


def _die(msg: str, code: int = 2) -> None:
    print(f"[preflight FATAL] {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def _free_port() -> int:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _detect_prompt_format(model_dir: Path) -> str:
    """Pick the right chat-template wrapper for the source weights.

    Llama-2-chat models historically ship no `chat_template` in
    tokenizer_config.json — the convention is `<s>[INST] X [/INST]`. The
    README is the most reliable signal that the upstream is Llama-2-chat
    (e.g. AdaptLLM's continued-pretrain-from-Llama-2-chat recipe).

    Returns: `llama2_inst` (Llama-2-chat), `mistral_inst` (Mistral-Instruct /
    Saul), `zephyr` (ZySec-AI/SecurityLLM and other Zephyr-DPO descendants),
    `tokenizer_template` (chat_template present but format unrecognised), or
    `raw` (no chat-format signal — continued-pretrain trap risk).
    """
    readme = model_dir / "README.md"
    if readme.exists():
        txt = readme.read_text(errors="ignore").lower()
        if "llama-2-chat" in txt or "llama2-chat" in txt or "[inst]" in txt:
            return "llama2_inst"
    tok_cfg = model_dir / "tokenizer_config.json"
    if tok_cfg.exists():
        try:
            cfg = json.loads(tok_cfg.read_text())
            ct = cfg.get("chat_template")
            if ct:
                if "<|im_start|>" in ct:
                    return "chatml"
                if "<|user|>" in ct and "<|assistant|>" in ct:
                    return "zephyr"
                if "[INST]" in ct:
                    return "mistral_inst"
                return "tokenizer_template"
        except Exception:
            pass
    return "raw"


def _format_prompt(question: str, fmt: str) -> str:
    if fmt in ("llama2_inst", "mistral_inst"):
        return f"<s>[INST] {question.strip()} [/INST]"
    if fmt == "zephyr":
        return f"<|user|>\n{question.strip()}</s>\n<|assistant|>\n"
    if fmt == "chatml":
        return f"<|im_start|>user\n{question.strip()}<|im_end|>\n<|im_start|>assistant\n"
    return question.strip()


def _convert_to_f16_gguf(
    *,
    model_dir: Path,
    out_path: Path,
    convert_script: Path,
    base_model_id: str | None,
) -> None:
    """Run `convert_hf_to_gguf.py --outtype f16 --outfile <out>`."""
    if out_path.exists():
        _log(f"reusing existing F16 GGUF at {out_path}")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(convert_script),
        str(model_dir),
        "--outfile",
        str(out_path),
        "--outtype",
        "f16",
    ]
    _log(f"converting {model_dir.name} → F16 GGUF (this can take ~5 min)")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-2000:] + "\n" + proc.stderr[-2000:] + "\n")
        _die(f"convert_hf_to_gguf failed (rc={proc.returncode})")
    _log(f"convert OK in {time.perf_counter() - t0:.1f}s → {out_path}")


class LlamaServerSession:
    """Spin up `llama-server` on a free port and tear it down on exit."""

    def __init__(
        self,
        *,
        gguf_path: Path,
        llama_server_bin: Path,
        n_gpu_layers: int = 99,
        ctx_size: int = 4096,
        n_predict: int = 256,
        threads: int = 8,
        startup_timeout_s: float = 180.0,
    ) -> None:
        self.gguf_path = gguf_path
        self.llama_server_bin = llama_server_bin
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        self.n_predict = n_predict
        self.threads = threads
        self.startup_timeout_s = startup_timeout_s
        self.port = _free_port()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_fh = None

    def __enter__(self) -> "LlamaServerSession":
        log_path = Path("/tmp/g3-logs") / f"preflight-server-{self.gguf_path.stem}-{self.port}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(log_path, "wb")
        cmd = [
            str(self.llama_server_bin),
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
        self._proc = subprocess.Popen(cmd, stdout=self._log_fh, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"llama-server died during startup (rc={self._proc.returncode}); see {log_path}"
                )
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1.0) as resp:
                    if resp.status == 200:
                        return self
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(0.5)
        raise RuntimeError(f"llama-server failed to come up within {self.startup_timeout_s}s")

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

    def complete(self, prompt: str) -> str:
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
            with urllib.request.urlopen(req, timeout=180.0) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            _log(f"  HTTP error: {type(exc).__name__}: {exc}")
            return ""
        return str(body.get("content") or "").strip()


def main() -> int:
    models_dir = Path(os.environ.get("MODELS_DIR", "/home/nvidia/data/models"))
    quants_dir = Path(os.environ.get("QUANTS_DIR", "/home/nvidia/data/quants"))
    model_slug = os.environ.get("MODEL_SLUG") or _die("MODEL_SLUG env required") or ""
    base_model_arg = os.environ.get("BASE_MODEL_ARG") or os.environ.get("MODEL_ID")
    llama_cpp_bin = Path(os.environ.get("LLAMA_CPP_BIN", "/home/nvidia/llama.cpp/build/bin"))
    llama_convert = Path(
        os.environ.get("LLAMA_CPP_CONVERT", "/home/nvidia/llama.cpp/convert_hf_to_gguf.py")
    )
    vertical = os.environ.get("VERTICAL_BENCH", "financebench").lower()
    if vertical not in ("financebench", "legalbench", "cybermetric", "medmcqa"):
        _die(
            f"VERTICAL_BENCH must be 'financebench' / 'legalbench' / 'cybermetric' / 'medmcqa', "
            f"got {vertical!r}"
        )
    finbench_jsonl = Path(
        os.environ.get(
            "FINBENCH_JSONL",
            "/home/nvidia/data/eval-benches/financebench/financebench_merged.jsonl",
        )
    )
    legalbench_jsonl = Path(
        os.environ.get(
            "LEGALBENCH_JSONL",
            "/home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl",
        )
    )
    cyberbench_jsonl = Path(
        os.environ.get(
            "CYBERBENCH_JSONL",
            "/home/nvidia/data/eval-benches/cybermetric/cybermetric_merged.jsonl",
        )
    )
    medmcqa_jsonl = Path(
        os.environ.get(
            "MEDMCQA_JSONL",
            "/home/nvidia/data/eval-benches/medmcqa/medmcqa_merged.jsonl",
        )
    )
    subset = os.environ.get("FINBENCH_SUBSET", "metrics-generated")
    n = int(os.environ.get("PREFLIGHT_N", "5"))
    min_correct = int(os.environ.get("PREFLIGHT_MIN", "1"))
    n_predict = int(os.environ.get("PREFLIGHT_N_PREDICT", "256"))
    n_gpu_layers = int(os.environ.get("PREFLIGHT_NGL", "99"))
    ctx_size = int(os.environ.get("PREFLIGHT_CTX", "4096"))

    model_dir = models_dir / model_slug
    f16_gguf = quants_dir / model_slug / f"model-F16.gguf"
    llama_server_bin = llama_cpp_bin / "llama-server"

    if not (model_dir / "config.json").exists():
        _die(f"model weights not found at {model_dir} (run `g3_build_first_quant.sh download` first)")
    if vertical == "financebench" and not finbench_jsonl.exists():
        _die(f"FinanceBench JSONL not found at {finbench_jsonl}")
    if vertical == "legalbench" and not legalbench_jsonl.exists():
        _die(f"LegalBench JSONL not found at {legalbench_jsonl} (run `python3 scripts/legalbench_merge.py` first)")
    if vertical == "cybermetric" and not cyberbench_jsonl.exists():
        _die(f"CyberMetric JSONL not found at {cyberbench_jsonl} (run `python3 scripts/cyber_merge.py` first)")
    if vertical == "medmcqa" and not medmcqa_jsonl.exists():
        _die(f"MedMCQA JSONL not found at {medmcqa_jsonl} (run `python3 scripts/medmcqa_merge.py` first)")
    if not llama_server_bin.exists():
        _die(f"llama-server not found at {llama_server_bin} (build llama.cpp first)")
    if not llama_convert.exists():
        _die(f"convert_hf_to_gguf.py not found at {llama_convert}")

    _convert_to_f16_gguf(
        model_dir=model_dir,
        out_path=f16_gguf,
        convert_script=llama_convert,
        base_model_id=base_model_arg,
    )

    fmt = _detect_prompt_format(model_dir)
    _log(f"prompt format: {fmt}")
    if fmt == "raw":
        _log("WARN: no chat-format signal found — likely continued-pretrain trap")
        _log("      proceeding anyway; scorer will return 0 if outputs aren't formatted")

    if vertical == "financebench":
        vb = VerticalBench.from_jsonl(
            finbench_jsonl,
            format="financebench",
            open_book=True,
            subset=None if subset == "all" else subset,
            limit=n,
        )
        scorer = lambda pred, exp: numeric_match(pred, exp, rel_tolerance=0.01)
        bench_label = f"FinanceBench subset={subset}"
    elif vertical == "legalbench":
        vb = VerticalBench.from_jsonl(legalbench_jsonl, format="legalbench", limit=n)
        scorer = contains
        bench_label = "LegalBench"
    elif vertical == "cybermetric":  # shares legalbench's {id,text,answer,task} JSONL shape
        vb = VerticalBench.from_jsonl(cyberbench_jsonl, format="legalbench", limit=n)
        scorer = mcq_letter
        bench_label = "CyberMetric MCQ"
    else:  # medmcqa — same legalbench JSONL shape, mcq_letter scorer (second reuse)
        vb = VerticalBench.from_jsonl(medmcqa_jsonl, format="legalbench", limit=n)
        scorer = mcq_letter
        bench_label = "MedMCQA"
    if not vb.questions:
        _die(f"no questions loaded for {bench_label}")
    _log(f"scoring {len(vb.questions)} questions from {bench_label}")

    correct = 0
    with LlamaServerSession(
        gguf_path=f16_gguf,
        llama_server_bin=llama_server_bin,
        n_gpu_layers=n_gpu_layers,
        ctx_size=ctx_size,
        n_predict=n_predict,
    ) as server:
        for i, q in enumerate(vb.questions, start=1):
            prompt = _format_prompt(q.question, fmt)
            t_q = time.perf_counter()
            predicted = server.complete(prompt)
            elapsed = time.perf_counter() - t_q
            score = scorer(predicted, q.expected)
            correct += int(score)
            _log(
                f"  Q{i}/{len(vb.questions)} [{elapsed:.1f}s] qid={q.qid} "
                f"expected={q.expected[:80]!r} predicted={predicted[:200]!r} score={score:.0f}"
            )

    _log(f"score: {correct}/{len(vb.questions)} (threshold ≥ {min_correct})")
    if correct >= min_correct:
        _log("PASS — proceed with quantize+measure")
        return 0
    _log("FAIL — model + format pairing broken — re-pick")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[preflight FATAL] unhandled: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
