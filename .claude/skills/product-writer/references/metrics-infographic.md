# The build-metrics infographic

The infographic is the spine of a "built it in a day" claim. Its credibility
depends entirely on the numbers being *measured from primary sources* rather
than estimated — a reader who senses round, invented figures discounts the
whole piece. The `scripts/mine_build_metrics.py` script exists so you never
have to guess.

## Mining the numbers

Run the script with the build window, the Claude Code transcript directory, the
source paths, the test globs, and the commit pattern. Example (Orionfold Arena):

```bash
python3 ~/.claude/skills/product-writer/scripts/mine_build_metrics.py \
  --since 2026-05-28T09:00:00 --until 2026-05-29T01:00:00 \
  --log-dir /home/nvidia/.claude/projects/-home-nvidia-ainative-business-github-io \
  --repo /home/nvidia/ainative-business.github.io \
  --commit-grep '^(arena:|spec\(arena\))' \
  --loc fieldkit/src/fieldkit/arena --loc-exclude _webui \
  --loc src/components/arena --loc src/lib/arena --loc src/pages/arena \
  --tests 'fieldkit/tests/arena/test_*.py' \
  --out products/<slug>/assets/build-metrics.json
```

What each source gives you:

| Number | Source | Why it's trustworthy |
|---|---|---|
| Tokens (processed / generated / cache) | session JSONL transcripts, deduped by message id, split by model | the actual API accounting, not a guess |
| Lines of code | non-blank source lines, built bundles + AppleDouble turds excluded | *authored* source only |
| Test cases | `def test_` / `it(` / `test(` under the test globs | counts real cases, not files |
| Wall-clock | first → last matching git commit | the build's real elapsed span |
| Sessions / turns | distinct transcripts / assistant messages in the window | the agentic effort behind it |

Save the JSON into `products/<slug>/assets/build-metrics.json` and copy the
figures into the frontmatter `build:` block. Because the script is
deterministic, anyone can re-run it and get the same numbers — that's the
point.

## Picking the build window honestly

The window defines everything downstream, so choose it defensibly:
- Start at the first commit of real work (a spec-lock or M1 commit), end at the
  ship commit. The git wall-clock the script reports is your sanity check.
- The token mine counts *all* assistant turns in the window across *all*
  sessions in that project — so if the operator did unrelated work in the same
  hours, the token figure includes it. If that's a concern, narrow the window
  or note the caveat. For a focused build sprint it's fine and honest.

## Framing the numbers — interpret, don't just dump

Each headline number needs one sentence saying what it *means*. Some honest
framings, with the traps to avoid:

- **Tokens processed vs. generated.** The big number (hundreds of millions) is
  *processed* tokens, and most of it is cache reads — for the Arena, 228M of
  233M (98%) were served from Claude Code's prompt cache. Quote both: "233M
  tokens processed, 98% of them cache hits; 972k tokens actually generated."
  The cache ratio is itself a story about why agentic coding at this scale is
  affordable. **Trap:** quoting "233M tokens" as if they were all freshly
  generated overstates the work and misleads on cost.
- **Lines of code.** Quote *authored* source (bundles excluded). **Trap:**
  including a compiled `_webui/` bundle to inflate the number — the script's
  `--loc-exclude` exists precisely so you don't.
- **Model mix.** Report the real models. If the build was 100% one model and a
  newer one is now the daily driver, that's the honest and more interesting
  framing (the handoff), not a fabricated split. **Trap:** implying two models
  shared the build when the logs show one.
- **Tests.** "125 tests, written alongside the features" supports the
  production-quality claim better than the raw count alone.
- **Wall-clock.** "~15 hours across one day and an overnight" is more honest
  than "in a day" if that's what the commits show. Let the git span set the
  phrasing.

## Specifying the infographic for the destination repo

The skill does not render the chart — the destination (Mac) repo owns the
infographic component, exactly as it owns the home-page "At a glance" chart and
the layouts. The skill's job is to emit clean data + a clear spec. In
`PRODUCT-ARTICLES.md` the rendering contract describes the component the
destination should build; the `build:` frontmatter block is its data source.

A good infographic for a build story shows, at a glance:
- the headline trio — **time · code · tests** (the "production tool, one day"
  proof);
- the agentic-effort row — sessions · turns · tokens generated · cache ratio;
- the model + harness credits — what built it, what drives it now.

Keep it honest, keep it scannable, and make sure every figure on it traces back
to `build-metrics.json`. If you quote a number in the prose that isn't in the
mined JSON, that's a bug — either add the source or cut the number.
