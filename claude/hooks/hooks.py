#!/usr/bin/env python3
"""The workspace plugin's hooks: one stdlib script for every event it answers.

    hooks.py session-start   SessionStart: the backlog, graded in one line of context
                             (and the ledgers' own history, one local commit)
    hooks.py edit            PostToolUse (async): note a file the turn changed
    hooks.py stop            Stop: after a turn that changed repo files, one critique pass

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
import subprocess
import sys
import tempfile
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


def _marker(session_id: str) -> Path:
    """The file that lists one session's changes until its Stop reads them."""
    session = re.sub(r"[^a-zA-Z0-9_-]", "", session_id or "") or "nosession"
    folder = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or tempfile.gettempdir()) / "critique"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{session}.txt"


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
def _delta(workspace: Path, rel: str) -> str:
    """*rel* with its change against its repo's HEAD, as the critique names it."""
    path = workspace / rel
    git = ["git", "-C", str(path.parent)]
    try:
        stat = subprocess.run(git + ["diff", "--numstat", "HEAD", "--", str(path)], capture_output=True, text=True).stdout
        found = re.match(r"(\d+)\s+(\d+)", stat)
        if found:
            return f"{rel} (+{found.group(1)} -{found.group(2)})"
        tracked = subprocess.run(git + ["ls-files", "--", str(path)], capture_output=True, text=True).stdout
        if tracked.strip():
            return f"{rel} (committed)"
        # Untracked, ignored, or in no repo at all: a file the turn made.
        with open(path, encoding="utf-8", errors="replace") as f:
            return f"{rel} (new, {sum(1 for _ in f)} lines)"
    except OSError:
        return rel


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


def stop(data: dict) -> None:
    """After a turn that changed repo files, ask for one critique pass that names
    them and the affected-tests command to verify with (never a full suite here:
    CODE_STANDARD section 9). Nothing when the turn is already that pass, changed
    nothing, changed only ``.claude/`` or files outside the project, or is waiting
    on background work (its marker is kept for the turn that finishes it)."""
    marker = _marker(str(data.get("session_id") or ""))
    if data.get("stop_hook_active"):
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
    target = " ".join(shown) + (f" (+{more} more)" if more > 0 else "") if shown else "<the files you changed>"
    listed = (
        ", ".join(_delta(workspace, rel) for rel in shown) + (f" and {more} more" if more > 0 else "")
        if shown
        else "files through the shell"
    )
    shell_note = " plus any file you changed through the shell" if shell else ""
    _emit(
        "Stop",
        f"This turn changed {listed}. Check them for bugs, verify with python m3trik/scripts/affected_tests.py "
        f"{target}{shell_note} --run (never a full suite here), then delete what they made unneeded. Fix what "
        "you find now (CLAUDE.md, Findings); one line if nothing needs changing.",
    )


EVENTS = {"session-start": session_start, "edit": edit, "stop": stop}

if __name__ == "__main__":
    handler = EVENTS.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if handler is None:
        sys.exit(f"usage: hooks.py {{{'|'.join(EVENTS)}}}")
    try:
        handler(_input())
    except Exception as exc:  # a hook must never break the session it serves
        sys.stderr.write(f"plugin hook {sys.argv[1]}: {type(exc).__name__}: {exc}\n")
