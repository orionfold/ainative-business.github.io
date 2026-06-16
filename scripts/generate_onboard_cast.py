#!/usr/bin/env python3
"""Generate the `field-edition onboard` marketing cast (asciicast v2).

The guided onboarding TUI is deterministic + Rich-rendered, but a *live*
`field-edition onboard` capture would need a real NGC key, a ~2-10 min model
pull, and a full container bring-up — too slow + network-bound to record
cleanly (HANDOFF "TUI marketing demo" build note). So this driver replays the
REAL renderable builders from `fieldkit.field_edition.onboard` — the same
welcome panel, preflight table, NGC panel, download manifest, while-you-wait
value cards, and CTA the customer actually sees — into a faithful synthetic
`.cast`. Nothing is hand-mocked except the passing DoctorReport (a clean box)
and the phase event stream (the exact `▶ <label>: <detail>` / `✓` strings
`run_up` emits), both pulled from the real `PHASES` table.

Output: products/orionfold-arena/casts/onboard.cast  (+ public mirror).
Re-run after any onboard.py copy/flow change so the cast stays honest.

    PYTHONPATH=fieldkit/src /tmp/fk/bin/python scripts/generate_onboard_cast.py
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from rich.console import Console

from fieldkit.field_edition import onboard as ob
from fieldkit.field_edition.doctor import CheckResult, DoctorReport, TESTED_MATRIX
from fieldkit.field_edition.up import PHASES

WIDTH = 100
HEIGHT = 34
REPO = Path(__file__).resolve().parents[1]
CAST = REPO / "products/orionfold-arena/casts/onboard.cast"
PUBLIC = REPO / "public/products/orionfold-arena/casts/onboard.cast"

# A clean box that matches the tested matrix — the happy path the cast shows.
_FOUND = {
    "DGX OS": "7.4.0",
    "NVIDIA driver": "580.159.03",
    "CUDA runtime": "13.0",
    "Docker CE": "28.1.1",
    "NVIDIA Container Toolkit": "1.17.8",
}


def passing_report() -> DoctorReport:
    results = tuple(
        CheckResult(
            key=c.key,
            label=c.label,
            found=_FOUND.get(c.label, c.tested),
            status="ok",
            tested=c.tested,
            reason="",
            fix=c.fix,
        )
        for c in TESTED_MATRIX
    )
    return DoctorReport(results=results)


def render(renderable) -> str:
    """Render a Rich renderable to a real-terminal ANSI string."""
    buf = io.StringIO()
    con = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        width=WIDTH,
        highlight=False,
        emoji=False,
    )
    con.print(renderable)
    return buf.getvalue()


class CastWriter:
    """Accumulate asciicast v2 output events with a virtual clock."""

    def __init__(self) -> None:
        self.events: list[tuple[float, str]] = []
        self.t = 0.0

    def wait(self, seconds: float) -> None:
        self.t += seconds

    def out(self, text: str) -> None:
        # Real PTYs terminate lines with CRLF; Rich emits bare LF. Without the
        # CR the player's terminal emulator stair-steps every line.
        self.events.append((round(self.t, 3), text.replace("\n", "\r\n")))

    def panel(self, renderable, *, hold: float = 1.6, lead: float = 0.35) -> None:
        self.wait(lead)
        self.out(render(renderable))
        self.wait(hold)

    def type_command(self, prompt: str, command: str) -> None:
        self.out(prompt)
        self.wait(0.4)
        for ch in command:
            self.out(ch)
            self.wait(0.045)
        self.wait(0.5)
        self.out("\r\n")

    def line(self, text: str, *, hold: float = 0.5, lead: float = 0.15) -> None:
        self.wait(lead)
        self.out(text + "\n")
        self.wait(hold)

    def dump(self) -> str:
        header = {
            "version": 2,
            "width": WIDTH,
            "height": HEIGHT,
            "title": "fieldkit field-edition onboard",
            "env": {"TERM": "xterm-256color"},
        }
        lines = [json.dumps(header)]
        for t, data in self.events:
            lines.append(json.dumps([t, "o", data]))
        return "\n".join(lines) + "\n"


# ANSI helpers for the few non-Rich shell lines (prompt + simulated paste echo).
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
BOLD = "\x1b[1m"
RST = "\x1b[0m"


def build() -> str:
    w = CastWriter()

    # 0) The install one-liner, typed out.
    w.type_command(f"{GREEN}${RST} ", "fieldkit field-edition onboard")
    w.wait(0.6)

    # 1) Welcome.
    w.panel(ob.welcome_panel(), hold=2.4)

    # 2) Preflight — the real doctor table on a clean box.
    w.panel(ob.doctor_table(passing_report()), hold=2.0)
    w.line(f"{GREEN}✓{RST} Box matches the tested matrix.", hold=1.0)

    # 3) NGC key capture — panel, then a simulated paste (masked).
    w.panel(ob.ngc_prompt_panel(), hold=2.2)
    w.out("  NGC key: ")
    w.wait(0.6)
    w.out(f"{DIM}nvapi-••••••••••••••••••••••••••••••{RST}")
    w.wait(0.5)
    w.out("\r\n")
    w.line(f"{GREEN}✓{RST} Saved to ~/.nim/secrets.env — never leaves this box.", hold=1.4)

    # 4) Bring-up — narrate the real PHASES the way the _Presenter does:
    #    "▶ <label>: <detail>" on start, the manifest when Model pull begins,
    #    one while-you-wait card per phase, "✓ <label>" on completion.
    card = 0
    for phase in PHASES:
        if phase.optional:
            continue
        w.line(f"{BOLD}▶ {phase.label}: {phase.detail}{RST}", hold=0.6)
        if phase.label == "Model pull":
            w.panel(ob.manifest_table(), hold=1.8, lead=0.2)
        if card < len(ob.VALUE_CARDS):
            w.panel(ob.card_panel(ob.VALUE_CARDS[card]), hold=2.2, lead=0.2)
            card += 1
        w.line(f"{GREEN}✓ {phase.label}{RST}", hold=0.5)

    # 5) Finish — the CTA panel.
    w.wait(0.4)
    w.panel(ob.cta_panel(), hold=3.0)
    w.line(f"{CYAN}Opening {ob.COCKPIT_WELCOME_URL}{RST}", hold=2.5)

    return w.dump()


def main() -> None:
    cast = build()
    CAST.parent.mkdir(parents=True, exist_ok=True)
    CAST.write_text(cast, encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CAST, PUBLIC)
    last_t = max(json.loads(l)[0] for l in cast.splitlines()[1:])
    print(f"wrote {CAST.relative_to(REPO)} ({len(cast.splitlines())} events, ~{last_t:.0f}s)")
    print(f"wrote {PUBLIC.relative_to(REPO)}")


if __name__ == "__main__":
    main()
