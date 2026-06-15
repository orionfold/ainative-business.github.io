# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the guided onboarding TUI (fieldkit.field_edition.onboard).

Box-independent: the value cards + manifest + renderable builders are pure, and
run_onboard takes injectable seams (console / prompt_fn / executor / doctor_fn /
opener) so the whole flow runs without Docker / GPU / network / a browser.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

import fieldkit.field_edition.compose as compose_mod
import fieldkit.field_edition.onboard as ob
from fieldkit.cli import app
from fieldkit.field_edition.compose import FieldEditionConfig, write_ngc_api_key
from fieldkit.field_edition.doctor import evaluate_matrix
from fieldkit.field_edition.up import Executor, PhaseError
from typer.testing import CliRunner

runner = CliRunner()


def _tmp_config(tmp_path: Path) -> FieldEditionConfig:
    return FieldEditionConfig(home=tmp_path / "of", model_store=tmp_path / "of" / "models")


class _FakeExecutor(Executor):
    """Records dispatched phases; optionally fails the named one."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.ran: list[str] = []
        self.fail_on = fail_on

    def dispatch(self, key: str, config: FieldEditionConfig) -> None:
        self.ran.append(key)
        if key == self.fail_on:
            raise PhaseError(f"{key} blew up", fix="do the thing")


def _green_report():
    return evaluate_matrix(
        {
            "dgx_os": "7.4.0",
            "driver": "580.159.03",
            "cuda": "13.0",
            "docker": "Docker version 29.2.1",
            "container_toolkit": "NVIDIA Container Toolkit CLI version 1.19.1",
        }
    )


def _red_report():
    probes = {
        "dgx_os": "6.0.0",  # too old
        "driver": "580.159.03",
        "cuda": "13.0",
        "docker": "Docker version 29.2.1",
        "container_toolkit": "NVIDIA Container Toolkit CLI version 1.19.1",
    }
    return evaluate_matrix(probes)


def _cap() -> Console:
    """A non-terminal console that captures to a buffer (plain-text path)."""
    return Console(file=io.StringIO(), width=100, force_terminal=False)


def _text(con: Console) -> str:
    return con.file.getvalue()


# --- pure data ---------------------------------------------------------------


def test_value_cards_and_manifest_are_locked() -> None:
    assert len(ob.VALUE_CARDS) == 6
    titles = [c.title for c in ob.VALUE_CARDS]
    assert "Honest refusals" in titles
    assert "What we are downloading now" in titles
    man = ob.download_manifest()
    assert len(man) == 3
    assert any("2.84 GB" == r["size"] for r in man)


def test_renderable_builders_construct() -> None:
    con = _cap()
    con.print(ob.welcome_panel())
    con.print(ob.doctor_table(_green_report()))
    con.print(ob.manifest_table())
    con.print(ob.card_panel(ob.VALUE_CARDS[0]))
    con.print(ob.cta_panel())
    out = _text(con)
    assert "Welcome to your Arena" in out
    assert "2.84 GB" in out
    assert "What does the Orionfold Arena do" in out


# --- write_ngc_api_key -------------------------------------------------------


def test_write_ngc_api_key_creates_and_masks(tmp_path: Path) -> None:
    secrets = tmp_path / ".nim" / "secrets.env"
    # placeholder-shaped fake so the repo secret-scan doesn't flag the fixture.
    path = write_ngc_api_key("placeholder-ngc-0001", secrets_path=secrets)
    assert path == secrets
    assert secrets.read_text() == "NGC_API_KEY=placeholder-ngc-0001\n"
    # mode 0600 (best-effort)
    assert (secrets.stat().st_mode & 0o777) in (0o600, 0o644)


def test_write_ngc_api_key_preserves_other_lines(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("# header\nFOO=bar\nNGC_API_KEY=old\n")
    write_ngc_api_key("new-key", secrets_path=secrets)
    text = secrets.read_text()
    assert "FOO=bar" in text
    assert "# header" in text
    assert "NGC_API_KEY=new-key" in text
    assert "old" not in text


def test_write_ngc_api_key_rejects_blank(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_ngc_api_key("   ", secrets_path=tmp_path / "secrets.env")


# --- ensure_ngc_key ----------------------------------------------------------


def test_ensure_ngc_key_returns_existing_without_prompting() -> None:
    con = _cap()
    calls = {"prompted": False}

    def prompt():
        calls["prompted"] = True
        return "should-not-be-used"

    key = ob.ensure_ngc_key(con, prompt_fn=prompt, read_fn=lambda: "existing-key")
    assert key == "existing-key"
    assert calls["prompted"] is False


def test_ensure_ngc_key_captures_and_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    con = _cap()
    monkeypatch.setattr(ob.os, "environ", dict(ob.os.environ))
    written: dict[str, str] = {}
    key = ob.ensure_ngc_key(
        con,
        prompt_fn=lambda: "  pasted-key  ",
        read_fn=lambda: None,
        write_fn=lambda k: written.setdefault("key", k),
    )
    assert key == "pasted-key"
    assert written["key"] == "pasted-key"
    assert ob.os.environ["NGC_API_KEY"] == "pasted-key"
    assert "NGC API key needed" in _text(con)


def test_ensure_ngc_key_blank_returns_none() -> None:
    con = _cap()
    key = ob.ensure_ngc_key(con, prompt_fn=lambda: "   ", read_fn=lambda: None)
    assert key is None


# --- run_onboard -------------------------------------------------------------


def test_run_onboard_happy_path_opens_welcome(tmp_path: Path) -> None:
    con = _cap()
    exe = _FakeExecutor()
    opened: list[str] = []
    # open-embedder config → no NGC capture needed for the happy path.
    cfg = _tmp_config(tmp_path).with_open_embedder()
    result = ob.run_onboard(
        cfg,
        console=con,
        executor=exe,
        doctor_fn=_green_report,
        opener=lambda url: opened.append(url),
    )
    assert result.ok is True
    assert result.stopped_at is None
    assert opened == [ob.COCKPIT_WELCOME_URL]
    assert result.opened == ob.COCKPIT_WELCOME_URL
    # all live phases dispatched
    assert exe.ran == ["matrix", "bundle", "pull", "stack", "ingest", "sidecar", "resident"]
    out = _text(con)
    # narrated phases + manifest + while-you-wait cards + CTA
    assert "Model pull" in out
    assert "2.84 GB" in out
    assert "While you wait" in out
    assert "Your Advisor is warm" in out


def test_run_onboard_captures_ngc_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    con = _cap()
    monkeypatch.setattr(ob.os, "environ", dict(ob.os.environ))
    monkeypatch.delenv("NGC_API_KEY", raising=False)
    # default config needs an NGC key; force it absent + capture a paste.
    monkeypatch.setattr(compose_mod, "read_ngc_api_key", lambda *a, **k: None)
    written: dict[str, str] = {}
    monkeypatch.setattr(compose_mod, "write_ngc_api_key", lambda k, *a, **kw: written.setdefault("key", k))
    cfg = _tmp_config(tmp_path)  # NIM embedder → needs_ngc_key
    result = ob.run_onboard(
        cfg,
        console=con,
        executor=_FakeExecutor(),
        doctor_fn=_green_report,
        prompt_fn=lambda: "nvapi-pasted",
        opener=lambda url: None,
    )
    assert result.ok is True
    assert result.ngc_captured is True
    assert written["key"] == "nvapi-pasted"


def test_run_onboard_stops_on_doctor_failure(tmp_path: Path) -> None:
    con = _cap()
    exe = _FakeExecutor()
    result = ob.run_onboard(
        _tmp_config(tmp_path).with_open_embedder(),
        console=con,
        executor=exe,
        doctor_fn=_red_report,
        opener=lambda url: None,
    )
    assert result.ok is False
    assert result.stopped_at == "doctor"
    assert exe.ran == []  # never reached bring-up
    assert "Preflight failed" in _text(con)


def test_run_onboard_blank_ngc_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    con = _cap()
    monkeypatch.setattr(ob.os, "environ", dict(ob.os.environ))
    monkeypatch.delenv("NGC_API_KEY", raising=False)
    monkeypatch.setattr(compose_mod, "read_ngc_api_key", lambda *a, **k: None)
    result = ob.run_onboard(
        _tmp_config(tmp_path),
        console=con,
        executor=_FakeExecutor(),
        doctor_fn=_green_report,
        prompt_fn=lambda: "",  # blank paste
        opener=lambda url: None,
    )
    assert result.ok is False
    assert result.stopped_at == "ngc"


def test_run_onboard_stops_on_phase_failure(tmp_path: Path) -> None:
    con = _cap()
    exe = _FakeExecutor(fail_on="stack")
    result = ob.run_onboard(
        _tmp_config(tmp_path).with_open_embedder(),
        console=con,
        executor=exe,
        doctor_fn=_green_report,
        opener=lambda url: None,
    )
    assert result.ok is False
    assert result.stopped_at == "stack"
    assert result.opened is None
    assert "Needs a fix" in _text(con)


def test_run_onboard_no_open_skips_browser(tmp_path: Path) -> None:
    con = _cap()
    opened: list[str] = []
    result = ob.run_onboard(
        _tmp_config(tmp_path).with_open_embedder(),
        console=con,
        executor=_FakeExecutor(),
        doctor_fn=_green_report,
        auto_open=False,
        opener=lambda url: opened.append(url),
    )
    assert result.ok is True
    assert opened == []
    assert result.opened is None


# --- CLI registration --------------------------------------------------------


def test_onboard_command_registered() -> None:
    res = runner.invoke(app, ["field-edition", "onboard", "--help"])
    assert res.exit_code == 0
    assert "Guided onboarding" in res.stdout
    assert "--no-open" in res.stdout
