# Learning-objectives matrix — ai-field-notes

A topic-aware coverage map for the ai-field-notes blog. Eleven learning objectives in dependency order, foundations → evaluation. The audience is a **DGX Spark personal power user / edge AI builder** — someone running real AI workloads on one machine they own, who wants to understand both the underlying mechanisms and the NVIDIA products that operationalize them.

## How to use this reference

- **Optional, not a gate.** Articles outside this matrix are welcome. The matrix exists to make coverage gaps visible and to give the tech-writer skill a menu when the user wants one.
- **Cite by topic number** in the editorial overlay when it applies: *"Topic 3 — inference economics, decomposed on one DGX Spark."*
- **`Covered in:`** tracks which existing articles partially touch a topic. Maintained by hand; update it when a new article ships.
- **Every topic is framed for the DGX-Spark-builder audience.** The matrix is about products and mechanisms — not business angle, not ecosystem dynamics, not revenue motions. If a scope statement starts to read like a marketing brief, rewrite it.

---

## Topic 1 — Transformers & Attention

**Scope.** Understand Q/K/V attention, the O(n²) scaling law, and why this single equation shapes every optimization (KV cache, FlashAttention, PagedAttention, quantization) a power user encounters on-device.

**NVIDIA touchpoints.** TransformerEngine (FP8 kernels), TensorRT-LLM (attention-kernel fusion), NeMo (training on NVIDIA hardware), the CUDA-level context every later topic inherits.

**Dependencies.** None — foundation.

**Stage (frontmatter).** `foundations`.

**Covered in.** — (Nemotron-3-Super architecture referenced in `articles/nemoclaw-vs-openclaw-dgx-spark/`, not taught)

---

## Topic 2 — How Models Get Made: Pre-training → SFT → RLHF/DPO

**Scope.** The three-stage training pipeline and the cost asymmetry that shapes it (pre-training $10M+, SFT $10K–$1M, PEFT $100–$10K, inference pennies-per-query). Where a DGX Spark owner actually sits on that curve — which is SFT and PEFT, not pre-training. How the training objective changes at each stage (next-token loss → instruction-following on curated pairs → preference ranking via DPO/RLHF).

**NVIDIA touchpoints.** NeMo Framework (full lifecycle, 3D parallelism), NeMo Curator (dedup, quality filter, PII removal, synthetic data generation), NeMo Customizer (productized SFT / LoRA / DPO), TransformerEngine + FP8 for training throughput.

**Dependencies.** Topic 1.

**Stage.** `training`.

**Covered in.** —

---

## Topic 3 — Inference Economics & Optimization

**Scope.** The two-phase nature of LLM inference (compute-bound **prefill** vs. memory-bound **decode**), the KV cache as the central constraint, and the optimization stack ordered by leverage on a single-node Spark: continuous batching, PagedAttention, quantization (FP8 / INT8 / INT4), speculative decoding, kernel fusion. The TTFT-vs-TPOT tension and why it defines SLAs.

**NVIDIA touchpoints.** TensorRT-LLM (kernel fusion, FP8, speculative decoding, in-flight batching), Triton Inference Server (serving runtime), NIMs (packaged inference containers); vLLM as the open-source alternative running on the same NVIDIA GPUs.

**Dependencies.** Topics 1–2.

**Stage.** `inference`.

**Covered in.** Partial — `articles/nemoclaw-vs-openclaw-dgx-spark/` (latency decomposition, proxy-hop overhead, steady-state tok/s, cold-load mmap time for Q4_K_M models on Spark).

---

## Topic 4 — Retrieval-Augmented Generation (RAG)

**Scope.** The five-step mechanism (chunk → embed → index → retrieve → augment), why naive RAG breaks (embedding gap, top-K bluntness, chunking destroys context, no cross-chunk reasoning), and the fix ladder: hybrid search, reranking, query rewriting / HyDE, semantic chunking, metadata filtering. How to evaluate retrieval quality **separately** from generation quality (recall@K and MRR vs. faithfulness and answer relevance).

**NVIDIA touchpoints.** NeMo Retriever (embedding + reranker models, ships as NIMs), NeMo Guardrails (PII filtering on retrieved context), NeMo Curator for ingestion pipelines; open-source vector stores (pgvector, Milvus, Weaviate) running on the Spark or next to it.

**Dependencies.** Topic 3.

**Stage.** `inference`.

**Covered in.** —

---

