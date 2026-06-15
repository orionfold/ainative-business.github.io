"""Guided onboarding TUI for Orionfold Arena Field Edition — ``onboard``.

``fieldkit field-edition onboard`` is the customer-shaped front door: a
Rich-rendered **linear** flow over the headless ``up`` engine + ``doctor``
preflight. It owns only the *experience* — ``up``/``doctor`` still do the work
underneath. The bootstrap (``get-orionfold.sh``) calls ``onboard`` for the
``curl | sh`` path.

Why Rich linear, not Textual: a Textual app needs a full interactive TTY and
breaks under ``curl | sh`` / CI / pipes. Rich degrades to plain output when
``stdout`` is not a TTY, so the same code path is scriptable and interactive.

The flow:

1. **Welcome** — a premium-voice greeting ("your AI Researcher").
2. **Preflight** — render ``run_doctor()``'s matrix; on a miss show each
   ``fix`` and stop honestly (no half-start).
3. **NGC key** — if ``read_ngc_api_key()`` is ``None`` and the embedder needs
   one, point the customer at the free key page and capture + persist what they
   paste (``write_ngc_api_key`` → ``~/.nim/secrets.env``). Blank → honest abort.
4. **Bring-up** — drive ``run_up`` and narrate each phase as it happens; show a
   named download manifest when ``pull`` starts; advance one "while you wait"
   value card per phase so the customer reads the product *as* it installs.
5. **Finish** — a call-to-action + auto-open the ``/arena/welcome/`` first-run
   surface (keeps the welcome → chat journey intact).
6. **Honest failure** — a stopped phase prints its ``fix`` + the re-entrant
   "run ``onboard`` again" hint (``up`` checkpoints and resumes).

Everything here is unit-testable without Docker/GPU/network: the value cards +
manifest + renderable builders are pure, and :func:`run_onboard` takes injectable
seams (``console`` / ``prompt_fn`` / ``executor`` / ``doctor_fn`` / ``opener``).
No ``anthropic`` / ``claude-agent-sdk`` (``feedback_llm_skill_pattern``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fieldkit.field_edition import compose as _compose
from fieldkit.field_edition.compose import FieldEditionConfig
from fieldkit.field_edition.up import PHASES, UpResult, run_up

__all__ = [
    "VALUE_CARDS",
    "ValueCard",
    "OnboardResult",
    "COCKPIT_WELCOME_URL",
    "download_manifest",
    "ensure_ngc_key",
    "run_onboard",
]

#: The first-run surface the finish step opens — the welcome → chat journey.
COCKPIT_WELCOME_URL = "http://127.0.0.1:7866/arena/welcome/"

#: Where a customer gets a free NGC key (the embedder's silent prerequisite).
NGC_KEY_URL = "https://org.ngc.nvidia.com/setup/api-keys"


@dataclass(frozen=True)
class ValueCard:
    """One "while you wait" orientation card (Part F, content locked)."""

    title: str
    body: str


#: The six locked cards — rotate through them as the install progresses so the
#: ~2-10 min pull pre-teaches the product instead of being dead air.
VALUE_CARDS: tuple[ValueCard, ...] = (
    ValueCard(
        "What your Researcher is",
        "A local model that answers only from your corpus, with citations. "
        "Private, yours, running on your Spark — nothing leaves the box.",
    ),
    ValueCard(
        "Grounded, not guessing",
        "It retrieves from your sources first, then writes. You see the sources "
        "on every reply.",
    ),
    ValueCard(
        "Honest refusals",
        "Ask outside your corpus and it says so — with no sources — instead of "
        "making something up. Trust by construction.",
    ),
    ValueCard(
        "What we are downloading now",
        "(1) your Advisor model, 2.84 GB · (2) your corpus, already bundled · "
        "(3) container images, cached.",
    ),
    ValueCard(
        "What verify is about to prove",
        "recall@5 0.977 · citations 95.7% · honest refusals 9/9. Receipts, not "
        "promises.",
    ),
    ValueCard(
        "First three things to try",
        '"What does the Orionfold Arena do?" · "Summarize the Field Edition '
        'license terms." · "What is not in my corpus?" (watch it refuse honestly).',
    ),
)


def download_manifest() -> list[dict[str, str]]:
    """The named download manifest (replaces a raw tqdm bar): what each piece is
    + what it unlocks. Pure data so the renderer + tests share one source."""
    return [
        {"item": "Your Advisor model", "size": "2.84 GB", "note": "Q4_K_M, downloading now"},
        {"item": "Your corpus (182 sources)", "size": "bundled", "note": "ships in the wheel — instant"},
        {"item": "Container images", "size": "cached", "note": "pgvector · embedder · serving lane"},
    ]


# --- Renderable builders (pure: return Rich renderables) ---------------------


def welcome_panel() -> Panel:
    """The opening greeting."""
    body = Text.assemble(
        ("Welcome to your Arena.\n\n", "bold"),
        "You are about to bring up your AI Researcher — a local model that reads "
        "your corpus and answers only from it, every time with sources. This "
        "guide will get a free key if you need one, download your model, and "
        "open the cockpit warm.\n\n",
        ("Nothing leaves your box.", "italic"),
    )
    return Panel(body, title="✦ Orionfold Arena · Field Edition", border_style="cyan", padding=(1, 2))


def doctor_table(report: object) -> Table:
    """Render a DoctorReport's matrix as a check table (✓ / ✗ + reason)."""
    table = Table(title="Preflight — does this box match the tested matrix?", expand=False)
    table.add_column("check")
    table.add_column("found")
    table.add_column("tested")
    table.add_column("")
    for r in getattr(report, "results", ()):  # CheckResult
        mark = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
        found = r.found or "[dim]not found[/dim]"
        table.add_row(r.label, str(found), r.tested, mark)
    return table


