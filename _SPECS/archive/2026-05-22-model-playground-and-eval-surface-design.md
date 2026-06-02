# Design — Model playground + comprehensive eval surface for Orionfold's 6 GGUF quants

**Date:** 2026-05-22 · **Constraint:** strictly $0/month-ongoing · **Audience:** tiered (prospects + researchers)

## Context

The site already catalogs **9 Orionfold artifacts** (6 GGUF quants — `finance-chat-gguf`, `ii-medical-8b-gguf`, `saul-7b-instruct-v1-gguf`, `securityllm-gguf`, `patent-strategist-v3-nemo-gguf`, `patent-strategist-v3-unsloth-gguf` — plus 2 LoRAs and 1 bench). Every detail page links out to HuggingFace, but **zero interactive inference, embedded demo, or off-the-shelf benchmark surface** exists today. All eval rendering is offline-computed (`vertical_eval` field per quant, e.g. "FinanceBench n=50 numeric_match") and static. The site does not yet tell prospects "try this in one click" or tell researchers "reproduce these scores in a notebook."

The user wants to add both: a hosted playground (free), comprehensive standardized evals (free), and a bring-your-own-prompt path. Constraint is **$0/month-ongoing**; tiered audience means we serve both a casual "tap to try" prospect and a "reproduce my eval" researcher.

The dominant external constraint that shapes everything below: of the ~12 free-tier platforms surveyed, **only HuggingFace Spaces CPU Basic** accepts arbitrary GGUF for hosted inference at $0/month (Cloudflare Workers AI is catalog-only; ZeroGPU requires HF Pro $9/mo to create a Space; Modal/Replicate/Lightning are credit-capped). Free GPU lives in *notebooks* — Google Colab T4 and Kaggle T4×2. So the tiered design isn't a stylistic choice; it's the shape the free-tier landscape forces.

## Recommended approach (two tiers, three deliverables)

### Tier A — Prospect playground: one HF Space, six models, slow but live