## Topic 5 — Agents & Multi-Turn Tool Use

**Scope.** The ReAct loop (thought → action → observation → done), tool design as API design (few, well-named, composable, clear failure modes), the three memory tiers (context window vs. working memory vs. long-term-which-is-really-RAG), planning patterns (ReAct / plan-and-execute / tree search / hierarchical), and the failure modes that separate a toy from a product: infinite loops, context explosion, tool hallucination, goal drift, non-determinism.

**NVIDIA touchpoints.** NeMo Agent Toolkit (agent-building blocks), open-source frameworks layered on NVIDIA inference (LangGraph, AutoGen, CrewAI), agent-serving NIMs. Bridges to Topic 6 via MCP for tool access.

**Dependencies.** Topics 1–4.

**Stage.** `agentic`.

**Covered in.** Partial — `articles/nemoclaw-vs-openclaw-dgx-spark/` (agent-framework overhead on Spark, sandbox vs. host, onboarding tax, ~26 s steady-state tax decomposed into proxy hop + OpenAI-compat wrapping + k3s routing + tool loop).

---

## Topic 6 — Interoperability Protocols: MCP & A2A

**Scope.** **Model Context Protocol** (Anthropic, Nov 2024 — JSON-RPC + capability negotiation for agent↔tool access; the "LSP for AI") vs. **Agent-to-Agent Protocol** (Google, April 2025 — Agent Cards, task lifecycles, opaque delegation). Where each applies, why they are complementary (MCP = function call, A2A = delegation), and how to design interoperable agent systems without framework lock-in.

**NVIDIA touchpoints.** NIMs that speak both protocols, NeMo Agent Toolkit's alignment with open standards, MCP servers that front NVIDIA-stack surfaces (NGC, Triton, NeMo Customizer).

**Dependencies.** Topic 5.

**Stage.** `agentic`.

**Covered in.** —

---

## Topic 7 — Customization: Fine-tuning, PEFT, LoRA, Distillation

