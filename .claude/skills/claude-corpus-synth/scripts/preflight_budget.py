"""Pre-flight session-token budget gate for claude-corpus-synth.

Estimates the CC-session token cost of generating N corpus rows in-CC-session,
projects against the user's weekly Max plan cap, and blocks for confirm. No
Claude calls — pure math + optional `/usage` paste parsing.

Cost model (in-CC-session, no subprocess):
  per_row_tokens = avg_output_tok + tool_call_overhead + prompt_input_tok
                 + amortized_cache_read

  where (defaults, override by flag):
    tool_call_overhead     = 500   (Edit-append tool payload framing)
    prompt_input_tok       = 300   (queue row's prompt + skill context per row)
    amortized_cache_read   = 0.5 × avg_output_tok × N / N
                           = 0.5 × avg_output_tok   (per row, contextual growth)

  total_session_tokens = N × per_row_tokens

The amortized-cache-read approximation captures that each row's response
becomes part of the next row's input cache_read until /clear or session end.
Cache reads are cheap ($0.30/M Sonnet) but they count against the cap.

Sonnet-equivalent hours conversion: ~400K tok/hr (community empirical).
Max plan tiers + caps published per tier.

Exit codes:
  0 — approved (user confirmed, or --yes)
  1 — declined (user said no)
  2 — over-cap (projected post-run > 95% of weekly cap low-bound)
  3 — bad input

Usage:
  python preflight_budget.py --rows 25000 --avg-output-tok 1976
  echo "<usage paste>" | python preflight_budget.py --rows 25000 --avg-output-tok 1976 --paste-usage -
"""
from __future__ import annotations

import argparse
import re
import sys

CAP_TIERS = {
    "max5x":  {"sonnet_hr_low": 140, "sonnet_hr_high": 280},
    "max20x": {"sonnet_hr_low": 240, "sonnet_hr_high": 480},
    "pro":    {"sonnet_hr_low":  28, "sonnet_hr_high":  56},
}

SONNET_TOK_PER_HR = 400_000          # community-measured throughput
DEFAULT_ROWS_PER_SESSION = 200       # how many rows fit in one CC session before /clear
DEFAULT_TOOL_CALL_OVERHEAD = 500     # tokens of Edit-append tool framing per row
DEFAULT_PROMPT_INPUT = 300           # tokens of prompt + skill context per row


def parse_usage_paste(text: str) -> dict | None:
    """Extract current weekly-cap % from a pasted `/usage` block.

    /usage output format varies; we try a couple of common shapes and return
    None on failure (caller falls back to estimate-only).
    """
    if not text:
        return None
    m = re.search(r"[Cc]urrent\s+week.*?(\d+(?:\.\d+)?)\s*%", text, re.DOTALL)
    if m:
        return {"current_pct": float(m.group(1))}
    m = re.search(r"(\d+(?:\.\d+)?)\s*%[^\n]{0,40}(weekly|used|limit)", text, re.IGNORECASE)
    if m:
        return {"current_pct": float(m.group(1))}
    return None


