# Screenshot Workflows

Three sources, one decision:

```
Is it a web UI?          → Playwright-MCP
Is it terminal output?   → Fenced code block (NOT a screenshot)
Is it a GUI app or       → scrot / gnome-screenshot
system dialog?
```

## Web UI via Playwright-MCP

Playwright-MCP is registered at user scope. The browser tools appear as `mcp__playwright__browser_*`.

### Verify it's available

```bash
claude mcp list
```

Should show `playwright: ... - ✓ Connected`. If not, the skill should direct the user to restart Claude Code — the MCP server was registered but a session predating the registration won't have the tools loaded.

### aarch64 / DGX Spark note

Recent `@playwright/mcp` defaults to the **Chrome** channel, which looks for `/opt/google/chrome/chrome` — a binary that does not ship on aarch64 (no official Chrome arm64 build). On DGX Spark, every browser call errors with `Chromium distribution 'chrome' is not found`. Fix: register the MCP with an explicit `--executable-path` pointed at Playwright's bundled chromium.

```bash
# One-time install of the bundled chromium (arm64-compatible)
npx -y playwright install chromium

# Re-register the MCP with the bundled chromium binary
claude mcp remove playwright -s user
claude mcp add -e DISPLAY=:1 --scope user --transport stdio playwright -- \
  npx -y @playwright/mcp@latest \
  --executable-path "$(ls -d ~/.cache/ms-playwright/chromium-* | grep -v headless | sort | tail -1)/chrome-linux/chrome" \
  --isolated --headless
```

Claude Code must be restarted for the new args to take effect — changing the MCP config mid-session does not restart the already-connected MCP process.

### Core flow

1. **Navigate:** `mcp__playwright__browser_navigate` to the URL.
2. **Snapshot (cheap):** `mcp__playwright__browser_snapshot` returns the accessibility tree. Use this to find elements and confirm the page loaded — it doesn't render a screenshot, so it's much faster than capturing one.
3. **Interact if needed:** `mcp__playwright__browser_click` / `browser_type`, passing refs from the snapshot.
4. **Resize:** `mcp__playwright__browser_resize` to `1440×900` before capture. The article layout renders embedded images at up to ~1232px wide on desktop (see "Image rendered width" below), so a 1440-wide viewport with the default 2x device-scale-factor produces a 2880×1800 PNG that stays crisp at the rendered width. Narrower viewports produce soft images.
5. **Capture:** `mcp__playwright__browser_take_screenshot`. Pass `fullPage: true` for long pages, or scope to an element via `element` + `ref` for a cropped shot.
6. **Save:** write the returned bytes to `articles/<slug>/screenshots/NN-description.png`.

### Image rendered width

The ai-field-notes article layout breaks `<img>` elements out of the 48rem prose column so they span the `.article` container (80rem max, ~1232px at desktop after padding). This is intentional — dashboard and portal screenshots need the width to remain readable. Two practical consequences:

- **Capture wide.** Aim for a 1440+ wide viewport with `deviceScaleFactor: 2`. A 1024×768 capture will display blurry once widened to 1232px.
- **Crop tight only when the subject is small.** For a full dashboard, full-page or viewport capture is fine. For a single UI affordance (a filter panel, a single button), prefer scoped element capture — the breakout CSS still centers it under the caption.
- **Captions stay at prose width.** The `*italic*` caption line after an image is kept narrow (52ch, centered) by a separate CSS rule, so caption text remains readable even as the image widens.

### Fallback: direct Node + Playwright

When MCP can't be used (aarch64 chromium issues, mid-session reconfiguration that doesn't reload, or scripted batch captures), fall back to the reusable Node script at `scripts/playwright-screenshot.js`. It uses the cached Playwright install + auto-resolves the bundled chromium binary, so it works in environments where `chrome` (Google-branded) isn't installed.

```bash
# Full-page capture
node ~/.claude/skills/tech-writer/scripts/playwright-screenshot.js \
  'https://example.com/page' \
  articles/<slug>/screenshots/NN-description.png

# Viewport-only, scrolled to a specific element (useful for vibe-testing
# local dev server output)
node ~/.claude/skills/tech-writer/scripts/playwright-screenshot.js \
  'http://127.0.0.1:4321/articles/<slug>/' \
  /tmp/article-viewport.png \
  --viewport-only --selector '.prose img'
```

Use this when verifying a just-embedded image renders correctly on the Astro dev server without needing to round-trip through the MCP.

### Sandbox / containerized web UIs

If the URL you need to screenshot lives inside an OpenShell sandbox or other local container, and a host-side service already binds the sandbox's exposed port, see [`sandbox-screenshots.md`](./sandbox-screenshots.md). The canonical case is the NemoClaw sandbox dashboard sharing host `:18789` with the host OpenClaw gateway — you have to temporarily vacate the host port to forward the sandbox one.

### Naming convention

`NN-short-description.png` — zero-padded number + kebab-case description. Examples:

- `01-ngc-catalog-overview.png`
- `02-nim-product-page-top.png`
- `03-ngc-filter-dgx-spark-applied.png`
- `04-nim-playground-first-response.png`

The numeric prefix orders them by article flow, which makes the `screenshots/` folder self-documenting and ensures alphabetical listings match reading order.

### Pages that require login

NGC (personal keys), build.nvidia.com (account), and some dashboards require authentication. For pages behind login:

