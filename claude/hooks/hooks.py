#!/usr/bin/env python3
"""The workspace plugin's hooks: one stdlib script for every event it answers.

    hooks.py session-start   SessionStart: the backlog, graded in one line of context
                             (and the ledgers' own history, one local commit)
    hooks.py edit            PostToolUse (async): note a file the turn changed
    hooks.py stop            Stop: after a turn that changed repo files, the gates a machine
                             can run (lint, the affected tests), then one critique pass for
                             what is left; nothing at all after a turn that changed only docs

Stop decides in three steps, cheapest first. A turn that changed only documents asks
nothing (the docs check is their gate). Otherwise it lints the changed Python files for
what is broken at any age and runs the affected tests itself, inside ``--budget``
seconds, so a passing run costs the model nothing and a failing one arrives with its
output. Only then does it ask for the critique, saying what the gates already settled.
Every decision is one line in ``log.jsonl`` beside the markers (files, lines, verdict,
seconds, and whether the critique that followed changed anything): the record the
thresholds of a proportional review are to be set from. A hook that outlasts its
entry's timeout has its output discarded, so the budget ends first; an entry loaded
before ``--budget`` existed gets ``BUDGET``, which fits its old 15 seconds.

``hooks.json`` runs it with no shell (``uv run --no-project python -I hooks.py
<event>``), so one entry works on Windows, macOS and Linux; Claude Code hands
each event's input as JSON on stdin. It imports nothing outside the standard
library, so it runs before, and without, any package of the workspace.

Why a marker at all: no field of the Stop input names the files a turn changed,
and the transcript's format is undocumented (and may lag), so the edit event
notes each change as it happens. It runs ``async``: no tool call waits on it, and
the model's closing message gives it seconds to land before Stop reads it.

The scripts' paths come from ``CLAUDE_PROJECT_DIR`` (the project), never from
this file's location (a plugin lives outside the project), and the marker lives
in ``CLAUDE_PLUGIN_DATA``, the plugin's own data folder (a temp folder without it).
"""

import datetime
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

