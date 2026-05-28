---
title: "Hardening the Hermes Harness on a DGX Spark — The Box Contains It, You Don't Trust the Model"
date: 2026-05-26
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: intermediate
time_required: "~2 hours, most of it the hostile-tool-call containment battery"
hardware: "NVIDIA DGX Spark"
tags: [hermes, agentic, hardening, sandbox, security, tool-calling, local-first, dgx-spark]
summary: "Before you leave a tool-wielding agent running on your desk, harden it. One pure function turns Hermes' permissive defaults into a desk-grade posture, then a scripted hostile-tool-call test proves it: egress denied at the sandbox, secrets in .env only, the config surviving a restart."
signature: HermesHardening
series: Harnesses
also_stages: [observability]
fieldkit_modules: [harness]
---

The first two articles in this series got the cockpit fast and reliable: Hermes Agent driving a local lane, a closed tool-call loop, 0% format errors. Both of them ran the agent with `--yolo`. That flag is fine for a supervised five-minute demo and exactly wrong for the thing this series is actually building toward — an agent you leave running on your desk, that you text from your phone, that has a shell. The moment the loop is unsupervised, the question stops being "is it fast" and becomes "what happens the first time it emits a tool call it shouldn't."

And it *will*. Not because the model is malicious — because a small local model occasionally misreads its own context, and because a prompt-injection riding in on a web page or a file it reads can turn the agent's hands against you. The mistake is to respond to that by trying to make the model trustworthy. You can't, and you don't have to. Hardening is the opposite move: you assume the agent will, sooner or later, try to do something hostile, and you make the *box* contain it anyway. This article is about doing that to Hermes on the Spark — turning a permissive default config into a desk-grade one with a single pure function, and then proving the containment with a scripted hostile-tool-call test rather than asserting it.

:::why[Containment beats trust]
The instinct after a bad tool call is to tune the prompt so the model "knows better." That's a treadmill — every new model, every new injection technique, resets it. Containment is durable instead: a sandbox with no network can't exfiltrate a secret no matter how thoroughly the model was talked into trying. The hardening posture is designed around the call you *didn't* foresee, which is the only kind that matters.
:::

## Why a personal box raises the stakes, not lowers them

It's tempting to think a single machine on your home network is low-risk — no fleet, no blast radius, no customers. The opposite is true for an always-on agent. The Spark's 128 GB of unified memory is what makes "always on" feasible in the first place: the model stays resident, the harness stays up, and you interact with it asynchronously over days. That same persistence means a single bad tool call isn't a transient blip in a CI job — it's an agent with shell access sitting on the same LAN as your other machines, holding whatever credentials you handed it, running while you're asleep.

So the personal-power-user framing cuts both ways. The Spark lets one person run an agent that would have needed a team and a security review to deploy at work — and it also hands that one person the entire security review. There's no platform team to set the sandbox policy. The good news, and the reason this is an afternoon of work rather than a project, is that the harness already ships every lever you need; they're just set to "fast iteration" out of the box. Hardening is mostly flipping known switches in the right combination and then *checking that the combination actually holds*.

:::hardware[An agent that outlives the session]
On a laptop you start an agent, watch it, and close the lid. On a 128 GB Spark the model is resident and the harness is a service — you message it the way you'd message a person, and it's there hours later. That changes the threat model from "a process I'm supervising" to "a standing service with my credentials and a shell." Hardening is what earns it the right to keep running when you're not looking.
:::

## Where hardening sits in the harness

Hermes is deliberately permissive by default, and for good reason — the fastest path to a working agent is one that runs commands directly on your host, never blocks on an approval prompt, and warns rather than halts when a tool loop misbehaves. Every one of those defaults is a productivity choice that becomes a liability the moment the loop is unsupervised. Hardening is a distinct lifecycle stage that sits *after* install (H1) and lane-tuning (H2) and *before* you ever hand the agent real power over the box — which is why it has to land before the keystone MCP article, not after.

The mechanism is one function in `fieldkit.harness`: `harden_config`. It takes the `HermesConfig` you'd configure a lane with and a `HardeningPolicy`, and returns a *new* hardened config. The diagram below is the whole thesis in one picture — a hostile call lands in the sandbox and simply cannot get back out.

