# NemoClaw GitHub Repository Overview

Source: https://github.com/NVIDIA/NemoClaw
Captured: 2026-04-21 (one-time traversal)

## What NemoClaw is

NemoClaw is an open-source reference stack from NVIDIA that enables secure execution of OpenClaw always-on assistants through the NVIDIA OpenShell runtime. It provides guided onboarding, a hardened blueprint, state management, OpenShell-managed channel messaging, routed inference, and layered protection.

- **License:** Apache 2.0
- **Status:** Alpha / early preview as of March 2026 — expect breaking changes.
- **Language breakdown (approx.):** TypeScript 71%, Shell 25%, Python 2%, other 2%.
- Not related to NVIDIA **NeMo** or **NeMo-Guardrails**. If a user mentions those, it's a different product line — disambiguate before advising.

## Install one-liner

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```

Handles Node.js (if missing), OpenShell CLI, repo clone, CLI build, and `nemoclaw onboard` wizard.

## Uninstall one-liner (alternative to the in-repo `uninstall.sh`)

```bash
curl -fsSL https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh | bash
```

Flags (same as the in-repo `./uninstall.sh`):
- `--yes` — skip confirmation
- `--keep-openshell` — retain `openshell` binary
- `--delete-models` — also remove Ollama models

## System requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 vCPU | 4+ vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 20 GB free | 40 GB free |
| Node.js | 22.16+ | |
| npm | 10+ | |

Docker required (DGX Spark preinstalls a compatible version). NVIDIA Container Runtime required for GPU inference. aarch64 on DGX Spark.

## Repository root layout (as of capture)

```
NemoClaw/
├── bin/                    # CLI entry point (CJS)
├── nemoclaw/               # TypeScript plugin (Commander extension)
│   └── src/
│       ├── blueprint/      # Runner, snapshot, validation, state
│       ├── commands/       # Slash commands, migration
│       └── onboard/        # Configuration
├── nemoclaw-blueprint/     # Blueprint YAML and policies
├── scripts/                # Install helpers and automation (incl. fix-coredns.sh)
├── test/                   # Integration and E2E tests
├── docs/                   # User-facing docs (Sphinx/MyST)
├── agents/                 # Agent definitions
├── schemas/                # Schema definitions
├── ci/                     # CI pipeline configurations
├── .github/                # CI/CD workflows
├── Dockerfile              # Container definition
├── Makefile                # Build automation
├── package.json            # Node.js dependencies
├── pyproject.toml          # Python project config
├── install.sh              # Main installer (what `nemoclaw.sh` downloads)
└── uninstall.sh            # Complete removal script
```

### Notable scripts

- `scripts/fix-coredns.sh` — used by the troubleshooting guide to recover k3s CoreDNS on DGX Spark.
- `install.sh` / `uninstall.sh` — top-level lifecycle.
- `nemoclaw setup-spark` — host command that applies the cgroup-namespace fix automatically (per the troubleshooting guide).

### Documentation published alongside the repo

The repo links out to:
- Overview
- How It Works
- Architecture
- Inference Options
- Network Policies
- Security Best Practices
- CLI Commands
- Troubleshooting

These are rendered on docs.nvidia.com/nemoclaw/latest/ — consult them for deeper architecture questions not covered in the other reference files here.

## Usage examples from the README

Connect to a sandbox:
```bash
nemoclaw my-assistant connect
```

Launch the terminal UI:
```bash
openclaw tui
```

Send a single message from the CLI:
```bash
openclaw agent --agent main --local -m "hello" --session-id test
```

## State directories the installer creates

- `~/.nemoclaw/` — installer-managed state (includes `source/` with the cloned repo).
- `~/.nemoclaw/source/` — the clone used by `./uninstall.sh`.
- `~/.config/openshell/` — OpenShell CLI config.
- `~/.config/nemoclaw/` — NemoClaw CLI config.

All four are removed by the uninstaller.

## Security reporting (do not use public issues)

- NVIDIA Vulnerability Disclosure Program
- `psirt@nvidia.com` (PGP)
- GitHub private vulnerability reporting on the repo

## Related resources (not fetched in this traversal)

- docs.nvidia.com/nemoclaw/latest/ — authoritative developer guide, including CLI command reference and architecture.
- github.com/NVIDIA/dgx-spark-playbooks — additional DGX-Spark-specific playbooks.