#: A backlog entry's heading: ``## 2026-01-15 | mayatk | S2 | ready | title``.
HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) \|")
#: ``- Verified: 2026-01-20 | reproduces ...``: a measurement stamp.
VERIFIED = re.compile(r"^- Verified: (\d{4}-\d{2}-\d{2}) \| ([a-z]+)")
BLOCKERS = ("ready", "decision", "scope", "blocked")
#: The verdicts that MEASURE an entry; a "by reading" stamp keeps nothing alive.
MEASURED = ("reproduces", "partial", "stale", "refuted")
#: An entry older than this since its last measurement is expired.
TTL_DAYS = 14
#: A shell command that writes files: POSIX and PowerShell writing verbs, stdout
#: redirected to a real path (not 2>, >&, >=, -> or /dev/null), stdin-fed
#: interpreters, in-script writes. It errs toward marking: a false positive
#: costs one "nothing to change" line, a false negative silences the review.
SHELL_WRITE = re.compile(
    r"\bsed\s+(-[a-z]*i|--in-place)|\bperl\s+-[a-z]*i|\btee\b|"
    r"\b(cp|mv|rm|mkdir|touch|patch|truncate|install)\b|"
    r"\bgit\s+(apply|checkout|reset|stash|mv|rm|restore|clean|commit)\b|"
    r"(^|[^2&<>=-])>{1,2}(?![=&>])\s*(?!/dev/null\b|NUL\b)\S|"
    r"\bpython[0-9.]*\s+-\s|write_text\(|write_bytes\(|\.write\(|open\([^)]*[\"'][wax]|"
    r"\b(Set-Content|Add-Content|Clear-Content|Out-File|New-Item|Copy-Item|Move-Item|"
    r"Remove-Item|Rename-Item)\b|\[(System\.)?IO\.File\]::Write",
    re.IGNORECASE | re.DOTALL,
)
#: What a marker line holds for a write made through the shell (its paths are unknown).
SHELL = "(shell)"
#: The most files the critique names; the rest are counted.
SHOWN = 15
#: Files a model has no bugs to look for in: the docs check is their gate.
DOCS = (".md", ".rst", ".txt")
#: What the lint gate looks for: a file that no longer parses, a comparison or statement
#: that cannot mean what it says, a name nothing defines. Broken whatever the file's age,
#: so a legacy file's style findings never reach the ask.
LINT_RULES = "E9,F63,F7,F82"
#: The most lint findings the ask carries.
LINT_SHOWN = 10
#: The last lines of a failing test run the ask carries.
TAIL = 30
#: Seconds the gates may take when the entry names no ``--budget``.
BUDGET = 8
#: The runners whose tests are plain Python: the only ones the hook starts. Any
#: other selected runner (a headless Maya, Blender, Unity, dotnet, one nobody listed
#: here) is handed back: the hook never starts an application.
PLAIN_RUNNERS = ("m3trik", "pythontk", "uitk", "extapps", "tentacle")
#: The most tests the hook runs itself: a larger selection is handed back, never
#: started and then stopped at the budget.
TEST_CAP = 300
#: A row of the selector's plan: ``<runner>: N module(s), ~M test(s)`` (M kept), or
#: ``<runner>: <label>, run whole`` (no count: a whole suite, never plain).
PLAN_ROW = re.compile(r"^([A-Za-z0-9_.\-]+): (?:\d+ module\(s\), ~(\d+) test\(s\)|.*\brun whole\b)", re.MULTILINE)
#: Seconds the plan may take, the tree kill may take, and naming the changes may take.
PLAN_WAIT = 20
#: Seconds a run started by the hook may take: what is slower is stopped and handed
#: back, so a turn never waits the whole budget on tests the model then runs anyway.
RUN_WAIT = 20
KILL_WAIT = 5
LABEL_WAIT = 4


def _input() -> dict:
    """The event's JSON input, or ``{}`` when it is not JSON."""
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        return {}


def _emit(event: str, context: str) -> None:
    """Hand *context* to the model as this event's additional context."""
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    sys.stdout.write(json.dumps(out))


def _project() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _data() -> Path:
    """The folder the markers and the decision log live in."""
    folder = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or tempfile.gettempdir()) / "critique"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _marker(session_id: str) -> Path:
    """The file that lists one session's changes until its Stop reads them."""
    session = re.sub(r"[^a-zA-Z0-9_-]", "", session_id or "") or "nosession"
    return _data() / f"{session}.txt"


