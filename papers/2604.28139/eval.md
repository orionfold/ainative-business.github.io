> **FIELDKIT FIT (2026-05-02):** retro-annotation; eval predates the v0.1 template.
> - **Would import:** `fieldkit.nim` (agent + judge chat clients); `fieldkit.eval` (`Judge` rubrics for the semantic-dimension grader, `Trajectory` for the audit-log analyzer, `is_refusal` for refusal-rate accounting).
> - **Would extend:** `fieldkit.eval` — add a `HybridGrader` that fuses a deterministic-checker callable (file-state checksum, service-state assert, audit-log assertion) with a `Judge` semantic call and returns a single score. The current `Judge` is judge-only; this paper is the canonical reason to lift hybrid grading.
> - **Would propose for v0.x:** `fieldkit.agents` — sandbox-per-task orchestration over NemoClaw + workspace-snapshot fixtures (v0.2; concludes the v0.2 scope alongside ClawGym and Eywa).

# Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows

## Hypothesis

Static agent benchmarks freeze a task set at release and grade only the final response — they can't tell whether the agent actually executed the workflow or just guessed plausibly. Claw-Eval-Live separates a **refreshable signal layer** (workflow demands sourced from public ClawHub Top-500 skills, updated each release) from a **time-stamped reproducible release snapshot** (105 tasks with fixed fixtures, mocked services, sandboxed workspaces, and graders). Grading is hybrid: deterministic checks on execution traces / audit logs / service state / post-run workspace artifacts when evidence is sufficient, and structured LLM judging only for semantic dimensions. The paper evaluates 13 frontier models — the leader passes only **66.7%**, no model breaks 70%, and HR / management / multi-system business workflows are persistent bottlenecks. The bet is that grounding evaluation *twice* — in fresh external demand AND in verifiable agent action — is what eval needs to track real workflow capability.

## Memory budget

Pure-inference benchmark on the agent side, plus the sandbox infrastructure on the host:

- **Agent model under test** (Llama 3.1 8B or 70B fp8 via NIM): 16–80 GB. Per the capability map, both fit; 70B fp8 is the marginal-but-in-envelope option.
- **Mocked business services** (HR system, ticketing, file workspace): each service is a small Python or container process — 0.5–2 GB each. At 5–10 services concurrently mocked: ~10–20 GB.
- **Sandbox per-task workspace**: NemoClaw OpenShell containers, ~0.5–1 GB each at idle. Run them serially through the 105 tasks, not concurrently — workflow tasks can be long-running and parallel sandboxes risk the unified-memory OOM landmine.
- **LLM judge** for semantic-dimension grading: reuse the same NIM-served model (or a smaller Llama 8B sidecar) — adds 0–16 GB depending on choice.

Realistic envelope: 70B fp8 agent + 10 mocked services + 1 active sandbox + 8B judge ≈ 110 GB peak. Tight; comfortable with an 8B-as-agent + 8B-as-judge configuration (~40 GB).

## Proposed Spark recipe

There is no GitHub repo at eval time — the paper references a project page at `https://claw-eval-live.github.io` but no code/dataset URL surfaced via search. Recipe assumes the release ships shortly; in the interim, the article can demo the protocol on a 5–10 task subset reconstructed from the paper's task-family descriptions.

1. **Wait or proxy** — if the 105-task release isn't out, hand-author 5 representative tasks per family (HR, multi-system business, local workspace repair) using the paper's task structure as a template.
2. **Stand up the sandbox via NemoClaw** — each task gets a fresh OpenShell container with the workspace pre-populated from a fixture tarball. Use the verified file-transfer pattern from `reference_clawnav_file_transfer` (the `cat | openshell sandbox exec` workaround, since `openshell sandbox upload` is broken on v0.0.26).
3. **Mock the business services** as Flask/FastAPI processes inside the same network namespace — HR API, ticketing API, file-workspace state. Audit-log every request to a JSONL.
4. **Serve the agent under test via NIM**. Run two side-by-side: `llama-3.1-8b-instruct` and `nemotron-super-49b` (or 70B fp8 if the box has been freshly booted). The agent uses its tool-calling protocol against the mocked services + sandbox shell.
5. **Build the grader**: deterministic checks come from the audit log + workspace diff (file-state checksums, service-state asserts). Semantic checks (e.g. "did the agent's reply summarize the resolution correctly?") go through an LLM judge — Llama 8B as judge keeps it Spark-local.
6. **Score and compare**: publish per-task-family pass rates, mirror the paper's "leaderboard rank vs overall completion" finding on the smaller scale, and call out whether the local-first models exhibit the same HR / multi-system bottleneck pattern.

## Blockers

- **No repo, no dataset URL** as of eval time. The article either holds for the release or proxies a hand-authored subset — the proxy is honest if framed as protocol replication, not benchmark reproduction.
- **Service mocking is real engineering** — HR / ticketing mocks are non-trivial to build well. The article risks becoming "how I built mocks" rather than "what the agent did." Use the simplest possible mocks (3 endpoints each, single-table SQLite state).
- **The 13 models the paper evaluates aren't named in the abstract** — without the paper's exact list, the article's leaderboard will be a Spark-stack subset rather than directly comparable.
- **Judge contamination risk**: using the same family of models for agent + judge biases the score. Mitigate by using a *different family* (e.g., agent = Llama, judge = Nemotron) or by relying on deterministic-only checks for the headline number.

## Verdict

**spark-feasible** — 8B agent + lightweight service mocks + sequential sandbox runs sit comfortably below 50 GB, and NemoClaw + OpenShell are exactly the verified primitives this benchmark needs (`nemoclaw-vs-openclaw-dgx-spark`, `autoresearch-agent-loop`); the active blocker is the unreleased dataset, not the hardware envelope.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** claw-eval-live-on-spark
- **Suggested stage:** observability
- **Suggested series:** Autoresearch
- **Suggested tags:** agentic, benchmark, sandboxing, evals, llm-as-judge, audit-log, nemoclaw, openclaw
- **Suggested summary:** Stand up Claw-Eval-Live's sandboxed-workflow protocol on Spark using NemoClaw + OpenShell, mock the business-service backends, run Llama 3.1 8B vs Nemotron Super 49B as agent under deterministic-trace + LLM-judge grading, and chart where local-first agents land vs the paper's 66.7% frontier ceiling.
