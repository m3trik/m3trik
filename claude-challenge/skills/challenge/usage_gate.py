#!/usr/bin/env python3
# coding=utf-8
"""The usage gate: no work starts that the account's usage windows cannot finish.

A Claude subscription meters use in windows (five hours, a week), and ``claude -p /usage``
reports how much of each is used and when it resets, free of charge. :class:`UsageGate` reads
that before work is started and refuses work whose estimate does not fit what is left, less a
reserve kept back for the person's own work, saying when the window resets. The reserve shrinks as
the reset nears (nothing left in a window outlives its reset, so an hour before it there is nothing
to keep back), and ``python usage_gate.py`` prints each window, the model it belongs to, its hours
to its reset and what is spendable now. A window ``/usage`` lists for one model alone holds only
work on that model. It learns what a dollar of agents costs each window by reading the windows
before and after each run.

Two users: the challenge runner (``challenge.py``) asks before each stage, and the plugin's
``PreToolUse`` hook asks before any tool call that launches paid agents in any session: a
subagent (``Agent``, ``Task``), a workflow (``Workflow``), or a shell command starting a headless
``claude -p`` session or a challenge run.

    python usage_gate.py --hook     # the hook: the event on stdin; exit 2 blocks, its message on stderr
    python usage_gate.py            # print the windows as read now

It never blocks what it cannot measure: no reading (an API key account, no ``claude`` command, a
timeout) lets the call through. ``CLAUDE_USAGE_GATE=off`` switches it off.

Prior art weighed: Claude Code's own limit message arrives only once a window is full, after the
work has started; ``--max-budget-usd`` caps one session's dollars but knows nothing of the
windows. Standard library only, so the hook runs in any Python.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

#: What one launched agent is assumed to need when nothing better is known: a reviewer on a senior
#: model, as measured on the challenge's runs (about 56k tokens read, 16k written).
AGENT_TOKENS = 72000
#: The tools that launch paid agents themselves.
AGENT_TOOLS = ("Agent", "Task", "Workflow")
#: Where a shell command starts: a line's start, or after a separator, a group, a substitution or
#: a keyword that runs what follows (a loop's ``do``, a branch's ``then``, ``else``); past any
#: environment assignments and the wrappers that run the rest as a command. A word inside an
#: argument (``git commit -m "claude -p"``, ``grep "claude -p"``) is no command.
_AT_COMMAND = (r"""(?:^|[;&|({`]|\$\()\s*(?:(?:do|then|else|elif)\s+)*(?:[A-Za-z_]\w*=\S*\s+)*"""
               r"""(?:(?:env|nohup|time|exec|start|timeout(?:\s+-\S+)*\s+\S+|cmd(?:\.exe)?\s+/[ck])\s+)*""")
#: The ``claude`` binary, bare or by a path (quoted where it holds a space), or its Windows shims.
_CLAUDE = r"""(?:"[^"\n]*[/\\]|'[^'\n]*[/\\]|[^\s"';&|()`]*[/\\])?claude(?:\.exe|\.cmd|\.ps1)?["']?"""
#: A shell command that starts a headless session (``rest``: what follows its ``-p``), or a
#: challenge run that will start many.
LAUNCH = re.compile(_AT_COMMAND + _CLAUDE + r"""\s+(?:[^|;&\n]*?\s)?(?:-p|--print)\b(?P<rest>[^|;&\n]*)"""
                    r"""|(?<![\w-])challenge\.py\b[^\n]*--mode[\s=]+["']?(?:run|frame)\b""", re.I | re.M)
#: A command handed whole to another shell (``bash -c "..."``, ``cmd /c "..."``,
#: ``powershell -Command "..."``): its ``inner`` text is a command line of its own.
NESTED = re.compile(_AT_COMMAND + r"""(?:(?:ba|z|da|k)?sh|cmd|pwsh|powershell)(?:\.exe)?(?:\s+[-/]\w+)*?"""
                    r"""\s+(?:-[a-z]*c|-command|/c|/k)\s+(?P<q>["'])(?P<inner>.*?)(?P=q)""", re.I | re.M)
#: What follows ``-p`` in a session that only reads the windows: never gated, so the reading
#: itself always works.
READS_USAGE = re.compile(r"""\s+["']?/usage["']?(?:\s|$)""")
#: A model a shell command names for the sessions it starts.
MODEL_ARG = re.compile(r"""--model[\s=]+["']?([\w.\[\]-]+)""", re.I)


def home():
    """Where the gate keeps its calibration and its last reading (the user's cache folder)."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "claude-challenge"


def read_usage(exe=None, cwd=None, timeout=20):
    """The account's usage windows as ``claude -p /usage`` reports them (free: no model is called),
    ``{window: {"pct", "resets"}}``, or None where it reports none or cannot be run. It runs in
    *cwd*, else the gate's own folder (:func:`home`), never a shared one whose project settings
    another user could plant; *timeout* stays under the hook's own limit (``hooks.json``)."""
    exe = exe or shutil.which("claude")
    if not exe:
        return None
    try:
        if not cwd:
            cwd = home()
            cwd.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([exe, "-p", "/usage", "--output-format", "json", "--strict-mcp-config",
                               "--no-session-persistence", "--tools", ""], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cwd),
                              timeout=timeout)
        return UsageGate.parse(str(json.loads(done.stdout).get("result") or ""))
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def cached(read, path=None, ttl=90):
    """*read*, its answer reused for *ttl* seconds (kept in *path*), so a burst of launches reads once."""
    path = Path(path) if path else home() / "usage_cache.json"

    def reading():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(data.get("at", 0)) < ttl:
                return data.get("usage")
        except (OSError, ValueError):
            pass
        usage = read()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"at": time.time(), "usage": usage}), encoding="utf-8")
        except OSError:
            pass
        return usage

    return reading