def _log(entry: dict) -> None:
    """One line per decision: what a later, proportional review sets its thresholds from."""
    entry = dict(entry, at=datetime.datetime.now().isoformat(timespec="seconds"))
    try:
        with open(_data() / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


# -- SessionStart ---------------------------------------------------------------
def _date(text: str):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _checkpoint(folder: Path) -> None:
    """Commit what changed in *folder* since the last session, when it is a git
    repository of its own (``git init`` inside ``.claude/``, a person's choice).
    The ledgers sit in no package's repo, so this is their history: an entry a
    session deleted is found again with ``git log -S``. Local only: nothing is
    pushed, what the folder's ``.gitignore`` names stays out, and a commit that
    cannot be made (another session holds the lock, no git, no git identity)
    is skipped."""
    if not (folder / ".git").exists():
        return
    git = ["git", "-C", str(folder)]
    try:  # three calls, together inside the hook's 15 seconds
        dirty = subprocess.run(git + ["status", "--porcelain"], capture_output=True, text=True, timeout=4)
        if dirty.returncode or not dirty.stdout.strip():
            return
        subprocess.run(git + ["add", "-A"], capture_output=True, timeout=4)
        subprocess.run(git + ["commit", "-q", "-m", "Checkpoint"], capture_output=True, timeout=4)
    except (OSError, subprocess.SubprocessError):
        pass


def session_start(data: dict, today: datetime.date = None) -> None:
    """The backlog's line (:func:`_grade`), then the ledgers' history where the
    folder keeps one (:func:`_checkpoint`): the line is written out before git
    is asked anything, so a slow or stuck commit never costs the session it."""
    try:
        _grade(today or datetime.date.today())
    finally:
        sys.stdout.flush()
        _checkpoint(_project() / ".claude")


def _grade(today: datetime.date) -> None:
    """One line on ``.claude/BACKLOG.md``: how many entries are open, how many are
    S1 and actionable, wait on a decision, have expired (no measurement in
    ``TTL_DAYS``) or carry a malformed heading; nothing when it has none."""
    backlog = _project() / ".claude" / "BACKLOG.md"
    try:
        lines = backlog.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    entries = [(n, line) for n, line in enumerate(lines, 1) if HEADING.match(line)]
    if not entries:
        return
    s1 = s1_ready = decisions = 0
    malformed = []
    for number, line in entries:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5 or not re.fullmatch(r"S[123]", parts[2]) or parts[3] not in BLOCKERS:
            malformed.append(number)
            continue
        if parts[2] == "S1":
            s1 += 1
            s1_ready += parts[3] == "ready"
        decisions += parts[3] == "decision"

    # One body pass: verification coverage (an entry is a lead, not a spec) and
    # the TTL (a measured stamp's date resets the clock; a dated note does not).
    verified = total = expired = 0
    entry = None  # [severity, measured, latest measurement]

    def close(item) -> None:
        nonlocal verified, expired
        if item is None:
            return
        if item[1] and item[0] in ("S1", "S2"):
            verified += 1
        if item[2] is not None and (today - item[2]).days > TTL_DAYS:
            expired += 1

    for line in lines:
        head = HEADING.match(line)
        if head:
            close(entry)
            parts = line.split("|")
            severity = parts[2].strip() if len(parts) >= 3 else ""
            total += severity in ("S1", "S2")
            entry = [severity, False, _date(head.group(1))]
        elif entry is not None:
            stamp = VERIFIED.match(line)
            if stamp and stamp.group(2) in MEASURED:
                entry[1] = True
                when = _date(stamp.group(1))
                if when and (entry[2] is None or when > entry[2]):
                    entry[2] = when
    close(entry)

    notes = [f"{len(entries)} deferred issue(s) are open in .claude/BACKLOG.md."]
    if s1:
        notes.append(f"{s1} {'is' if s1 == 1 else 'are'} S1, {s1_ready} of those actionable now (blocker=ready).")
    if decisions:
        notes.append(f"{decisions} wait on a maintainer decision - /m3trik:backlog decide batches them to the user.")
    if expired:
        notes.append(
            f"{expired} entr{'y is' if expired == 1 else 'ies are'} past the {TTL_DAYS}-day TTL "
            "(no measurement in 14 days; notes do not count) - /m3trik:backlog archives them at SELECT."
        )
    notes.append(
        "Slice it with: grep '^## 20' .claude/BACKLOG.md | grep '| S1 |'. "
        "FIX-NOW BAR: mechanical/S3 findings get fixed in the turn that finds them, never logged. "
        "If this session touches an affected package, re-measure a relevant entry before acting on it "
        "(entries are leads, not specs) and delete any entry your work resolves. Reviewed-but-not-committed "
        "items live in .claude/FUTURE.md; purged/expired history in .claude/BACKLOG.archive.md (grep it, "
        "never load it). Work it with the /m3trik:backlog skill."
    )
    if total and verified < total:
        notes.append(
            f"{verified}/{total} S1+S2 entries carry a measured Verified stamp - the rest are unmeasured "
            "leads; /m3trik:backlog verify batch-stamps the top of the queue."
        )
    if malformed:
        notes.append(
            f"WARNING {len(malformed)} heading(s) have a missing or unknown severity/blocker field "
            f"(line(s) {', '.join(map(str, malformed))}) - re-stamp them per the file header "
            "(blockers: ready|decision|scope|blocked)."
        )
    _emit("SessionStart", " ".join(notes))


# -- PostToolUse ----------------------------------------------------------------
def edit(data: dict) -> None:
    """Note what this tool call changed: a file tool's path, or ``(shell)`` for a
    shell command that looks like a write (auto mode edits through the shell)."""
    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") in ("Bash", "PowerShell"):
        if not SHELL_WRITE.search(str(tool_input.get("command") or "")):
            return
        entry = SHELL
    else:
        entry = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if not entry:
            return
    with open(_marker(str(data.get("session_id") or "")), "a", encoding="utf-8") as f:
        f.write(entry + "\n")


# -- Stop -----------------------------------------------------------------------
def _change(workspace: Path, rel: str, deadline: float = None) -> tuple:
    """*rel* with its change against its repo's HEAD, as the critique names it, and
    the number of lines that changed; past *deadline*, *rel* alone and no git call."""
    if deadline is not None and time.monotonic() > deadline:
        return rel, 0
    path = workspace / rel
    git = ["git", "-C", str(path.parent)]
    try:
        stat = subprocess.run(git + ["diff", "--numstat", "HEAD", "--", str(path)], capture_output=True, text=True, timeout=4).stdout
        found = re.match(r"(\d+)\s+(\d+)", stat)
        if found:
            return f"{rel} (+{found.group(1)} -{found.group(2)})", int(found.group(1)) + int(found.group(2))
        tracked = subprocess.run(git + ["ls-files", "--", str(path)], capture_output=True, text=True, timeout=4).stdout
        if tracked.strip():
            return f"{rel} (committed)", 0
        # Untracked, ignored, or in no repo at all: a file the turn made.
        with open(path, encoding="utf-8", errors="replace") as f:
            count = sum(1 for _ in f)
        return f"{rel} (new, {count} lines)", count
    except (OSError, subprocess.SubprocessError):
        return rel, 0


def _stop(proc) -> None:
    """Stop *proc* and everything it started, never waiting long for either.

    Prior art weighed: pythontk's execution monitor stops a process tree this way (a
    bounded ``taskkill /T``, a guarded ``killpg``); a hook imports nothing of the
    workspace, so the few lines are restated here."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=KILL_WAIT)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # already gone, or the kill itself hung: the hook moves on either way
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _run(command: list, cwd: Path, timeout: float) -> tuple:
    """``(exit code, output)`` of *command*; ``(None, "")`` when it outlasts
    *timeout*, its whole process tree stopped. The output goes to a file and the
    wait is on the process, so a child that outlives the command and still holds
    its output open neither blocks the hook nor turns a finished run into a timeout."""
    own_group = {} if os.name == "nt" else {"start_new_session": True}
    with tempfile.TemporaryFile() as log:
        try:
            proc = subprocess.Popen(
                command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **own_group
            )
        except OSError as exc:
            return 127, str(exc)
        try:
            code = proc.wait(timeout=max(timeout, 0))
        except subprocess.TimeoutExpired:
            _stop(proc)
            return None, ""
        log.seek(0)
        return code, log.read().decode("utf-8", "replace")


def _tool(project: Path, name: str):
    """The workspace's own *name* (its virtual environment's), or ``None``."""
    for rel in (f".venv/Scripts/{name}.exe", f".venv/bin/{name}"):
        if (project / rel).is_file():
            return str(project / rel)
    return None


def _lint(project: Path, files: list, timeout: float, run=_run) -> list:
    """What the linter calls broken in the Python files of *files*, at most
    ``LINT_SHOWN`` lines; nothing where the workspace has no linter."""
    ruff = _tool(project, "ruff")
    targets = [rel for rel in files if rel.endswith(".py") and (project / rel).is_file()]
    if not ruff or not targets or timeout <= 0:
        return []
    code, out = run([ruff, "check", "--quiet", "--output-format", "concise", "--select", LINT_RULES, *targets], project, timeout)
    if code != 1:  # 0 is clean; anything else is the linter failing, never a finding
        return []
    return [line for line in out.splitlines() if line.strip()][:LINT_SHOWN]


def _tests(project: Path, files: list, timeout: float, run=_run) -> tuple:
    """Run the tests *files* reach, when a machine may: ``(verdict, detail)``.

    It plans first, and starts a run only when every selected runner is plain Python
    (``PLAIN_RUNNERS``) and the selection is small (``TEST_CAP``): the hook never
    starts an application, and never starts a run it would have to stop. ``passed``
    and ``failed`` are judged here. Handed back to the model: ``skipped`` (no
    selector, or only shell writes), ``none`` (no test selected), ``host`` (a runner
    that needs an application, or one not known to be plain), ``large``, ``idle``
    (every selected test skipped), ``timeout``, ``error``, and ``partial`` (a pass
    beside shell writes, set by the caller)."""
    script = project / "m3trik" / "scripts" / "affected_tests.py"
    if not files or not script.is_file():
        return "skipped", ""
    started = time.monotonic()
    left = lambda: timeout - (time.monotonic() - started)  # noqa: E731
    if left() < 3:
        return "timeout", ""
    select = [_tool(project, "python") or sys.executable, str(script), *files]
    code, plan = run(select + ["--no-gui"], project, min(left(), PLAN_WAIT))
    if code is None:
        return "timeout", ""
    if code != 0:
        return "error", ""
    rows = PLAN_ROW.findall(plan)
    if not rows:
        return "none", ""
    if any(name not in PLAIN_RUNNERS or not count for name, count in rows):
        return "host", ""
    if sum(int(count) for _, count in rows) > TEST_CAP:
        return "large", ""
    if left() < 3:
        return "timeout", ""
    code, out = run(select + ["--run", "--no-gui"], project, min(left(), RUN_WAIT))
    if code is None:
        return "timeout", ""
    lines = out.splitlines()
    summary = next((line for line in reversed(lines) if line.startswith("=== affected tests:")), "")
    if code == 0:
        return ("passed" if "all passed" in summary else "none"), ""
    if "FAILED" in summary:
        return "failed", "\n".join(lines[-TAIL:])
    return ("idle" if "RAN NOTHING" in summary else "error"), ""


def _ask(listed: str, target: str, shell_note: str, tests: str, detail: str, lint: list) -> str:
    """The one message a turn's changes earn, by what the gates already settled."""
    head = f"This turn changed {listed}."
    if lint:
        head += " The linter calls this broken:\n" + "\n".join("  " + line for line in lint) + "\n"
    rerun = f"python m3trik/scripts/affected_tests.py {target}{shell_note} --run"
    if tests == "passed":
        return (
            f"{head} The hook ran their affected tests and they passed; do not rerun them. Check the change for "
            "bugs the tests do not cover, then delete what it made unneeded. Fix what you find now (CLAUDE.md, "
            "Findings); one line if nothing needs changing."
        )
    if tests == "failed":
        return (
            f"{head} Their affected tests FAILED when the hook ran them:\n{detail}\nFix the cause (never a "
            f"retry), verify with {rerun} (never a full suite here), then delete what the change made unneeded."
        )
    return (
        f"{head} Check them for bugs, verify with {rerun} (never a full suite here), then delete what they made "
        "unneeded. Fix what you find now (CLAUDE.md, Findings); one line if nothing needs changing."
    )


