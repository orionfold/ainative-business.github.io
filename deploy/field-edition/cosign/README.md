# Arena Field Edition — cosign signing of the proven-matrix images (§9/M3)

Signing of the Orionfold-built proven-matrix container images, so the
installer's §9 update channel can verify provenance before it applies a new
matrix (`fetch → cosign-verify → pull → up → gate → receipt`).

**This is operator-armed**, and it is **not a first-boot blocker** — the proven
matrix pulls fine unsigned today (`up` works); cosign hardens the *update* path.

## Why key-based (not keyless)

Sigstore **keyless** signing needs **Fulcio** (the CA) at `fulcio.sigstore.dev`,
which is **network-blocked on the Spark box** — it answers 443 in plaintext
(`tls: first record does not look like a TLS handshake` / OpenSSL `wrong version
number`). Rekor (`rekor.sigstore.dev`) and the TUF root
(`tuf-repo-cdn.sigstore.dev`) *are* reachable, so we sign with a **long-lived
Ed25519 key** and still upload to the public **Rekor** transparency log.

The **public key is committed + pinned** (`proven-matrix.pub`), exactly
mirroring how this repo already pins the Ed25519 license key in
`license.TRUSTED_KEYS`. (If the network is later opened to Fulcio, moving to
keyless or to a GitHub-Actions keyless workflow identity is a drop-in swap —
re-pin `proven-matrix.pub` → an identity/issuer pair.)

## Scope: what gets signed

Only **Orionfold-built, GHCR-hosted, digest-pinned** images — derived live from
the installed `fieldkit` (`compose.default_config()`) so this never drifts from
`compose.py`. Today that is exactly **one**:

| Image | Owner | Signed here? |
|---|---|---|
| `ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2…` (the CUDA-13 lane) | Orionfold | ✅ yes |
| `ghcr.io/orionfold/cortex-embedder` | Orionfold | ⏳ when built + pinned (v1.1) — auto-included |
| `pgvector/pgvector@sha256:…` | upstream (Docker Hub) | ❌ not ours to sign |
| `nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2@sha256:…` | NVIDIA NGC | ❌ not ours to sign |

## Key custody

| Artifact | Where | Committed? |
|---|---|---|
| **private key** `cosign.key` | `~/.orionfold/cosign/cosign.key` (`$OF_COSIGN_KEY`), encrypted with `COSIGN_PASSWORD` | ❌ **never** — keep it + the password in the orionfold secret store, same custody as the prod license seed |
| **public key** `proven-matrix.pub` | this directory | ✅ yes — it's the pin the verify side + the installer use |

## Prerequisites (operator)

1. **cosign** — `sign-proven-matrix.sh --install-cosign` fetches it to
   `~/.local/bin` (already done: v2.4.1).
2. **GHCR write auth as `orionfold`** — the signature (`.sig`) is *written* to
   the same GHCR repo, so this needs orionfold's own `write:packages` token (the
   `manavsehgal` token gets `permission_denied`). Already logged in this session:
   ```sh
   gh auth switch -u orionfold
   gh auth token | docker login ghcr.io -u orionfold --password-stdin
   # ... sign ...  then switch git back:
   gh auth switch -u manavsehgal
   ```

## The arm

```sh
cd deploy/field-edition/cosign

# 1. dry-run — see exactly what will be signed, sign nothing (safe):
./sign-proven-matrix.sh

# 2. arm it — pick a strong COSIGN_PASSWORD (it protects the new key):
COSIGN_PASSWORD='…' ./sign-proven-matrix.sh --sign
```

First run generates the key pair (into `~/.orionfold/cosign/`), publishes the
public half to `proven-matrix.pub`, then key-signs each image and uploads to
Rekor. Re-runs reuse the existing key. `COSIGN_PASSWORD` must be set (or cosign
prompts) to generate and to decrypt the key for signing.

## Verify (confirmation + the installer's M3 reference)

```sh
./verify-proven-matrix.sh
```

Runs the exact pinned check the installer's `LiveUpdateChannel.verify_signature`
performs at M3:

```sh
cosign verify --key proven-matrix.pub ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2…
```

## How M3 consumes this

`update.py`'s `LiveUpdateChannel.verify_signature` currently raises an honest
`UpdateError` ("proven-matrix releases must be cosign-signed — §9"). At M3, once
the images are signed and `proven-matrix.pub` is committed, that method shells
out to the pinned `cosign verify --key` above (the `verify-proven-matrix.sh`
logic) and the update channel goes live. Wiring it in is a fieldkit change gated
on the signatures existing first — i.e. **after** this arm.

## Notes

- **`OF_NO_TLOG=1`** signs/verifies without the Rekor upload (fully
  self-contained) — only needed if the transparency log is unreachable. Rekor is
  reachable today, so the default keeps the public-log provenance.
- **Registry-independent.** If the lane image is ever mirrored to the NGC public
  Catalog (distribution-spec §7 brand play), `cosign sign --key` the NGC ref too
  — same flow, additive.
