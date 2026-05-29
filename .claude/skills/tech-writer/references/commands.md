# Command Intents

Claude Code slash commands don't parse positional arguments. When the user types `/tech-writer polish nim-first-inference`, the skill receives the whole string as free text via `args`. Route by intent detection, not by argv position.

## Intent detection

Match the user's phrasing against these patterns. When multiple match, prefer the more specific one.

| Phrases (examples) | Mode | Arguments to extract |
|---|---|---|
| "draft an article", "write this up", "turn this session into a post", "new post about X", "/tech-writer draft" | **draft** | Optional: slug hint, editorial overlay |
| "capture this", "note this for later", "save this moment for the blog", "/tech-writer capture" | **capture** | Optional: short label for the note |
| "polish the X piece", "improve the article on Y", "refine the draft of Z", "/tech-writer polish Z" | **polish** | **Required:** slug (ask if missing) |
| "publish the X piece", "commit the article Y", "/tech-writer publish Z" | **publish** | **Required:** slug (ask if missing) |
| "show me the articles", "update the blog index", "what have I written" | **index** | None |

## Extracting slugs from natural language

The user often refers to an article by its topic, not its exact slug. Strategy:

1. Glob `articles/*/` for candidates.
2. Match the user's phrasing against slug fragments (case-insensitive, substring).
3. If exactly one match, proceed — confirm briefly ("polishing `nim-first-inference-dgx-spark`").
4. If multiple matches, list them and ask the user which.
5. If zero matches, clarify — they may be thinking of a slug that doesn't exist yet.

Example:

> User: "polish the NIM piece"
>
> Skill: *globs `articles/` → finds `nim-first-inference-dgx-spark` and `nim-agent-blueprints-walkthrough`*
>
> Skill: "Two NIM articles exist: `nim-first-inference-dgx-spark` and `nim-agent-blueprints-walkthrough`. Which one?"

## Ambiguous phrasing

When the intent is genuinely unclear, ask **one** sharp question. Don't ask a list.

- User: "let's do the blog thing"
  - Skill: "Drafting a new article, or adding a note to a scratch folder?"
- User: "write up what we just did"
  - Skill: *infers draft mode.* Ask for the editorial overlay.

## The implicit fifth mode: `index`

If the user asks for an overview of the blog — "what have I written", "show me the articles", "update the index", "rebuild the table of contents" — rewrite `articles/README.md` to list all current articles.

Format:

```markdown
## Articles

### Inference
- **[Your First NIM Inference on DGX Spark — and What It Says About On-Device Deployment](nim-first-inference-dgx-spark/article.md)** — *2026-04-21, intermediate, NIM.* One-paragraph summary from frontmatter.

### Agentic
- **[Another article](another-slug/article.md)** — ...
```

Group by `stage`. Newest first within each group. The frontmatter provides title, date, difficulty, product, summary.

## Error handling

### `articles/` doesn't exist yet

Don't fail — offer to bootstrap:

> Skill: "The articles/ tree doesn't exist yet in `/home/nvidia/ainative-business.github.io`. I can create it with `scripts/init_blog.sh` — ok to proceed?"

### Slug collision on `new_article.sh`

The script errors out. Propose a disambiguating suffix:

- `-v2` / `-revisited` for follow-ups
- A more specific subtopic (`nim-agent-blueprints-retrieval-demo` vs `nim-agent-blueprints-walkthrough`)

Don't silently overwrite.

### Playwright-MCP tools missing mid-session

If `mcp__playwright__browser_*` tools aren't available but the MCP server is registered (`claude mcp list` shows it connected), the session predates the registration. Tell the user to restart Claude Code — a session mid-flight can't pick up new MCP servers.

### `verify_article.sh` fails

Show the exact output. Don't paraphrase the failures — the user needs the file paths and field names.

## Don't bypass the user for irreversible actions

- **Never auto-push to remote.** `publish` mode stages + commits only.
- **Never auto-install scrot or asciinema.** Offer to run the install command; wait for approval.
- **Never overwrite a user-edited article.md.** Polish mode reads, diffs, applies minimal changes.