<figure class="fn-diagram" aria-label="A hostile tool call from a runaway model or a prompt-injection lands in the hardened sandbox, a docker container run with network egress denied. The single solid edge into the sandbox is the call arriving; the dashed edge from the sandbox to the internet is severed with a red cross, marking egress denied via --network=none. The verdict strip reads exfil, DNS, and remote-payload fetch all failed — contained.">
  <svg viewBox="0 0 900 440" role="img" aria-label="A hostile tool call from a runaway model or a prompt-injection lands in the hardened sandbox, a docker container run with network egress denied. The single solid edge into the sandbox is the call arriving; the dashed edge from the sandbox to the internet is severed with a red cross, marking egress denied via --network=none. The verdict strip reads exfil, DNS, and remote-payload fetch all failed — contained." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d03-hostile-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-red)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d03-sandbox-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d03-sandbox-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="40" y="160" width="210" height="120" rx="10" fill="url(#d03-hostile-grad)" stroke="none"/>
    <rect x="360" y="160" width="220" height="120" rx="10" fill="url(#d03-sandbox-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="d03-land-path" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 230 220 L 360 220" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 580 200 L 690 130" />
    </g>
    <circle class="fn-diagram__flow" r="6"><animateMotion dur="3s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.4s"><mpath href="#d03-land-path" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="170" width="170" height="100" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="360" y="160" width="220" height="120" rx="10" style="fill: url(#d03-sandbox-accent-grad)" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="690" y="60" width="160" height="100" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="145" y="166" text-anchor="middle">RUNAWAY · INJECTION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="145" y="232" text-anchor="middle">hostile call</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="145" y="252" text-anchor="middle">curl|sh · rm -rf</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="470" y="156" text-anchor="middle">HARDENED SANDBOX</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="470" y="222" text-anchor="middle">docker · ephemeral</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="242" text-anchor="middle">--network=none</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="262" text-anchor="middle">approvals: manual</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="770" y="56" text-anchor="middle">UNREACHABLE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="770" y="122" text-anchor="middle">internet</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="770" y="142" text-anchor="middle">egress</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(133 180)"><path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(458 170)"><path d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/></g>
      <g class="fn-diagram__icon" transform="translate(758 70)"><path d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418"/></g>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="640" y="158" text-anchor="middle">egress denied</text>
      <text class="fn-diagram__annotation" x="450" y="402" text-anchor="middle">exfil ✗ · DNS ✗ · remote payload ✗ — contained</text>
      <g stroke="var(--svg-accent-red)" stroke-width="2" stroke-linecap="round"><line x1="630" y1="160" x2="640" y2="170"/><line x1="640" y1="160" x2="630" y2="170"/></g>
    </g>
  </svg>
  <figcaption>The accent node is the only place the agent runs — and it has no route out. Whether the call came from a confused model or an injected instruction is irrelevant; the box doesn't ask.</figcaption>
</figure>

## The two defaults that bite, and the function that flips them

Reading Hermes' shipped `config.yaml` on the Spark, two defaults stand out as the ones that turn a helpful agent into a liability. The terminal backend is `local` — tool calls that run a shell run it *on your host*, in your home directory, as you. And the tool-loop guardrails are warn-only (`hard_stop_enabled: false`) — when the agent gets stuck failing the same tool five times, it gets a stern note in its context rather than a hard stop. Add the `--yolo` flag both earlier articles used (which sets approvals to `off`), and you have an agent that runs arbitrary commands on your host with no brakes. Great for a demo. Not something you leave running.

:::pitfall[`--yolo` plus the `local` backend is the combination to never leave running]
Individually each is survivable. Together — approvals off, commands executing directly on the host, loop guardrails warning instead of halting — they compose into "an unsupervised process with your shell and no stop button." The fix isn't to remember not to use `--yolo`; it's to make the *persisted* config refuse that posture so a forgotten flag can't resurrect it.
:::

`harden_config` flips these in one call. Every field of the policy maps to a real key in Hermes' config schema (verified against the installed v0.14.0), so the output isn't fieldkit's idea of hardening — it's Hermes' own knobs, set correctly:

```python
from fieldkit.harness import HermesConfig, harden_config

cfg = HermesConfig(provider="custom", base_url="http://127.0.0.1:8000/v1",
                   model="nvidia/nemotron-nano-9b-v2")
hardened = harden_config(cfg)   # DEFAULT_HARDENING — the spec §4.3 baseline
print(hardened.render())
```

```yaml
model:
  provider: custom
  base_url: "http://127.0.0.1:8000/v1"
  default: nvidia/nemotron-nano-9b-v2
terminal:
  backend: docker                 # sandbox, not the host
  container_persistent: false     # ephemeral — gone when the call returns
  docker_mount_cwd_to_workspace: false
  lifetime_seconds: 300
  docker_extra_args:
    - "--network=none"            # the egress lever
tool_loop_guardrails:
  warnings_enabled: true
  hard_stop_enabled: true         # halt, don't just warn
approvals:
  mode: manual                    # never silently auto-run a dangerous command
  cron_mode: deny
agent:
  max_turns: 30
  subagent_auto_approve: false
session_reset:
  mode: both
```