**Scope.** The decision tree — knowledge gap → RAG (don't fine-tune for facts); style/domain → SFT or LoRA; behavior → DPO; speed → distillation. The LoRA math (low-rank update `W + A·B`, ~99.5% parameter reduction), the multi-adapter superpower (one base model + thousands of LoRA adapters, hot-swapped at serve time), QLoRA for 70B training on one ~48 GB GPU, continued pre-training for extreme domain shift, and response vs. logit distillation for shrinking after you're done.

**NVIDIA touchpoints.** NeMo Framework (full FT + PEFT + LoRA + RLHF/DPO), NeMo Customizer (productized pipelines), NeMo Curator (synthetic data generation — the quiet revolution), Triton + vLLM multi-LoRA serving, Nemotron synthetic-data pipeline.

**Dependencies.** Topics 2–3.

**Stage.** `fine-tuning`.

**Covered in.** —

---

## Topic 8 — The NVIDIA Stack: NeMo, NIM, Triton, TensorRT-LLM

**Scope.** The mental model that ties the stack together — *how do I build the model* (NeMo + Curator + Customizer + Evaluator), *how do I run it fast* (TensorRT-LLM for kernel compilation, Triton for serving), *how do I ship it as a unit* (NIMs as packaged containers, Blueprints as reference architectures). Where each piece adds value, where flexibility (vLLM, raw PyTorch, Ollama) is the better choice, and how the pieces compose on a single DGX Spark.

**NVIDIA touchpoints.** NeMo suite (Framework, Curator, Customizer, Evaluator, Retriever, Guardrails, Agent Toolkit), TensorRT-LLM, Triton Inference Server, NIMs, Blueprints, NGC (container + model catalog), build.nvidia.com (playground + docs).

**Dependencies.** Topics 2–3, 7.

**Stage.** `dev-tools`.

**Covered in.** Partial — `articles/dgx-spark-day-one-access-first/` (access-layer intro, NIM positioning); `articles/nemoclaw-vs-openclaw-dgx-spark/` (Nemotron via Ollama path; TensorRT-LLM / Triton / NIM paths not yet covered).

---

## Topic 9 — Deployment: MLOps, Kubernetes, Observability

**Scope.** Why LLMOps differs from classical MLOps (the operational center of gravity moved from retraining pipelines to prompt/retrieval/eval management and inference infra), the operational lifecycle (model registry, prompt versioning, eval gates, observability, feedback loops, token-cost tracking), GPU scheduling in Kubernetes (GPU Operator, device plugin, MIG, time-slicing, DRA, NVLink topology awareness), and the observability minimums — trace every request, eval in production, detect drift, alert on anomalies. Compliance (SOC 2, HIPAA, GDPR, EU AI Act) framed as **technical constraints on system design**.

**NVIDIA touchpoints.** NVIDIA GPU Operator (K8s cluster automation), NIMs (deployable containers for pods), Triton (multi-model serving), NeMo Guardrails (PII detection, jailbreak defense, policy enforcement), DGX reference architectures, OpenTelemetry GenAI semantic conventions.

**Dependencies.** Topics 4–8.

**Stage.** `deployment`.

**Covered in.** —

---

## Topic 10 — Deployment Targets on DGX Spark: Local Runtimes, Containers, Remote Endpoints

**Scope.** The concrete runtime choices a Spark builder actually makes when serving inference. Five options, each with specific trade-offs: **Ollama / llama.cpp on the host** (fastest to start, no optimization floor, what most first-day setups use); **NIMs pulled from NGC** (packaged + tuned, Docker-native, OpenAI-compatible API); **Triton + TensorRT-LLM engines** (compiled per-GPU, maximum throughput, multi-model serving, recompile per generation); **vLLM / SGLang / text-generation-inference** (open-source alternatives running on the same CUDA, more flexible, good for iteration); **remote endpoints** (self-hosted NIM on another box, or an NVIDIA-managed NIM microservice at build.nvidia.com) for workloads the Spark's unified memory ceiling can't hold.

**NVIDIA touchpoints.** NIMs (container form + API contract), Triton Inference Server, TensorRT-LLM (engine compilation), NGC (container + model registry), build.nvidia.com (managed NIM microservices for overflow), DGX reference stacks; open-source Ollama / vLLM / llama.cpp for comparison, all running on the same NVIDIA CUDA substrate.

**Dependencies.** Topics 3, 8.

**Stage.** `deployment`.

**Covered in.** Partial — `articles/nemoclaw-vs-openclaw-dgx-spark/` (Ollama path benchmarked; NIM, Triton, vLLM, and remote-endpoint paths not yet covered).

---

## Topic 11 — Evaluation: From Benchmarks to Production

**Scope.** Why LLM outputs are not ground-truth-able by default (no single correct answer for open-ended text, tool-call sequences, multi-step agent trajectories), and the five eval layers: **model benchmarks** (MMLU, GSM8K, SWE-bench, GPQA — useful but saturated and contamination-prone); **task-level evals** (golden datasets, task-matched metrics, pass/fail rubrics); **component evals** (Ragas for RAG's recall/precision/faithfulness, τ-bench and AgentBench for agent trajectories); **end-to-end evals** (LLM-as-judge done right — detailed rubrics, pairwise comparisons, position-bias control, human calibration); and **production evals** (sample-and-grade, human review queues, shadow deployments, A/B tests, drift detection, regression gates). Cost and latency are eval metrics too.

**NVIDIA touchpoints.** NeMo Evaluator (benchmarking harness for standard + custom evals), NeMo Guardrails (evaluator components for safety + PII), OpenTelemetry GenAI conventions for production tracing; integration patterns with Ragas / LangSmith / Langfuse / Inspect / Promptfoo.

**Dependencies.** Applied on top of all prior topics — the discipline that validates everything else.

**Stage.** `observability`.

**Covered in.** —

---

## Coverage at a glance

| # | Topic | Stage | Coverage |
|---|---|---|---|
| 1 | Transformers & Attention | foundations | — |
| 2 | How Models Get Made: Pre-training → SFT → RLHF/DPO | training | — |
| 3 | Inference Economics & Optimization | inference | partial |
| 4 | Retrieval-Augmented Generation (RAG) | inference | — |
| 5 | Agents & Multi-Turn Tool Use | agentic | partial |
| 6 | Interoperability Protocols: MCP & A2A | agentic | — |
| 7 | Customization: Fine-tuning, PEFT, LoRA, Distillation | fine-tuning | — |
| 8 | The NVIDIA Stack: NeMo, NIM, Triton, TensorRT-LLM | dev-tools | partial |
| 9 | Deployment: MLOps, Kubernetes, Observability | deployment | — |
| 10 | Deployment Targets on DGX Spark | deployment | partial |
| 11 | Evaluation: From Benchmarks to Production | observability | — |