def doctor_fixes(report: object) -> Group:
    """The per-failure fix lines for a failed preflight."""
    lines: list[Text] = [Text("Preflight failed — fix these, then run onboard again:", style="bold red")]
    for r in getattr(report, "failures", ()):
        lines.append(Text.assemble((f"  • {r.label}: ", "bold"), r.reason or r.status))
        if r.fix:
            lines.append(Text(f"      → {r.fix}", style="cyan"))
    return Group(*lines)


def ngc_prompt_panel() -> Panel:
    """The 'go get a free key' panel shown when no NGC key is found."""
    body = Text.assemble(
        "Your Cortex embedder needs a free NVIDIA NGC key (one-time).\n\n",
        ("Get one here: ", ""),
        (NGC_KEY_URL, "cyan underline"),
        "\n\nThen paste it below. It is saved to ~/.nim/secrets.env on this box "
        "and never leaves it.",
    )
    return Panel(body, title="NGC API key needed", border_style="yellow", padding=(1, 2))


def manifest_table() -> Table:
    """The named download manifest."""
    table = Table(title="Downloading — what and why", expand=False)
    table.add_column("piece")
    table.add_column("size")
    table.add_column("note", style="dim")
    for row in download_manifest():
        table.add_row(row["item"], row["size"], row["note"])
    return table


def card_panel(card: ValueCard) -> Panel:
    """One while-you-wait value card."""
    return Panel(
        Text(card.body),
        title=f"While you wait · {card.title}",
        border_style="blue",
        padding=(1, 2),
    )


def cta_panel(welcome_url: str = COCKPIT_WELCOME_URL) -> Panel:
    """The finish call-to-action."""
    body = Text.assemble(
        ("✅ Your Advisor is warm.\n\n", "bold green"),
        "Open the cockpit and ask it:\n",
        ('  "What does the Orionfold Arena do?"\n', "italic"),
        "\nOpening your Arena at\n",
        (welcome_url, "cyan"),
    )
    return Panel(body, title="You are live", border_style="green", padding=(1, 2))


def failure_panel(stopped_at: str, fix: str, detail: str = "") -> Panel:
    """An honest, recoverable stop."""
    body = Text.assemble(
        (f"Stopped at the {stopped_at} step.\n", "bold red"),
        (f"{detail}\n\n" if detail else "\n"),
        ("→ fix: ", "bold"),
        (f"{fix}\n\n" if fix else "see the message above\n\n"),
        "Re-run ",
        ("fieldkit field-edition onboard", "cyan"),
        " to resume — it picks up from this step.",
    )
    return Panel(body, title="Needs a fix", border_style="red", padding=(1, 2))


# --- NGC key capture ---------------------------------------------------------


def ensure_ngc_key(
    console: Console,
    *,
    prompt_fn: Callable[[], str],
    read_fn: Callable[[], Optional[str]] | None = None,
    write_fn: Callable[[str], object] | None = None,
) -> Optional[str]:
    """Return a usable NGC key, capturing + persisting one if absent.

    Resolves an existing key first; otherwise shows the 'get a key' panel,
    prompts (the caller's ``prompt_fn``), writes it to ``~/.nim/secrets.env`` +
    sets it live in ``os.environ``, and returns it. A blank paste returns
    ``None`` so the caller can abort honestly with the fix.
    """
    read = read_fn or _compose.read_ngc_api_key
    write = write_fn or _compose.write_ngc_api_key
    existing = read()
    if existing:
        return existing
    console.print(ngc_prompt_panel())
    pasted = (prompt_fn() or "").strip()
    if not pasted:
        return None
    write(pasted)
    os.environ["NGC_API_KEY"] = pasted
    return pasted