:::define[Terminal backend: `local` vs `docker`]
Hermes' terminal tool runs shell commands either directly on the host (`local`) or inside a throwaway container (`docker`). The container backend is the single biggest hardening move: a command that `rm -rf`s the workspace destroys an ephemeral container, not your home directory, and a command that tries to reach the network hits whatever the container's network policy allows — which, hardened, is nothing.
:::

:::define[Tool-loop guardrails]
Hermes counts repeated tool failures and "no-progress" loops. By default it *warns* (injects a note into the agent's context) at low thresholds. Hardened, `hard_stop_enabled: true` makes those thresholds terminal — the agent is stopped, not nudged. This is the in-loop analog of a circuit breaker, and it's directly the policy pattern this project's Guardrails-on-the-retrieval-path work established: a declared budget that halts rather than degrades.
:::

The design choice worth calling out: `harden_config` is a **pure function**. It doesn't write your config, doesn't touch `~/.hermes`, doesn't have an opinion about when you apply it. It takes a config and returns a new frozen one with the hardened sections folded in; the input is untouched. That's deliberate — it makes the hardening testable in isolation (you can assert on the output without a Hermes install) and composable (you harden, then diff, then decide to apply). It also means hardening can *refuse*.

:::deeper[Why it refuses instead of best-effort]
`harden_config` raises rather than emit a config it can't vouch for, in three cases. If `local_first` is set and the provider isn't local (the cloud `nvidia` Nemotron provider, say), it refuses — a cloud provider defeats the entire local-only posture. If the requested approval mode is `off`, it refuses — that's `--yolo`, and the function won't bless it. And if a secret-looking key (`api_key`, a `*_token`) sits in the config *body*, it refuses — secrets belong in `~/.hermes/.env`, never in the version-controllable YAML. Erring toward refusal is the same instinct as the `serve_lane` memory guard from H2: a tool that hardens should fail loudly, not produce something that merely looks hardened.
:::

## Proving it: the scripted hostile-tool-call test

A hardened config you didn't test is a hope. The spec's gate for this article is explicit — *the harness survives a scripted hostile-tool-call test, and restart behavior is verified* — so the evidence is a five-check battery (`evidence/harden_hostile_test.py`) that runs against the real container runtime and the real Hermes binary, not against fieldkit's own assumptions. The interesting check is egress containment, because it's the one that doesn't depend on the model behaving at all.

The test launches a sandbox exactly as the hardened config dictates — `docker run --network=none` — and inside it attempts the three things a runaway tool call would try: resolve a hostname, exfiltrate a (fake) key over an outbound request, and fetch a remote payload to run. Then it runs the identical three moves on the default network as a control, to prove they'd otherwise succeed.

```text
--- HARDENED (--network=none) ---
  dns_resolve:    contained=True  | "nslookup: can't connect to remote host: Network unreachable"
  exfil_post:     contained=True  | "wget: bad address 'huggingface.co'"
  fetch_payload:  contained=True  | "wget: bad address 'huggingface.co'"
--- CONTROL (default network) ---
  dns_resolve:    contained=False | "Address: 2600:9000:234c:...  (resolved)"
  exfil_post:     contained=False | "<!doctype html><html ...  (reached the host)"
  fetch_payload:  contained=False | "HTTP/1.1 404 Not Found  (reached the host)"
```

That contrast is the whole argument. On the default network every hostile move connects; under `--network=none` DNS itself is dead — there's no name resolution, no route, nothing to connect to. The model can want to exfiltrate a secret as badly as a prompt-injection can make it want to; the sandbox has no network, so the want goes nowhere. Containment, not trust.

:::define[Network egress and `--network=none`]
"Egress" is any outbound connection a sandboxed command can open — a DNS lookup, an HTTP POST, a reverse shell. Docker's `--network=none` gives the container no network interface at all (just loopback), so egress isn't *filtered*, it's *absent*. The hardened config carries this as `terminal.docker_extra_args`, the one hardening lever that's a list rather than a scalar — which matters for how it gets applied, below.
:::

The other four checks round out the posture. **Secret hygiene:** the hardened config's rendered body contains no secret string, the API key lives only in the `.env`, and `harden_config` refuses outright if you try to put a secret in the body. **In-loop guardrails:** the emitted `hermes config set` lines flip approvals to `manual`, deny cron auto-approval, and turn the loop guardrail to hard-stop — and the function refuses to emit `--yolo`. **Restart persistence** gets its own section because it's where most "hardening" quietly fails.

## Restart is where hardening usually leaks

Hardening that lives in a runtime flag evaporates on restart — and a desk agent restarts: on a crash, on a reboot, on the daily session reset the hardened config itself schedules. So the posture has to live in the persisted `config.yaml`, and the only way to be sure is to apply it through the real CLI and read it back from a fresh process. Using a throwaway `HERMES_HOME` (the user's live `~/.hermes` is never touched), the test applies the hardened scalar levers via the actual `hermes config set` and then re-reads the file:

```text
$ hermes config set terminal.backend docker          # ... 8 scalar levers
✓ Set terminal.backend = docker
✓ Set tool_loop_guardrails.hard_stop_enabled = True
✓ Set approvals.mode = manual
...
# restart-equivalent: a fresh process reads config.yaml back
terminal:
  backend: docker
  container_persistent: false
tool_loop_guardrails:
  hard_stop_enabled: true
approvals:
  mode: manual
  cron_mode: deny
agent:
  max_turns: 30
session_reset:
  mode: both
```

Two details earned their way into the code from this run. First, `hermes config set` coerces `true`/`false` and integers to real types but stores everything else as a raw string — so it persists booleans correctly but *cannot* parse the one list-valued lever, `terminal.docker_extra_args: ["--network=none"]`. That's why `HermesConfig.config_set_commands()` emits the scalar levers and deliberately skips the list one, which is applied via the rendered YAML block instead. The function tells you the truth about what `config set` can and can't do rather than emitting a line that would silently store `["--network=none"]` as a literal string. Second, Hermes' own `config set` routes any `*_API_KEY`/`*_TOKEN` to the `.env` automatically — the secret-hygiene posture isn't fieldkit imposing a convention, it's fieldkit refusing to fight one the harness already enforces.

A fresh `hermes config show` confirms it from the outside: `Backend: docker`. The hardened posture is in the file, so it's there after the reboot you didn't plan.

## What didn't go to plan

The first pass of the egress test reported the DNS move as *not* contained, which was alarming for about a minute until I read the actual output. The move was contained — `nslookup` returned "Network unreachable" — but my failure-signature matcher was looking for the string "network is unreachable" and the runtime emits "Network unreachable" without the "is." The containment was real; the *detection* of it was wrong. It's a small thing, but it's the kind of small thing that, in a security test, is the difference between "I proved it" and "I think I proved it." The fix was broadening the signature set; the lesson was that a containment test has to be as carefully checked as the thing it's testing, because a test that passes for the wrong reason is worse than no test.

The other surprise was how much of "hardening" turned out to be *refusing to do things* rather than configuring them. The most valuable lines in `harden_config` aren't the ones that set `terminal.backend: docker` — those are obvious. They're the three `raise` statements: refuse a cloud provider under a local-first policy, refuse `--yolo`, refuse a secret in the config body. Hardening as a feature is easy to imagine as "more settings"; in practice the settings are the boring part and the guardrails on *misconfiguration* are where the safety actually lives.

## What this unlocks

With the harness hardened, three things become reasonable to do that weren't before. You can leave the agent running as a service and message it asynchronously — the daily `session_reset` and the ephemeral sandbox mean a stuck or compromised session doesn't accumulate state or reach for the network while you're away. You can point it at untrusted input — a web page, a downloaded file, an email — knowing that a prompt-injection in that content lands in a box with no egress, so the worst case is a wasted turn, not an exfiltrated credential. And you can give it genuinely useful tools, because the next article does exactly that.

That's the real payoff, and the reason this article had to come before the next one. The keystone of this series is wiring Hermes to operate the Spark itself — exposing `fieldkit` as MCP tools so the agent can quantize a model, measure it, and publish it. Handing an *un*-hardened agent that kind of write access to your pipeline would be reckless. Handing a hardened one those tools is the entire point: a contained agent with real power over the box, which is what a personal AI cockpit was always supposed to be.

## Closing

The Spark makes it feasible for one person to run an always-on, tool-wielding agent at home — and hardening is the unglamorous step that makes "always-on" mean "safe to ignore" rather than "running unsupervised with my shell." The move that matters is the reframe: you don't make the model trustworthy, you make the box containing it indifferent to whether the model is trustworthy. A hostile call lands in a sandbox with no network, the loop hard-stops instead of spinning, secrets sit in a file the agent's body never sees, and the whole posture survives the reboot you didn't plan.

Next up — the keystone: Hermes drives the Spark via `fieldkit`-as-MCP. The agent we just made safe to leave running gets the tools to quantize, measure, and publish models on the box itself. The cockpit stops being something you operate and becomes something that operates the machine.
