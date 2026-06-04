#!/usr/bin/env bash
# arena_lifecycle.sh — tear down / bring up the Orionfold Arena cockpit on the
# DGX Spark, optionally alongside a visible CDP-attached Chromium for
# browser-use mode (puppeteer-core / playwright-core connectOverCDP).
#
# Usage:
#   arena_lifecycle.sh up       [--browser|--no-browser]
#   arena_lifecycle.sh down     [--browser|--no-browser]
#   arena_lifecycle.sh restart  [--browser|--no-browser]
#   arena_lifecycle.sh status
#
# Default is --no-browser (cockpit only). Pass --browser to also launch/kill
# the visible Chromium. `down --browser` and `restart --browser` include the
# browser; plain `down`/`restart` leave any running browser alone on `down`
# (it's cheap to keep) but `restart --browser` always recycles it.
#
# Everything deterministic lives here so the skill body stays thin. Tunables
# are env-overridable; the defaults match the Spark operator setup.
set -uo pipefail

# ---- Tunables (env-overridable) -------------------------------------------
REPO_ROOT="${ARENA_REPO_ROOT:-/home/nvidia/ainative-business.github.io}"
VENV="${ARENA_VENV:-/tmp/arena-venv}"
COCKPIT_PORT="${ARENA_COCKPIT_PORT:-7866}"
CDP_PORT="${ARENA_CDP_PORT:-9222}"
CHROME_PROFILE="${ARENA_CHROME_PROFILE:-/tmp/arena-chrome-profile}"
CHROME_BIN="${ARENA_CHROME_BIN:-/snap/bin/chromium}"
DISPLAY_ID="${ARENA_DISPLAY:-:1}"
COCKPIT_LOG="${ARENA_COCKPIT_LOG:-/tmp/arena-cockpit.log}"
CHROME_LOG="${ARENA_CHROME_LOG:-/tmp/arena-chromium.log}"
ENV_FILE="${ARENA_ENV_FILE:-$REPO_ROOT/.env.local}"
# Page the browser parks on (and the cockpit URL we report).
ARENA_URL="http://127.0.0.1:${COCKPIT_PORT}/arena/leaderboard/"

COCKPIT_PAT='fieldkit arena up'            # pgrep -f pattern for the cockpit
CHROME_PAT="remote-debugging-port=${CDP_PORT}"  # pgrep -f pattern for the browser

# ---- Pretty output ---------------------------------------------------------
say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }
hdr()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# ---- Probes ----------------------------------------------------------------
cockpit_up() { curl -fs -m 2 "http://127.0.0.1:${COCKPIT_PORT}/healthz" >/dev/null 2>&1; }
cdp_up()     { curl -fs -m 2 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; }

# ---- Teardown --------------------------------------------------------------
down_cockpit() {
  if pgrep -f "$COCKPIT_PAT" >/dev/null 2>&1; then
    pkill -f "$COCKPIT_PAT" 2>/dev/null || true
    for _ in $(seq 1 10); do cockpit_up || break; sleep 0.5; done
  fi
  if cockpit_up; then err "cockpit still answering on :${COCKPIT_PORT}"; return 1; fi
  ok "cockpit down (:${COCKPIT_PORT} clear)"
}

down_browser() {
  if pgrep -f "$CHROME_PAT" >/dev/null 2>&1; then
    pkill -f "$CHROME_PAT" 2>/dev/null || true
    for _ in $(seq 1 10); do cdp_up || break; sleep 0.5; done
  fi
  if cdp_up; then err "CDP still answering on :${CDP_PORT}"; return 1; fi
  ok "browser down (:${CDP_PORT} clear)"
}

# ---- Bring-up --------------------------------------------------------------
ensure_venv() {
  if [ -x "$VENV/bin/fieldkit" ]; then return 0; fi
  warn "venv $VENV missing fieldkit — recreating (fieldkit[arena], ~1 min)"
  python3 -m venv "$VENV" || { err "venv create failed"; return 1; }
  "$VENV/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
  ( cd "$REPO_ROOT" && "$VENV/bin/pip" install -q -e './fieldkit[arena]' ) \
    || { err "fieldkit[arena] install failed"; return 1; }
  ok "venv rebuilt"
}