- **One** Space at `Orionfold/playground` (CPU Basic, 2 vCPU / 16 GB, $0/mo, sleeps after 48h idle)
- Gradio Blocks UI with **model dropdown** (6 models) + prompt input + output panel + 3 curated example prompts per model
- Inference via `llama-cpp-python` using **prebuilt wheels** ([Luigi/llama-cpp-python-wheels-hf-spaces-free-cpu](https://huggingface.co/Luigi/llama-cpp-python-wheels-hf-spaces-free-cpu)) — avoids the well-known build-timeout pitfall
- **Q4_K_M only** (smallest variant; 6 × 4-5 GB fits with lazy loading); accept ~3-7 tok/s
- Embedded into a new Astro page `/playground/` via the HF [Spaces embed](https://huggingface.co/docs/hub/en/spaces-embed) WebComponent (auto-sizes; superior to raw iframe)
- **Static fallback** on `/playground/`: each of the 6 example prompts has a pre-computed cached output rendered in MDX so the page is useful even when the Space is sleeping (cold-wake is 30-90 s)

### Tier B — Researcher reproducibility: one notebook, six repo roots, free GPU

- Author **one parameterized `notebook.ipynb`** that takes a `model_id` argument and runs the model's full benchmark suite
- **Copy** this notebook to the root of each of the 6 Orionfold HF model repos — that automatically generates the "Open in Colab" button on each model card ([HF notebooks docs](https://huggingface.co/docs/hub/main/en/notebooks))
- Notebook uses **lm-evaluation-harness** (`pip install lm-eval`) with the GGUF backend (`--model hf --model_args gguf_file=<file>,pretrained=Orionfold/<repo>`). Colab free T4 (16 GB) easily runs 8B Q5_K_M with `--n-gpu-layers -1`.
- Add an **"Open in Kaggle" badge** alongside (Kaggle gives 30 hr/wk T4×2; primary fallback when Colab T4 is unavailable)
- A sibling notebook `notebook-custom.ipynb` runs **Inspect AI** for the bench artifacts where lm-eval lacks tasks (patent-strategist-bench, FinanceBench public-150, HealthSearchQA judge-LLM)
- **SecurityLLM** gets one additional notebook `notebook-redteam.ipynb` running **Garak** (Apache-2.0; v0.15.0 May 2026 adds prompt-injection + system-prompt-extraction probes) and emitting an HTML report

### Tier C — Eval display: extend the existing artifact pages, add /evals/ leaderboard

- Extend the **artifact manifest schema** (`src/content.config.ts`) with a new optional `benchmarks[]` array carrying off-the-shelf eval scores per benchmark per variant. Mirror byte-faithfully on source per the established sync pattern.
- New component **`BenchmarkScoreTable.astro`** under `src/components/artifacts/`, modeled after existing `BenchBracketTable.astro`. Renders per-benchmark rows × per-variant columns.
- Quant detail page (`src/pages/artifacts/quants/[slug]/index.astro`) gains a **"Standardized benchmarks"** section between the existing "Spark vertical eval" and "Drift" sections. Renders the new component when `benchmarks[]` populated, no-ops otherwise (matches existing graceful-fallback pattern set by `positioning`/`siblings`/`known_drift`).
- New page **`/evals/` index** rendering one row per model × shared columns (e.g., MMLU-Pro subset scores across all 6) — a vertical-domain leaderboard.
- Each artifact page gains a **"Try in Playground / Reproduce in Colab"** CTA pair pointing to `/playground/` and to the HF Space's API (or to the model's HF page where the Open-in-Colab button lives natively).

## Eval framework spine

| Layer | Framework | What it covers | Why this one |
|---|---|---|---|
| Standardized MCQ + Q&A | **EleutherAI lm-evaluation-harness** | MMLU subsets, MedQA, MedMCQA, PubMedQA, MultiMedQA, LegalBench, LexGLUE, CaseHOLD, BillSum | The only major harness with **GGUF as a first-class backend**; reproducible in Colab T4 |
| Finance-specific | **lighteval** | FinBen/PIXIU tasks (FPB, FiQA, FinQA, ConvFinQA) | Lighter than the harness for finance subset; same notebook |
| Custom + judge-LLM | **Inspect AI** (UK AISI) | patent-strategist-bench, FinanceBench-150, HealthSearchQA, CyberSecEval orchestration | 200+ pre-built evals; judge-LLM support; web result viewer screenshots cleanly |
| Security red-team | **Garak** (NVIDIA) | Prompt-injection, jailbreak, encoding probes for SecurityLLM | Apache-2.0; HTML report embeds well on a marketing page |

**Explicitly NOT adopted:** HELM (enters maintenance June 2026); OpenAI Evals (OpenAI-coupled, weak on local GGUF); DeepEval/promptfoo (app-layer, not benchmark-layer).

## Per-model benchmark matrix (MUST-launch only)

| Model | MUST benchmarks |
|---|---|
| `finance-chat-gguf` | FinanceBench-public-150, FinQA, FPB sentiment |
| `ii-medical-8b-gguf` | MedQA, MedMCQA, PubMedQA, MMLU{clinical-knowledge, medical-genetics}, MultiMedQA group |
| `saul-7b-instruct-v1-gguf` | LegalBench (curated ~20 commercially-clean tasks), LexGLUE, CaseHOLD, MMLU professional-law |
| `securityllm-gguf` | CyberSecEval (insecure-code + prompt-injection subsets), Garak (4-6 probes), MMLU computer-security |
| `patent-strategist-v3-{nemo,unsloth}-gguf` | patent-strategist-bench-v0.1 (own), BIGPATENT (ROUGE), PatentMatch (binary) |

**Hard skips (license blockers):** TAT-QA (CC-BY-NC), ContractNLI (CC-BY-NC), Pile-of-Law eval (CC-BY-NC-SA), BloombergGPT eval (not public). LegalBench requires **per-task curation** (mixed licenses — ~20 tasks are commercial-clean).

## Bring-your-own-prompt UX

The Tier A HF Space *is* the BYOP surface — the model dropdown + prompt input is a generic interface, not a fixed-example demo. Layered fallback:
1. **Primary:** Embedded Space at `https://orionfold-playground.hf.space` (Gradio Blocks, sequential generation, rate-limited)
2. **Secondary:** "Open in Colab" badge → loads a `notebook-byop.ipynb` with `llama-cpp-python` + a Gradio share link (free T4 GPU; user enters prompt, gets full-speed inference)
3. **Static fallback:** Pre-computed canonical prompts cached as MDX (~6 prompts × 6 models = 36 short outputs; page works during 48h sleep)

## Critical files

**Destination side (this repo — `/Users/manavsehgal/Developer/ainative-business.github.io/`):**
- `src/content.config.ts:111-208` — extend `artifacts` Zod schema with `benchmarks[]` (mirror source-side change byte-for-byte)
- `src/components/artifacts/BenchmarkScoreTable.astro` — **new**; pattern from `BenchBracketTable.astro`
- `src/components/artifacts/PlaygroundCTA.astro` — **new**; renders the Try/Reproduce CTA pair
- `src/pages/artifacts/quants/[slug]/index.astro` — add "Standardized benchmarks" section + PlaygroundCTA (after line 67's `sweetSpot`/before drift section); graceful no-op when `benchmarks[]` empty
- `src/pages/playground/index.astro` — **new**; HF Space `<gradio-app>` embed + static fallback grid
- `src/pages/playground/cached-outputs.json` — **new**; 36 cached outputs (6 prompts × 6 models)
- `src/pages/evals/index.astro` — **new**; cross-model leaderboard rendering shared benchmarks
- `scripts/verify_artifact_rendering.mjs` — extend the post-build verifier to assert "Standardized benchmarks" section renders when `benchmarks[]` populated
- `src/data/seo.ts` + `src/components/Nav.astro` — add `/playground/` and `/evals/` nav entries (light-theme-first per `feedback_light_theme.md`); use **trailing slashes** in links per `feedback_trailing_slashes.md`

**Source side (ai-field-notes, via NFS mount when reachable):**
- `src/content.config.ts` — mirror the `benchmarks[]` Zod addition
- `fieldkit/src/fieldkit/eval/harness_runner.py` — **new**; thin wrapper around `lm-eval` that emits the manifest-shaped `benchmarks[]` array (reuses the existing `Bench`/`Judge` primitives noted in fieldkit quickstart)
- `notebooks/notebook-standardized.ipynb` — **new** parameterized notebook (lm-eval-harness)
- `notebooks/notebook-custom.ipynb` — **new** (Inspect AI)
- `notebooks/notebook-redteam.ipynb` — **new** (Garak — SecurityLLM only)
- `notebooks/notebook-byop.ipynb` — **new** (Colab Gradio share link for BYOP)
- `playground-space/app.py` — **new**; Gradio Blocks + llama-cpp-python prebuilt wheels (deploys to `Orionfold/playground`)
- `playground-space/requirements.txt` — **new**; pins to the prebuilt-wheels index
- For each of 6 Orionfold HF model repos: copy `notebook-standardized.ipynb` to repo root + add Open-in-Colab/Kaggle badges to README (hf-publisher skill territory)
- `_GUIDES/NARRATIVE-CONTRACT.md` — extend to cover the "benchmarks block" surface (so HF cards and site stay in sync)

## Phasing (validates cheaply before fanning out)

**Phase 1 — destination scaffolding (this repo, ~1 day):** Schema extension, BenchmarkScoreTable component, `/playground/` page with placeholder iframe + static fallback for **one** model, `/evals/` page skeleton, verifier extension. Ship behind a single commit so layout/contrast/perf can be browser-checked (per `feedback_pagespeed_techniques.md`).

**Phase 2 — single-model proof (source + HF, ~2 days):** Stand up `Orionfold/playground` with **Saul-7B-Instruct only** (best published baseline per research: 0.61 LegalBench-Instruct). Author standardized + custom notebook for Saul. Run lm-eval + Inspect AI; populate Saul's manifest `benchmarks[]`. Verify end-to-end: Space loads, notebook reproduces, destination page renders.

**Phase 3 — fan-out (source, ~3-5 days):** Add the other 5 models to the Space dropdown. Run benchmarks for each (MUST list above). Copy notebook to each HF model repo root. Populate manifests. Run a `/sync-field-notes` cycle to pull updates to destination.

**Phase 4 — leaderboard + red-team (source, ~1-2 days):** Build `/evals/` index data, run Garak for SecurityLLM, embed HTML report, finalize cross-model comparison view.

## Verification

- **Build clean:** `npm run build` exits 0; `verify_artifact_rendering.mjs` passes for all 9 artifacts including the new benchmarks section.
- **Browser live-check** via `claude-in-chrome` MCP: `npm run dev`, then load `/playground/`, `/evals/`, `/artifacts/quants/saul-7b-instruct-v1-gguf/`. Confirm iframe loads, dropdown switches models, fallback renders during sleep simulation.
- **Lighthouse + WCAG AA** on `/playground/` (the new heavy page) — light-theme primary, contrast checked.
- **Reproducibility:** Open the notebook in Colab T4 from `huggingface.co/Orionfold/saul-7b-instruct-v1-GGUF` (via Open-in-Colab button), run all cells, confirm emitted JSON matches the manifest's `benchmarks[]` values for `saul-7b-instruct-v1-gguf` within scoring tolerance.
- **Cold-start UX:** Hit the Space after >48h idle; confirm 30-90s wake; confirm `/playground/` static fallback is useful in the meantime.
- **API surface:** HF Spaces auto-expose an API endpoint ([docs](https://huggingface.co/docs/hub/en/spaces-api-endpoints)); confirm `gradio_client.Client("Orionfold/playground").predict(...)` works — this is the door open for future client-side BYOP without a separate inference service.

## Non-goals (explicit descope)

- ❌ Multiple Spaces (one per model) — wastes the org's 10-Space soft cap and confuses navigation. Single Space + dropdown.
- ❌ ZeroGPU / paid HF Pro / Inference Endpoints — violates $0/mo constraint.
- ❌ Custom inference proxy on Vercel/Netlify/Cloudflare — function timeouts can't load 5+ GB GGUF; no GPU.
- ❌ HELM as an eval spine — enters maintenance June 2026.
- ❌ A "live A/B model comparison" UI on the site — defer; the single-model dropdown is the launch surface.
- ❌ Hosting the patent-strategist BF16 LoRAs (16 GB merged weights) in the playground — too large for CPU Basic RAM; the playground is GGUF-only, the LoRA variants stay download-only.
- ❌ Auto-running evals on a schedule — all eval runs are author-triggered; no cron, no GitHub Actions for paid compute.

## Risks

- **HF Spaces 48h sleep + cold-start ~90s** can feel broken to first-time prospects. Mitigation: static fallback grid + visible "Wake up the model (~90s)" CTA + cached example outputs.
- **6 GGUF models lazily loaded in 16 GB RAM** is tight (4-5 GB each at Q4_K_M); risk of OOM when switching. Mitigation: unload-on-switch in the Gradio app; benchmark RAM headroom before publishing.
- **LegalBench license curation** is real work — 162 tasks, mixed per-task licenses. Mitigation: start with the Stanford-blessed "instruct" subset (~20 tasks) Saul itself was evaluated on.
- **Source/destination schema drift** if the `benchmarks[]` field is added on destination first. Mitigation: write the source-side Zod change before destination merges (NFS-mount writes; same pattern as the 2026-05-22 _GUIDES/NARRATIVE-CONTRACT.md edit).
- **CC-NC blunder** if anyone copies TAT-QA / ContractNLI / Pile-of-Law scores into the marketing-facing benchmark grid. Mitigation: hard `LICENSE_ALLOWLIST` constant in `fieldkit/eval/harness_runner.py`; refuse to write disallowed tasks into manifests.

## Open questions for the user before execution

1. **Phase 1 ship target** — Phase 1 as a standalone PR with placeholder data, or wait until Phase 2 has real Saul-7B scores so the first commit shows the full surface? (Recommendation: Phase 1 standalone — gives a browser-verifiable scaffold and unblocks source-side work to populate.)
2. **`/playground/` vs `/try/` URL** — playground/ is conventional; try/ is shorter. Either fits the existing trailing-slash convention.
3. **One Space or split prospect/researcher?** — recommendation is **one Space** with the dropdown (simpler nav, single API endpoint for future BYOP). Alternative: a "lite" Space for the marketing iframe + a separate "researcher" Space with all variants. Defer the split until a real performance/quota signal forces it.