1. First time: re-register the MCP server with a persistent user-data-dir so cookies survive restarts. Combine the persistent profile with the aarch64 `--executable-path` fix above:
   ```bash
   claude mcp remove playwright -s user
   claude mcp add -e DISPLAY=:1 --scope user --transport stdio playwright -- \
     npx -y @playwright/mcp@latest \
     --executable-path "$(ls -d ~/.cache/ms-playwright/chromium-* | grep -v headless | sort | tail -1)/chrome-linux/chrome" \
     --user-data-dir=/home/nvidia/.cache/playwright-mcp-profile
   ```
2. Walk the user through the login interactively with `--headless=false` (requires DISPLAY=:1).
3. Future sessions reuse the cookie.

Don't store credentials in the skill or in articles. Session cookies in the user-data-dir are fine; screenshots of logged-in states are fine; API tokens in prose are not.

### When NOT to screenshot a web page

- **Pure documentation pages** (docs.nvidia.com/...) — link to them, don't mirror them. Mirroring ages badly and duplicates their SEO.
- **Dynamic dashboards (metrics, live data)** — prefer an embedded `<iframe>` or a `curl`-to-JSON-table excerpt. A screenshot of a metric is obsolete before publication.
- **Anything that'll change next week** — a "New in 2.4!" banner in a screenshot is a time bomb.

## Terminal output as fenced code blocks

Default for all CLI work. Always preferred over a terminal screenshot.

### Why code blocks beat terminal screenshots

| Concern | Screenshot | Code block |
|---|---|---|
| Copy-paste | No | Yes |
| Search engine indexing | No | Yes |
| Screen reader accessible | Poor | Yes |
| Diffs cleanly in git | No | Yes |
| Survives font/theme changes | No | Yes |
| File size | Large | Tiny |

There is effectively no case where a terminal screenshot beats a code block.

### Language tags

````markdown
```bash
nvidia-smi
```

```
Thu Apr 21 16:42:11 2026
+-----------------------------------------------------------------------+
| NVIDIA-SMI 560.35.03   Driver Version: 560.35.03   CUDA Version: 12.6 |
...
```

```json
{
  "model": "meta/llama-3.1-8b-instruct",
  "usage": {"total_tokens": 142}
}
```

```yaml
services:
  nim:
    image: nvcr.io/nim/meta/llama-3.1-8b-instruct:latest
```
````

Use `bash` for commands, no tag (or `text`) for raw output, and language-specific tags for structured output.

### Trim long outputs

A 200-line `docker pull` output does nobody any favors. Show the first few meaningful lines, `...` to indicate truncation, and the last few lines if they carry the point (the final "pull complete" or the error). Readers can read the docs for the full output if they need it.

### Redact secrets

Before committing: scan code blocks for tokens, API keys, and anything that looks like a credential. The pattern `nvapi-...` and long base64-ish blobs are common leak formats. Use `nvapi-<redacted>` or `***` as placeholders.

## GUI apps via scrot (optional)

Needed rarely — most NVIDIA tooling is web or CLI. If you do need it:

```bash
# One-time install
sudo apt install scrot

# Capture active window after 3s delay (time to switch focus to target window)
DISPLAY=:1 scrot -d 3 -u articles/<slug>/screenshots/NN-description.png

# Capture full screen
DISPLAY=:1 scrot articles/<slug>/screenshots/NN-description.png

# Capture a selected area (requires user interaction)
DISPLAY=:1 scrot -s articles/<slug>/screenshots/NN-description.png
```

### Alternative: gnome-screenshot

```bash
DISPLAY=:1 gnome-screenshot -w -d 3 -f articles/<slug>/screenshots/NN-description.png   # active window
DISPLAY=:1 gnome-screenshot -a      -f articles/<slug>/screenshots/NN-description.png   # area select
```

### First-time friction

If `scrot` isn't installed, the skill should offer to install it via `sudo apt install scrot` rather than just failing.

## asciinema (optional polish)

For complex multi-step CLI flows where the **rhythm** matters — a long training job, a debugging session, a real-time stream — consider an asciinema recording.

```bash
# Install if missing
sudo apt install asciinema

# Record (space to pause, Ctrl-D to end)
asciinema rec articles/<slug>/assets/03-training-run.cast

# Embed in article.md
```

Embedding: either link to an asciinema.org upload or self-host using `asciinema-player.js`. Keep the cast file in `assets/` so it travels with the article.

### When asciinema is worth it

- Training runs where watching it unfold illustrates a point (memory climbs, then levels off, then the loss curve moves).
- Debugging sessions where the back-and-forth rhythm is the story.
- Anything interactive (REPL sessions, TUI apps).

### When it's not

- Short flows (< 1 minute). A code block suffices.
- Flows where only the final output matters. A code block suffices.
- Flows with secrets in the output. Asciinema casts are text and can leak.

## Alt text and captions — always both

Every image in the article needs both:

```markdown
![Description of what is visible in the image — specific, not a label](path/to/image.png)

*Caption: what the reader should notice or take away from this image.*
```

- **Alt text** describes the *content* of the image. Accessibility tools read this.
- **Caption** interprets the image — what should a reader take from it?

Bad alt text: `"screenshot"`, `"NGC page"`, `"terminal"`.
Good alt text: `"NGC catalog filtered by 'Optimized for DGX Spark', showing four model tiles with 'Runnable on 1x GPU' badges"`.