class UsageGate:
    """Keeps work inside the account's usage windows: :meth:`check` says why work of about so many
    tokens must not start now, or None when it fits what is left of every window it runs in less
    :attr:`RESERVE`. What a dollar costs each window, and what a token costs, it learns from each run
    (:meth:`begin`, :meth:`end`, kept in *path*); until then it stops only a window already within the
    reserve of full.

    A window is keyed by its span (``session``, ``week``), and a window ``/usage`` lists for one model
    alone by its span and that model (``week:sonnet``): work runs in the all-models windows and in
    those of the models it runs on, never in another model's.

    Parameters:
        read: Returns ``{window: {"pct", "resets"}}`` now (:func:`read_usage`), or None.
        path: The calibration file (default: the user's cache folder).
        clock: Returns the time now (default: the machine's local time).
    """

    RESERVE = 5.0  # percent of a window kept back for the person's own work, in full far from its reset
    #: Hours before a window's reset from which its reserve shrinks, to nothing at the reset.
    RESERVE_HOURS = {"session": 1.0, "week": 24.0}
    NAMES = {"session": "5-hour", "week": "weekly"}
    RESETS = re.compile(r"(?:(?P<mon>[A-Za-z]{3})[a-z]*\s+(?P<day>\d{1,2}),?\s*)?(?:at\s+)?"
                        r"(?:(?P<hour>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>am|pm))?", re.I)
    MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                          "nov", "dec"), 1)}
    #: One window's line: its span, what its parentheses say (``all models``, ``Sonnet only``), its use, its reset.
    LINE = re.compile(r"Current (session|week)\s*(?:\(([^)\n]*)\))?[^:\n]*:\s*(\d+(?:\.\d+)?)% used\W+resets\s+([^\n]+)",
                      re.I)
    #: Words of a window's parentheses that name no model.
    NOT_MODELS = {"all", "models", "model", "only", "claude"}

    def __init__(self, read, path=None, clock=None):
        self.read = read
        self.clock = clock or datetime.now
        self.path = Path(path) if path else home() / "calibration.json"
        try:
            self.cal = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        except ValueError:
            self.cal = {}
        self.start = None

    @classmethod
    def parse(cls, text):
        """The windows ``/usage``'s *text* lists, ``{window: {"pct", "resets"}}`` keyed as the class says
        (``week:sonnet`` for a model's own line), or None where it lists none."""
        found = {}
        for m in cls.LINE.finditer(text):
            words = re.findall(r"[\w.-]+", (m.group(2) or "").lower())
            model = None if "all" in words else next((w for w in words if w not in cls.NOT_MODELS), None)
            window, pct = m.group(1).lower() + (":%s" % model if model else ""), float(m.group(3))
            if window not in found or pct > found[window]["pct"]:  # a window listed twice counts its fuller line
                found[window] = {"pct": pct, "resets": m.group(4).strip()}
        return found or None

    @staticmethod
    def zone(name):
        """The time zone *name* names (``America/New_York``), or None where this machine cannot read it:
        Windows has no zone database without the ``tzdata`` package."""
        try:
            return ZoneInfo(name)
        except (KeyError, ValueError, OSError):  # ZoneInfoNotFoundError is a KeyError
            return None

    @classmethod
    def hours_left(cls, resets, now):
        """Hours from *now* to *resets* as ``/usage`` words it (``Nov 21, 2am (America/New_York)``,
        ``Nov 21 at 2am``, ``5:20pm``): in the zone it names where this machine can read it (:meth:`zone`),
        else in the machine's local time. None for words it does not read whole (an unknown month, a day
        the month lacks), which keeps a window's whole reserve."""
        named = re.search(r"\(([^()]*)\)", resets or "")
        found = cls.RESETS.fullmatch(re.sub(r"\(.*?\)", "", resets or "").strip())
        if not found or not (found.group("hour") or found.group("day")):
            return None
        month = cls.MONTHS.get(found.group("mon").lower()[:3]) if found.group("day") else now.month
        if not month:
            return None
        zone = cls.zone(named.group(1).strip()) if named else None
        if zone:
            now = now.astimezone(zone)  # a naive clock is the machine's local time
        hour = int(found.group("hour") or 0) % 12 + (12 if (found.group("ampm") or "").lower() == "pm" else 0)
        try:
            when = now.replace(hour=hour, minute=int(found.group("min") or 0), second=0, microsecond=0)
            if found.group("day"):
                when = when.replace(month=month, day=int(found.group("day")))
                if when < now - timedelta(days=1):
                    when = when.replace(year=now.year + 1)
            elif when < now:
                when += timedelta(days=1)
        except ValueError:  # Feb 30, or Feb 29 in a year without one
            return None
        if when.tzinfo:  # across a change of the clocks: by the instants, not the wall times
            when, now = when.astimezone(timezone.utc), now.astimezone(timezone.utc)
        return max(0.0, (when - now).total_seconds() / 3600.0)

    def reserve(self, window, resets):
        """The percent of *window* kept back now: :attr:`RESERVE`, shrinking over the last
        :attr:`RESERVE_HOURS` before its reset to nothing (all of it, where the reset can't be read)."""
        hours = self.hours_left(resets, self.clock())
        span = self.RESERVE_HOURS.get(window.partition(":")[0])
        if hours is None or not span:
            return self.RESERVE
        return self.RESERVE * min(1.0, hours / span)

    def budget(self):
        """Each window as read now, with the ``model`` it belongs to (``all``, or one model's name), its
        ``hours_left`` to the reset, its ``reserve`` and the percent ``spendable`` now; None without a reading."""
        now = self.read()
        if not now:
            return None
        out = {}
        for window, v in now.items():
            hours = self.hours_left(v.get("resets"), self.clock())
            reserve = self.reserve(window, v.get("resets"))
            out[window] = dict(v, model=window.partition(":")[2] or "all",
                               hours_left=None if hours is None else round(hours, 2), reserve=round(reserve, 2),
                               spendable=round(max(0.0, 100.0 - v["pct"] - reserve), 2))
        return out

    def check(self, need_tokens, models=()):
        """Why work of about *need_tokens* on *models* (names or ids: ``sonnet``, ``claude-opus-5-5``) must
        not start now, or None when it fits. It is held to the all-models windows and to each window of
        a model it names; with none named (a session's own model, which no event says), to the
        all-models windows alone."""
        now = self.read()
        if not now:
            return None
        usd = need_tokens * self.cal.get("usd_per_token", 1.05e-5)
        runs_on = [str(m).lower() for m in models or () if m]
        for window, v in now.items():
            span, _, model = window.partition(":")
            if model and not any(model in m for m in runs_on):
                continue  # another model's allocation: no constraint on this work
            reserve = self.reserve(window, v.get("resets"))
            left = 100.0 - v["pct"] - reserve
            rate = (self.cal.get("pct_per_usd") or {}).get(window)
            need = usd * rate if rate else 0.0
            name = " ".join(filter(None, (self.NAMES.get(span, span), model)))
            if left <= 0:
                return ("the %s window is %.0f%% used, inside the %g%% kept back for the person's own work; "
                        "it resets %s" % (name, v["pct"], round(reserve, 1), v["resets"]))
            if need > left:
                return ("the %s window is %.0f%% used and this needs about %.0f%% of it, so it would fail part "
                        "way; it resets %s" % (name, v["pct"], need, v["resets"]))
        return None

    def begin(self):
        self.start = self.read()

    def end(self, usd, tokens):
        """Learn from the run just made: each window's rise per dollar, and the dollars per token."""
        now = self.read()
        if not (self.start and now and usd > 0):
            return
        rates = self.cal.setdefault("pct_per_usd", {})
        for window, v in now.items():
            rise = v["pct"] - self.start.get(window, {}).get("pct", v["pct"])
            if rise > 0:
                rate = rise / usd
                rates[window] = rate if window not in rates else (rates[window] + rate) / 2
        if tokens:
            rate = usd / tokens
            self.cal["usd_per_token"] = rate if "usd_per_token" not in self.cal else (self.cal["usd_per_token"] + rate) / 2
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cal, indent=1), encoding="utf-8")


