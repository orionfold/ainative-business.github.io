# Arena Field Edition — `arena.orionfold.com` bootstrap

`get-orionfold.sh` is the customer-facing first-boot install entry point
(license-workflow-v1 §5.2). It is **released code authored Spark-side**; it is
intentionally dumb and offline-honest:

1. drops the signed license file at `~/.orionfold/license` (chmod 600),
2. installs `fieldkit[arena]` into a self-contained venv (no sudo / no PEP-668
   fight / no pipx requirement — prefers an existing `fieldkit` or `pipx` if
   present),
3. hands off to `fieldkit field-edition doctor` then `fieldkit field-edition up`
   (gate the box → pull the proven matrix → §8 first-boot verify).

The license is verified **offline** by fieldkit (Ed25519 vs the embedded
`TRUSTED_KEYS`); the script does **no** entitlement check of its own — Supabase
already did that when it minted the signed URL.

## The ownership seam

| Piece | Owner |
|---|---|
| This script (`get-orionfold.sh`) | **Spark** (this repo — released, public) |
| `arena.orionfold.com` DNS | **Website/commerce peer** |
| Hosting the script (Supabase bucket + CDN) at that domain | **Website peer** |
| Minting the per-customer short-TTL signed URLs (`OF_LICENSE_URL`, optional `OF_WEIGHTS_URL`) | **Website peer** (`fulfillLicense` / `entitlement-fetch`) |
| The copy-paste install command on the order-status page | **Website peer** |

Spark owns the *content*; the Website peer serves it and wires the signed-URL
delivery around it — the same forced split as the license file itself (Spark
owns the format + validator; Website owns issuance + delivery).

## What the Website peer needs to emit

The order-status page (after a successful purchase) shows the buyer a one-shot
command with their freshly minted signed license URL inlined:

```sh
curl -fsSL https://arena.orionfold.com | OF_LICENSE_URL='https://<supabase-signed-url>' sh
```

If v1.1 moves the GGUF weights from HuggingFace into the private `field-edition`
Supabase bucket, add a second signed URL:

```sh
curl -fsSL https://arena.orionfold.com \
  | OF_LICENSE_URL='https://<signed-license>' OF_WEIGHTS_URL='https://<signed-gguf>' sh
```

Signed URLs are short-TTL by design — the script fetches them **first** so an
expired URL fails fast with a clear "re-copy from your order page" message
before the slow fieldkit install.

## Environment contract

| Var | Req | Default | Purpose |
|---|---|---|---|
| `OF_LICENSE_URL` | ✅ | — | signed URL to the license file |
| `OF_WEIGHTS_URL` | — | (unset) | signed URL to the Q4_K_M GGUF (v1.1; v1 pulls from HF in `up`) |
| `OF_MODEL_STORE` | — | `~/.orionfold/models` | where `OF_WEIGHTS_URL` lands |
| `OF_LICENSE_PATH` | — | `~/.orionfold/license` | license drop path (mirrors `ORIONFOLD_LICENSE`) |
| `OF_FIELDKIT_SPEC` | — | `fieldkit[arena]` | pip install target (pin a version / signed wheel for locked installs) |
| `OF_VENV` | — | `~/.orionfold/venv` | managed-venv location |
| `OF_SKIP_DOCTOR` | — | `0` | bypass the §7 matrix gate (not recommended) |
| `OF_SKIP_UP` | — | `0` | install + stage license only; don't run `up` |

## Hosting notes for the Website peer

- Serve with `Content-Type: text/x-shellscript` (or `text/plain`); the bytes
  are what `curl … | sh` pipes, so **no HTML wrapper**.
- The script is versionless content — host the file verbatim. When this repo
  updates it, re-upload. (Optionally publish a `?v=` query or an `X-OF-Bootstrap`
  ETag so you can diff what's live against this file.)
- Do **not** bake any signed URL or secret into the hosted script — those are
  always passed per-customer via the env vars above.

## Local smoke

```sh
# guard: missing license URL must die with the order-page hint
sh get-orionfold.sh

# license-drop only (no install / no bring-up):
printf '{"payload":{},"signature":{}}' > /tmp/lic.json
OF_LICENSE_URL="file:///tmp/lic.json" OF_LICENSE_PATH=/tmp/dropped/license \
  OF_SKIP_DOCTOR=1 OF_SKIP_UP=1 sh get-orionfold.sh
ls -l /tmp/dropped/license   # -rw------- (chmod 600)
```