def _inside(path: str, root: Path):
    """*path* relative to *root* (``/``-separated), or ``None`` outside it: the
    path as the model spelled it (``C:/x``, ``c:\\x``) compared normalized, a
    sibling folder sharing the root's prefix (``<root>_old``) is outside."""
    full, base = os.path.abspath(path), os.path.abspath(str(root))
    try:
        if os.path.commonpath([os.path.normcase(full), os.path.normcase(base)]) != os.path.normcase(base):
            return None
    except ValueError:  # another drive
        return None
    rel = os.path.relpath(full, base).replace("\\", "/")
    return None if rel == "." else rel


def _budget(argv: list) -> int:
    """Seconds the gates may take: the entry's ``--budget N``, else ``BUDGET``."""
    try:
        return max(0, int(argv[argv.index("--budget") + 1]))
    except (ValueError, IndexError):
        return BUDGET


def stop(data: dict) -> None:
    """After a turn that changed repo files: lint them, run their affected tests
    (never a full suite here: CODE_STANDARD section 9), then ask for one critique
    pass that names them and says what the gates settled. Nothing when the turn is
    already that pass, changed nothing, changed only documents, ``.claude/`` or
    files outside the project, or is waiting on background work (its marker is kept
    for the turn that finishes it: a gate run then would judge work in progress)."""
    started = time.monotonic()
    session = str(data.get("session_id") or "")
    marker = _marker(session)
    if data.get("stop_hook_active"):
        # The critique pass ends here; whether it changed a file is what tells a
        # critique that found something from one that cost a turn for nothing.
        _log({"event": "critique", "session": session, "changed": marker.is_file()})
        marker.unlink(missing_ok=True)
        return
    if data.get("background_tasks") or not marker.is_file():
        return
    lines = marker.read_text(encoding="utf-8").splitlines()
    marker.unlink(missing_ok=True)

    workspace = _project()
    files = []
    for line in lines:
        rel = None if not line or line == SHELL else _inside(line, workspace)
        if rel and not rel.startswith(".claude/") and rel not in files:
            files.append(rel)
    shell = SHELL in lines
    if not files and not shell:
        return

    shown, more = files[:SHOWN], len(files) - SHOWN
    changes = [_change(workspace, rel, started + LABEL_WAIT) for rel in shown]
    code = [rel for rel in files if not rel.lower().endswith(DOCS)]
    record = {
        "event": "stop", "session": session, "code": len(code), "docs": len(files) - len(code),
        "shell": shell, "lines": sum(count for _, count in changes),
    }
    if not code and not shell:
        _log(dict(record, asked=False, tests="docs", lint=0, seconds=round(time.monotonic() - started, 1)))
        return

    budget = _budget(sys.argv)
    left = lambda: budget - (time.monotonic() - started)  # noqa: E731
    lint = _lint(workspace, code, min(left() - 1, 10))
    tests, detail = _tests(workspace, files, left() - 2)
    if shell and tests == "passed":
        tests = "partial"  # the shell changed files nobody can name: a pass vouches for the named ones only

    target = " ".join(shown) + (f" (+{more} more)" if more > 0 else "") if shown else "<the files you changed>"
    listed = (
        ", ".join(label for label, _ in changes) + (f" and {more} more" if more > 0 else "")
        if shown
        else "files through the shell"
    )
    shell_note = " plus any file you changed through the shell" if shell else ""
    _emit("Stop", _ask(listed, target, shell_note, tests, detail, lint))
    _log(dict(record, asked=True, tests=tests, lint=len(lint), seconds=round(time.monotonic() - started, 1)))


EVENTS = {"session-start": session_start, "edit": edit, "stop": stop}

if __name__ == "__main__":
    handler = EVENTS.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if handler is None:
        sys.exit(f"usage: hooks.py {{{'|'.join(EVENTS)}}}")
    try:
        handler(_input())
    except Exception as exc:  # a hook must never break the session it serves
        sys.stderr.write(f"plugin hook {sys.argv[1]}: {type(exc).__name__}: {exc}\n")
