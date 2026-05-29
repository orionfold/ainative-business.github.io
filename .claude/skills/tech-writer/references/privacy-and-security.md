# Privacy and Security — what must NEVER land in a published article

This blog is **public**. Articles get committed to a public GitHub repo and may be indexed by search engines, training corpora, and archive services. Anything that lands in `article.md`, `transcript.md`, files under `assets/`, or `screenshots/` is **effectively permanent** — git history, caches, and crawlers all have long memories. Rotating a leaked key is painful; unringing a bell about personal data is often impossible.

The tech-writer skill is responsible for a mandatory **scrub pass** before writing content and before committing. This file defines what to scrub, how to detect it, and what to do when something is found.

## The golden rule

**If in doubt, redact and ask.** It's cheaper to ask the user "is it OK to include this?" than to ship and have to rotate a key, change a hostname, or apologize. Default answer is always redact.

## What must always be scrubbed

### 1. Secrets and credentials — highest severity

| Kind | Pattern | Redaction |
|---|---|---|
| NGC API key | `nvapi-[A-Za-z0-9_-]{20,}` | `nvapi-<redacted>` |
| OpenAI-style key | `sk-[A-Za-z0-9]{20,}` (excluding `sk-ant-*`) | `sk-<redacted>` |
| Anthropic key | `sk-ant-[A-Za-z0-9_-]{20,}` | `sk-ant-<redacted>` |
| GitHub token | `gh[pousr]_[A-Za-z0-9]{20,}` | `ghp_<redacted>` |
| AWS access key ID | `AKIA[0-9A-Z]{16}` | `AKIA<redacted>` |
| AWS secret access key | 40-char base64-ish near an access key | `<redacted>` |
| Slack token | `xox[bpoa]-[A-Za-z0-9-]+` | `xox<redacted>` |
| Tailscale auth key | `tskey-(auth|api)-[A-Za-z0-9-]+` | `tskey-<redacted>` |
| SSH private key | `-----BEGIN OPENSSH PRIVATE KEY-----` block | remove the entire block |
| PEM private key / cert | `-----BEGIN (RSA\|EC\|DSA\|PRIVATE\|CERTIFICATE) KEY-----` | remove the entire block |
| JWT | `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | `<jwt-redacted>` |
| Bearer header in curl | `Authorization: Bearer <token>` | `Authorization: Bearer <redacted>` |
| Generic `.env` leak | `^[A-Z_]{3,}=[A-Za-z0-9/+_-]{16,}$` in a code block | evaluate case by case |

Any match from this table blocks the commit. The author can only proceed by redacting.

### 2. Personal identifiers (PII)

| Kind | Scrub rule |
|---|---|
| Real email addresses | The author's email may appear in frontmatter `author` *only*. In body prose, never include any email unless the person has publicly associated that email with their public work AND the author has approved it for this article. |
| Phone numbers | Always redact. No exceptions. |
| Home / personal IP addresses | Redact any public IP that could identify the user's ISP or location. RFC1918 addresses (`10.*`, `172.16-31.*`, `192.168.*`) and link-local (`169.254.*`) are usually safe to mention in technical context, but flag and let the author decide. |
| MAC addresses | Redact — they fingerprint hardware. |
| System hostnames | `dgx-spark` or default vendor hostnames are safe. Hostnames that identify an employer (`acme-corp-laptop`) or location (`home-office-pi`) must be redacted or genericized. |
| Shell prompt contents | Strip `user@host` prefixes from code blocks; replace with `$` or `#`. |
| Other people's names | Unless the person is a public figure whose public work is being cited, redact or use initials. |
| Geolocation | No addresses, coordinates, or "I live in…" details. |
| Serial numbers, UUIDs, license keys | Redact. |

### 3. System fingerprinting

Anything that would help an attacker profile this specific machine beyond what's needed to tell the story:

- Open ports and running services (`ss -tlnp`, `netstat`, `lsof` output)
- Full installed-package lists (a specific version relevant to the article is fine; `dpkg -l` is not)
- Firewall rules / ACLs (`ufw status verbose`, `iptables -L`)
- VPN / mesh network details (Tailscale node names, authkeys, ACLs, IPs)
- Backup paths, strategies, off-site locations
- Credentials-adjacent config files (`.netrc`, `.docker/config.json`, `.aws/credentials`)
- Other services running on the same machine unrelated to the article
- Private repository paths that hint at organization structure (`/home/manav/work/client-acme/`)

Rule of thumb: include what's necessary to tell the story; no more.

### 4. Browser and desktop state (screenshot hygiene)

Screenshots are the stealthiest leak vector because text in images isn't caught by text scans. The defenses are at **capture time**:

