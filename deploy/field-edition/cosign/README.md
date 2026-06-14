# Arena Field Edition — cosign signing of the proven-matrix images (§9/M3)

Sigstore **keyless** signing of the Orionfold-built proven-matrix container
images, so the installer's §9 update channel can verify provenance before it
applies a new matrix (`fetch → cosign-verify → pull → up → gate → receipt`).

**This is operator-armed.** Keyless signing completes an interactive GitHub
OIDC browser flow that only the operator can do (authenticating as the
`orionfold` account). The scripts here are authored Spark-side and *ready*; the
operator runs the one armed command. It is **not a first-boot blocker** — the
proven matrix pulls fine unsigned today (`up` works); cosign hardens the
*update* path.

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

## Prerequisites (operator)

1. **cosign** — single Go binary. `sign-proven-matrix.sh --install-cosign`
   fetches it to `~/.local/bin`, or install manually
   (<https://docs.sigstore.dev/cosign/system_config/installation/>).
2. **GHCR write auth as `orionfold`** — the signature (`.sig`) is *written* to
   the same GHCR repo, so this needs orionfold's own `write:packages` token
   (the `manavsehgal` token gets `permission_denied: create_package` — see the
   publish-auth-surfaces note). The lane image was pushed under this exact auth:
   ```sh
   gh auth switch -u orionfold          # or: gh auth login  (write:packages, device flow)
   gh auth token | docker login ghcr.io -u orionfold --password-stdin
   # ... sign ...
   gh auth switch -u manavsehgal        # switch git back afterward
   ```
3. A browser reachable from the box (the OIDC flow opens one; on a headless box
   cosign prints a URL to open elsewhere and paste the code).

## The arm

```sh
cd deploy/field-edition/cosign

# 1. dry-run — see exactly what will be signed, sign nothing (safe):
./sign-proven-matrix.sh

# 2. arm it — install cosign if missing, then keyless-sign each image:
./sign-proven-matrix.sh --install-cosign --sign
```

When armed, cosign opens the GitHub OIDC flow → authenticate as **orionfold** →
Fulcio mints a short-lived cert whose Subject is the orionfold GitHub email and
whose Issuer is the GitHub OAuth issuer → the signature + cert are pushed to
GHCR and logged to the public **Rekor** transparency log.

## Recording the identity to pin

A keyless verify is only meaningful if it **pins the signer identity + issuer**
(otherwise any GitHub user's signature would pass). After a successful `--sign`,
the script reads the identity back from the freshly minted cert and writes it to
`signed-identity.env`:

```
OF_COSIGN_IDENTITY="<orionfold GitHub email>"
OF_COSIGN_ISSUER="https://github.com/login/oauth"
```

**Commit `signed-identity.env`** — it carries no secret (it's the *public*
identity to pin), and the installer's §9 verify reads it. If the auto-read
fails, confirm with `cosign verify --output json <ref> | python3 -m json.tool`
and fill the `Subject`/`Issuer` fields by hand.

## Verify (confirmation + the installer's M3 reference)

```sh
./verify-proven-matrix.sh
```

This runs the exact pinned check the installer's `LiveUpdateChannel.verify_signature`
must perform at M3:

```sh
cosign verify \
  --certificate-identity   "$OF_COSIGN_IDENTITY" \
  --certificate-oidc-issuer "$OF_COSIGN_ISSUER" \
  ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2…
```

## How M3 consumes this

`fieldkit/src/fieldkit/field_edition/update.py` already has the boundary:
`LiveUpdateChannel.verify_signature` currently raises an honest `UpdateError`
("proven-matrix releases must be cosign-signed — §9"). At M3, once the images
are signed and `signed-identity.env` is committed, that method shells out to the
pinned `cosign verify` above (the `verify-proven-matrix.sh` logic) and the
update channel goes live. Wiring that in is a fieldkit change gated on the
signatures existing first — i.e. **after** this arm.

## Notes / future

- **Stable CI identity (optional, later).** An interactive personal-email SAN
  is fine to start, but a GitHub Actions keyless workflow identity
  (`https://github.com/orionfold/<repo>/.github/workflows/<f>@refs/heads/main`,
  issuer `https://token.actions.githubusercontent.com`) is more durable for an
  automated §9 release cadence. Re-pin `signed-identity.env` if you move to it.
- **Registry-independent.** If the lane image is ever mirrored to the NGC public
  Catalog (the distribution-spec §7 brand play), `cosign sign` the NGC ref too —
  same flow, additive, no fork.