# --- The orchestrator --------------------------------------------------------


@dataclass
class OnboardResult:
    """The outcome of a guided onboard run."""

    ok: bool
    stopped_at: Optional[str]  # "doctor" | "ngc" | an up phase key | None
    fix: str
    ngc_captured: bool
    opened: Optional[str]  # the URL auto-opened on success, else None


class _Presenter:
    """Print-as-you-go narrator over ``run_up``'s ▶/✓/✗ events. Deterministic
    (no threads/timers): advances one value card per phase start, and shows the
    download manifest when ``pull`` begins. Renders via the injected console, so
    a non-TTY console (tests, ``curl|sh`` capture) just gets plain text."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._card = 0

    def on_event(self, msg: str) -> None:
        if msg.startswith("▶"):
            # "▶ <label>: <detail>"
            self.console.print(Text(msg, style="bold"))
            if msg.startswith("▶ Model pull"):
                self.console.print(manifest_table())
            # Advance a while-you-wait card as each phase starts.
            if self._card < len(VALUE_CARDS):
                self.console.print(card_panel(VALUE_CARDS[self._card]))
                self._card += 1
        elif msg.startswith("✓"):
            self.console.print(Text(msg, style="green"))
        elif msg.startswith("✗"):
            self.console.print(Text(msg, style="red"))
        else:
            self.console.print(Text(msg, style="dim"))


def run_onboard(
    config: FieldEditionConfig | None = None,
    *,
    console: Console | None = None,
    prompt_fn: Callable[[], str] | None = None,
    executor: object | None = None,
    doctor_fn: Callable[[], object] | None = None,
    opener: Callable[[str], object] | None = None,
    auto_open: bool = True,
    with_verify: bool = False,
    force: bool = False,
) -> OnboardResult:
    """Drive the guided onboarding flow. Returns an :class:`OnboardResult`;
    never raises for an ordinary failure (renders it + reports ``ok=False``)."""
    cfg = config or _compose.default_config()
    con = console or Console()

    con.print(welcome_panel())

    # 1) Preflight (display) — run_up's matrix phase re-checks it idempotently.
    if doctor_fn is None:
        from fieldkit.field_edition.doctor import run_doctor as doctor_fn  # type: ignore
    report = doctor_fn()
    con.print(doctor_table(report))
    if not getattr(report, "ok", False):
        con.print(doctor_fixes(report))
        return OnboardResult(ok=False, stopped_at="doctor", fix="resolve the matrix misses above", ngc_captured=False, opened=None)

    # 2) NGC key (only when the embedder needs one).
    ngc_captured = False
    needs_ngc = getattr(getattr(cfg, "embedder", None), "needs_ngc_key", False)
    if needs_ngc and _compose.read_ngc_api_key() is None:
        pf = prompt_fn or (lambda: con.input("  NGC key: "))
        before = os.environ.get("NGC_API_KEY")
        key = ensure_ngc_key(con, prompt_fn=pf)
        if not key:
            return OnboardResult(
                ok=False, stopped_at="ngc",
                fix=f"get a free key at {NGC_KEY_URL}, then run onboard again",
                ngc_captured=False, opened=None,
            )
        ngc_captured = key != before

    # 3) Bring-up — narrate each phase as it runs.
    presenter = _Presenter(con)
    result: UpResult = run_up(
        cfg,
        executor=executor,  # None → LiveExecutor
        with_verify=with_verify,
        force=force,
        on_event=presenter.on_event,
    )
    if not result.ok:
        detail = {p.key: p.detail for p in PHASES}.get(result.failed or "", "")
        con.print(failure_panel(result.failed or "?", result.fix, detail))
        return OnboardResult(ok=False, stopped_at=result.failed, fix=result.fix, ngc_captured=ngc_captured, opened=None)

    # 4) Finish — CTA + auto-open the welcome surface.
    con.print(cta_panel())
    opened: Optional[str] = None
    if auto_open:
        open_fn = opener
        if open_fn is None:
            import webbrowser

            open_fn = webbrowser.open
        try:
            open_fn(COCKPIT_WELCOME_URL)
            opened = COCKPIT_WELCOME_URL
        except Exception:  # noqa: BLE001 — a headless box has no browser; not fatal
            opened = None
    return OnboardResult(ok=True, stopped_at=None, fix="", ngc_captured=ngc_captured, opened=opened)