- **Prefer scoped element screenshots over full-page / full-desktop.** Playwright-MCP's `mcp__playwright__browser_take_screenshot` accepts `element` + `ref` — use these whenever the point of the image is a specific UI fragment. A scoped NGC filter panel shot can't accidentally capture the bookmarks bar or logged-in username.
- **Use the Playwright-MCP browser, not the user's real browser.** The MCP-controlled browser runs with its own profile — no personal bookmarks, no open tabs, no autocomplete exposing past searches. Never ask the user to take a shot from their logged-in Chrome.
- **Full-desktop screenshots via scrot require explicit user OK.** Never take one by default. If unavoidable, ask the user to close unrelated windows, hide the taskbar / system tray, and dismiss any notifications first.
- **No `~/Pictures`, `~/Downloads`, or `/tmp` content visible.** Filenames alone leak information.
- **No system notifications visible in the shot** — email subject lines and chat message previews routinely surface in corners.
- **After capture, look at the image once.** Scan edges, corners, and background. If anything is ambiguous, ask the user to review before embedding.

Text scrubbing cannot clean an image. Capture-time discipline is the only defense.

### 5. Transcript-specific risks

`transcript.md` is the cleaned source log and is **just as public as the article**. Common mistakes:

- Treating the transcript as private "source material." It's not — it's committed to the repo.
- Dumping raw conversation without filtering. Side-conversations about unrelated projects, personal asides, and debugging dead-ends that reveal other systems don't belong.
- Leaving error messages with absolute paths to private directories.

Scrub `transcript.md` with the same rigor as `article.md`. Drop tangential conversation; keep evidentiary material (commands run, meaningful outputs, decisions made).

## The scrub pass — mandatory workflow

**Before writing `article.md` or `transcript.md`** (draft mode):

1. Scan source material (conversation transcript, `_drafts/` notes, intended screenshots) with the patterns in Sections 1-3.
2. For each hit: default is **redact**. Ask the user only when it's ambiguous (e.g., "include your email in the author field, yes or no?").
3. Prefer replacement over deletion — `nvapi-<redacted>` reads better than an unexplained gap and communicates intent.

**Before committing** (publish mode):

1. `verify_article.sh` re-runs the scan against `article.md`, `transcript.md`, and text files under `assets/`.
2. Any hit blocks the commit with the file path + line number surfaced.
3. The author fixes by redacting (or explicitly approving a value the scan would otherwise block — see override rules below).

## When the user says "it's fine, include it"

The author has the final say. If they explicitly approve a value the scrub would otherwise flag (e.g., "yes, publish my email in the contact section"), honor it — but:

1. **Never override silently.** Acknowledge the override in the conversation: "Noted — keeping your email in the footer per your OK."
2. **Record the override** in the commit message footer so there's an audit trail: `Approved: email in closing section per author request`.
3. **Preserve the default as redact.** The override is per-item, not a blanket permission for the article.

If the user says "just don't worry about it" without specifying the item, **do not take that as blanket approval**. Ask what specifically.

## Quick ad-hoc detection command

For scanning outside `verify_article.sh` (e.g., during draft mode):

```bash
grep -rEn \
  'nvapi-[A-Za-z0-9_-]{20,}|sk-(ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bpoa]-[A-Za-z0-9-]+|tskey-(auth|api)-[A-Za-z0-9-]+|-----BEGIN (OPENSSH|RSA|EC|DSA|PRIVATE|CERTIFICATE) (KEY|PRIVATE KEY|CERTIFICATE)-----|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' \
  articles/<slug>/ 2>/dev/null
```

If this returns anything, scrub before continuing.

## What this skill will NOT do automatically

- **Redact a value the author has explicitly approved for inclusion.** Approval is a gate the author controls.
- **Edit `transcript.md` without surfacing what was removed.** If substantial content is dropped during the scrub, tell the user what categories were removed ("two API keys", "one internal hostname", "one side-conversation about an unrelated project").
- **Guarantee screenshots are clean.** Images require human review. The skill will flag full-desktop shots and ask the user to review each one.
- **Auto-push to GitHub.** Covered elsewhere but worth repeating here — the user pushes explicitly, after reviewing staged changes, every time.

## If a leak is discovered post-commit

Before push:

1. Amend the commit: `git reset --soft HEAD~1`, fix the file, re-commit.
2. Or: `git rm --cached` the file, fix, re-stage, re-commit.

After push:

1. **Rotate the leaked credential immediately.** Git history rewrite is secondary; key rotation is primary.
2. Rewrite history with `git filter-repo` or BFG if appropriate, then force-push. Accept that archive services may have cached the original.
3. Notify any affected third parties (if PII of someone else leaked).

Prevention is cheaper than remediation. The scrub pass exists so this section stays hypothetical.