def launches(command):
    """Whether shell *command* starts a headless session (one that only reads the windows aside) or a
    challenge run, in a command it hands another shell too."""
    if any(m.group("rest") is None or not READS_USAGE.match(m.group("rest")) for m in LAUNCH.finditer(command)):
        return True
    return any(launches(m.group("inner")) for m in NESTED.finditer(command))


def need_of(event):
    """The tokens a tool call would launch agents for, or None when it launches none."""
    tool = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}
    if tool in AGENT_TOOLS:
        return AGENT_TOKENS
    if tool in ("Bash", "PowerShell") and launches(str(tool_input.get("command") or "")):
        return AGENT_TOKENS
    return None


def models_of(event):
    """The models a launching tool call names: a subagent's ``model``, a shell command's ``--model``.
    None named means the session's own model, which the event does not say."""
    tool_input = event.get("tool_input") or {}
    if (event.get("tool_name") or "") in AGENT_TOOLS:
        return [str(tool_input.get("model"))] if tool_input.get("model") else []
    return MODEL_ARG.findall(str(tool_input.get("command") or ""))


def hook(stdin, gate=None):
    """``(exit code, message)`` for a ``PreToolUse`` event read from *stdin* (UTF-8 bytes, as Claude Code
    writes it, or text): 2 and why, to block a launch the windows cannot take; 0 otherwise, reading
    nothing for a call that launches nothing."""
    raw = stdin.read()
    try:
        event = json.loads(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
    except ValueError:
        return 0, ""
    need = need_of(event) if isinstance(event, dict) else None
    if need is None or os.environ.get("CLAUDE_USAGE_GATE", "").lower() in ("off", "0", "false"):
        return 0, ""
    gate = gate or UsageGate(cached(read_usage))
    why = gate.check(need, models_of(event))
    if not why:
        return 0, ""
    return 2, ("Blocked by the usage gate: %s. Wait for the reset, or set CLAUDE_USAGE_GATE=off to start it "
               "anyway." % why)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--hook" in argv:  # the bytes: under -I a text stream decodes with the code page, not UTF-8
        code, message = hook(getattr(sys.stdin, "buffer", sys.stdin))
        if message:
            print(message, file=sys.stderr)
        return code
    print(json.dumps(UsageGate(read_usage).budget(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