def fmt_block(
    rows: int,
    avg_output_tok: int,
    tier: str,
    current_pct: float | None,
    rows_per_session: int,
    tool_call_overhead: int,
    prompt_input: int,
) -> tuple[str, int]:
    """Return (markdown_block, exit_recommendation).

    exit_recommendation: 1 = normal user confirm needed, 2 = over-cap, 3 = bad input.
    """
    if tier not in CAP_TIERS:
        return f"ERROR: unknown --cap-tier {tier!r} (pick one of {list(CAP_TIERS)})", 3

    cap = CAP_TIERS[tier]

    amortized_cache_read = 0.5 * avg_output_tok  # per row, averaged over session
    per_row_tokens = avg_output_tok + tool_call_overhead + prompt_input + amortized_cache_read
    total_session_tokens = rows * per_row_tokens

    projected_hr = total_session_tokens / SONNET_TOK_PER_HR
    pct_low = 100 * projected_hr / cap["sonnet_hr_high"]   # best case (high cap)
    pct_high = 100 * projected_hr / cap["sonnet_hr_low"]   # worst case (low cap)
    pct_mid = 100 * projected_hr / ((cap["sonnet_hr_low"] + cap["sonnet_hr_high"]) / 2)

    n_sessions = max(1, -(-rows // rows_per_session))  # ceil divide
    # In-session generation rate is ~30s/row in measured CC usage.
    wall_per_session_hr = (rows_per_session * 30) / 3600

    lines = []
    lines.append(f"## Pre-flight: claude-corpus-synth budget gate ({tier})")
    lines.append("")
    lines.append(f"- **Rows:** {rows:,}")
    lines.append(f"- **Avg output tokens/row:** {avg_output_tok:,}")
    lines.append(f"- **Per-row session-token cost (model):**")
    lines.append(f"    output {avg_output_tok:,} + tool_call {tool_call_overhead} + prompt {prompt_input} "
                 f"+ cache_read {int(amortized_cache_read):,} ≈ **{int(per_row_tokens):,} tok/row**")
    lines.append(f"- **Projected session-token total:** {int(total_session_tokens):,} (~{total_session_tokens/1e6:.1f}M)")
    lines.append(f"- **Sonnet-equivalent hours:** {projected_hr:.1f} hr (assumes {SONNET_TOK_PER_HR:,} tok/hr)")
    lines.append(f"- **% of weekly cap ({tier}):** **{pct_mid:.1f}% mid** · {pct_low:.1f}% best / {pct_high:.1f}% worst")
    lines.append(f"- **Estimated CC sessions to complete:** ~**{n_sessions}** (at {rows_per_session} rows/session)")
    lines.append(f"- **Wall per session:** ~{wall_per_session_hr:.1f}h ({'fits 5h window' if wall_per_session_hr <= 4 else 'EXCEEDS 4h — split sessions'})")

    if n_sessions > 1:
        # If total cap > 100%, must span multiple weekly cycles
        weeks_needed = max(1, int(pct_high / 100) + (1 if pct_high % 100 > 50 else 0))
        if weeks_needed > 1:
            lines.append(f"- **Weekly cycles needed:** ~**{weeks_needed}** (spread to keep per-week consumption tolerable)")

    if current_pct is not None:
        total_low = current_pct + pct_low
        total_mid = current_pct + pct_mid
        total_high = current_pct + pct_high
        lines.append("")
        lines.append(f"- **Current weekly usage (from /usage paste):** {current_pct:.1f}%")
        lines.append(f"- **Projected post-run total this week:** **{total_mid:.1f}% mid** · "
                     f"{total_low:.1f}% best / {total_high:.1f}% worst")
        if total_high > 95:
            lines.append("")
            lines.append(f"  ⚠️  **OVER-CAP RISK** — worst-case post-run = {total_high:.1f}% of this week's cap.")
            return "\n".join(lines), 2

    return "\n".join(lines), 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--avg-output-tok", type=int, required=True,
                   help="Measured avg output tokens/row from dry-run (no default — must measure)")
    p.add_argument("--cap-tier", default="max20x", choices=list(CAP_TIERS))
    p.add_argument("--paste-usage", default=None,
                   help="Path to file with pasted /usage output (or '-' for stdin)")
    p.add_argument("--rows-per-session", type=int, default=DEFAULT_ROWS_PER_SESSION)
    p.add_argument("--tool-call-overhead", type=int, default=DEFAULT_TOOL_CALL_OVERHEAD)
    p.add_argument("--prompt-input", type=int, default=DEFAULT_PROMPT_INPUT)
    p.add_argument("--yes", action="store_true",
                   help="Skip the interactive confirm prompt (still blocks on over-cap)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    current_pct = None
    if args.paste_usage:
        text = sys.stdin.read() if args.paste_usage == "-" else open(args.paste_usage).read()
        parsed = parse_usage_paste(text)
        if parsed:
            current_pct = parsed["current_pct"]
        else:
            print("(could not parse /usage paste — proceeding with estimate-only)", file=sys.stderr)

    block, rec = fmt_block(
        args.rows, args.avg_output_tok, args.cap_tier, current_pct,
        args.rows_per_session, args.tool_call_overhead, args.prompt_input,
    )
    print(block)
    print()

    if rec == 3:
        return 3
    if rec == 2 and not args.yes:
        print("Refusing to auto-approve. Re-run with --yes if you accept the over-cap risk.", file=sys.stderr)
        return 2
    if args.yes:
        print("Approved via --yes.")
        return 0
    try:
        ans = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        print("No TTY — pass --yes to confirm non-interactively.", file=sys.stderr)
        return 1
    if ans == "y":
        return 0
    print("Declined.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