up_cockpit() {
  if cockpit_up; then ok "cockpit already up on :${COCKPIT_PORT}"; return 0; fi
  ensure_venv || return 1
  # Source .env.local so OpenRouter (and friends) are in the cockpit's env —
  # without this the cloud lanes are cold. set -a exports every assignment.
  if [ -f "$ENV_FILE" ]; then
    set -a; # shellcheck disable=SC1090
    . "$ENV_FILE"; set +a
  else
    warn "no $ENV_FILE — cloud lanes will be cold"
  fi
  # setsid --fork + </dev/null fully detaches the sidecar into its own session,
  # reparented to init — so this script never waits on it and a piped
  # invocation (e.g. `... | sed`) returns the moment health-check passes
  # instead of hanging until the long-lived cockpit exits. The --fork is the
  # crucial bit: plain `setsid … &` leaves the daemon a child of this shell,
  # which then blocks in `wait` at exit.
  ( cd "$REPO_ROOT" \
      && setsid --fork "$VENV/bin/fieldkit" arena up --no-open --repo-root . \
         </dev/null > "$COCKPIT_LOG" 2>&1 )
  for _ in $(seq 1 30); do cockpit_up && break; sleep 1; done
  if ! cockpit_up; then
    err "cockpit failed to come up — tail $COCKPIT_LOG"; tail -n 8 "$COCKPIT_LOG" 2>/dev/null; return 1
  fi
  # Confirm the OpenRouter key actually made it into the process env.
  local pid key
  pid="$(pgrep -f "$COCKPIT_PAT" | head -1)"
  if [ -n "${pid:-}" ] && grep -aqz 'OPENROUTER_API_KEY=sk-' "/proc/$pid/environ" 2>/dev/null; then
    ok "cockpit up on :${COCKPIT_PORT} (OpenRouter key loaded)"
  else
    warn "cockpit up on :${COCKPIT_PORT} but OpenRouter key NOT in env (cloud lanes cold)"
  fi
}

up_browser() {
  if cdp_up; then ok "browser already up on CDP :${CDP_PORT}"; return 0; fi
  [ -x "$CHROME_BIN" ] || { err "chromium not at $CHROME_BIN"; return 1; }
  # setsid --fork + </dev/null: same full-detach reasoning as the cockpit launch.
  DISPLAY="$DISPLAY_ID" setsid --fork "$CHROME_BIN" \
    --remote-debugging-port="${CDP_PORT}" \
    --user-data-dir="$CHROME_PROFILE" \
    --no-first-run --no-default-browser-check \
    "$ARENA_URL" </dev/null > "$CHROME_LOG" 2>&1
  for _ in $(seq 1 15); do cdp_up && break; sleep 1; done
  if ! cdp_up; then
    err "browser failed to expose CDP — tail $CHROME_LOG"; tail -n 8 "$CHROME_LOG" 2>/dev/null; return 1
  fi
  local ver; ver="$(curl -fs -m 2 "http://127.0.0.1:${CDP_PORT}/json/version" 2>/dev/null \
                    | sed -n 's/.*"Browser": *"\([^"]*\)".*/\1/p')"
  ok "browser up on CDP :${CDP_PORT} (${ver:-?}), parked on /arena/leaderboard/"
}

# ---- Status ----------------------------------------------------------------
do_status() {
  hdr "arena status"
  if cockpit_up; then
    local pid; pid="$(pgrep -f "$COCKPIT_PAT" | head -1)"
    ok "cockpit UP   :${COCKPIT_PORT} (pid ${pid:-?}) → http://127.0.0.1:${COCKPIT_PORT}/arena/"
  else
    say "cockpit DOWN :${COCKPIT_PORT}"
  fi
  if cdp_up; then
    local pid; pid="$(pgrep -f "$CHROME_PAT" | head -1)"
    ok "browser UP   CDP :${CDP_PORT} (pid ${pid:-?})"
  else
    say "browser DOWN CDP :${CDP_PORT}"
    # Self-diagnose the recurring trap: a plain Chromium is running but exposes no
    # CDP (no --remote-debugging-port, or it forwarded the flag to an existing
    # default-profile instance). Fine for WATCHING, useless for connectOverCDP.
    if pgrep -f 'snap/chromium|snap/bin/chromium' >/dev/null 2>&1; then
      warn "a non-debug Chromium IS running (no --remote-debugging-port) — OK to watch, but"
      warn "CDP browser-use needs a debug instance on its own profile. Run:"
      warn "  $0 up --browser"
    fi
  fi
}

# ---- Arg parse -------------------------------------------------------------
VERB="${1:-}"; shift || true
WANT_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --browser)    WANT_BROWSER=1 ;;
    --no-browser) WANT_BROWSER=0 ;;
    *) err "unknown flag: $arg"; exit 2 ;;
  esac
done

rc=0
case "$VERB" in
  up)
    hdr "arena up$([ "$WANT_BROWSER" = 1 ] && echo ' + browser')"
    up_cockpit || rc=1
    [ "$WANT_BROWSER" = 1 ] && { up_browser || rc=1; }
    ;;
  down)
    hdr "arena down$([ "$WANT_BROWSER" = 1 ] && echo ' + browser')"
    down_cockpit || rc=1
    [ "$WANT_BROWSER" = 1 ] && { down_browser || rc=1; }
    ;;
  restart)
    hdr "arena restart$([ "$WANT_BROWSER" = 1 ] && echo ' + browser')"
    down_cockpit || rc=1
    [ "$WANT_BROWSER" = 1 ] && { down_browser || rc=1; }
    up_cockpit || rc=1
    [ "$WANT_BROWSER" = 1 ] && { up_browser || rc=1; }
    ;;
  status)
    do_status
    ;;
  ''|-h|--help|help)
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    err "unknown verb: $VERB (want: up | down | restart | status)"; exit 2 ;;
esac

[ "$VERB" != status ] && do_status
exit $rc
