# Agent instructions and operations — how agents read and act on this codebase

**Nav**: [← m3trik](../AGENTS.md) · [Code standard](CODE_STANDARD.md) · [Context budget](CONTEXT_BUDGET.md) · [The plugin](../claude/README.md)

Three pieces let an agent work in this codebase as it is meant to be worked in:

- **Instructions** (`ptk.AgentInstructions`): the rules an agent reads, kept as a checked tree, so each session reads only what applies and every repo carries what it needs when it is cloned alone.
- **Operations** (`ptk.OperationCatalog`): the codebase's named, typed actions, run from the command line (`python -m pythontk ops`) or over MCP, each with a dry run; one an application runs goes to an instance the tooling owns (a fresh one per command, one kept per session over MCP). An agent runs an operation rather than writing a script.
- **The Claude Code plugin** ([`m3trik/claude/`](../claude/README.md)): Claude Code's machinery: the `reviewer` and `sweep` agents, the `/backlog` skill, the hooks, and the two MCP servers that serve the operations.

Set them up once per machine; every session then has them.

## Set up

From the workspace root (Windows paths shown). On a new machine, clone `m3trik` into an empty folder first: `python m3trik/scripts/setup_workspace.py` prints what that folder lacks (the other repos, the `.venv`, the root's instruction files) and `--apply` makes it, each only where it is missing. That covers step 1; the rest configure your own tools, so they stay yours.

1. **Python.** The workspace `.venv`, Python 3.10 or later (the MCP servers need it; the packages run on 3.9), with every package installed editable. Installing is what registers each package's operations and host runner: entry points are install metadata, so a folder on `PYTHONPATH` alone registers nothing.

   ```powershell
   py -3.11 -m venv .venv
   .venv\Scripts\python -m pip install --config-settings editable_mode=compat -e pythontk -e uitk -e mayatk -e blendertk -e tentacle -e extapps -e unitytk
   ```

   `editable_mode=compat` puts each repo folder itself on `sys.path`, so a package imports from its repo whatever the working directory and with no `PYTHONPATH`, as an MCP client launches a server. The default editable mode loses to a repo folder seen first (the workspace root as the working directory, or on `PYTHONPATH`): the package then imports as an empty namespace and its operations cannot run. One install per package: reinstalling over an older one can leave the old copy in front (`pip uninstall` each until none is left, then install). `operations.check` names a hidden package.

   An operation a host runs needs that host installed: `maya.*` finds Maya through `MAYA_EXE`, `MAYA_LOCATION`, `PATH`, then the newest install; `blender.*` finds Blender through `BLENDER_EXE`, `PATH`, then the usual install folders.
2. **[uv](https://docs.astral.sh/uv/) on `PATH`.** The plugin's MCP servers run `uv run --no-project --with "mcp>=2.3,<3" python -m pythontk ops mcp`: uv finds the workspace `.venv` and adds the MCP SDK for that run alone, so the shared `.venv` never installs it.
3. **The `claude` command.** `claude install` (or Anthropic's installer) puts a self-updating build in `%USERPROFILE%\.local\bin`; add that folder to the user `PATH`, then open a new terminal (VS Code: restart it). The copy inside the VS Code extension sits in a folder named for its version, so it is not one to put on `PATH`.
4. **The plugin, for the workspace:**

   ```powershell
   claude plugin marketplace add <path of the m3trik checkout> --scope project
   claude plugin install m3trik@m3trik --scope project
   ```

   Both write to `.claude/settings.json`. Project scope, not the default user scope: the hooks speak this workspace's tools (the Stop hook names `m3trik/scripts/affected_tests.py`), so they belong to its sessions alone. In an interactive session, `/plugin marketplace add …` and `/plugin install …` do the same and ask for the scope. The marketplace is the local checkout, so an edit to the plugin reaches the next session as it stands.
5. **Permissions.** `ops` changes nothing (searches, reads, plans, views): allow it whole, `"mcp__plugin_m3trik_ops__*"` in `permissions.allow` in `.claude/settings.json`. `ops-apply` makes changes and runs code (`*_exec`: any code, with your rights, in an instance the tooling launched, as a shell command would), so allow it as you allow Bash: whole, `"mcp__plugin_m3trik_ops-apply__*"`, or leave it asking per call. Neither reaches a session a person opened, both talk only over stdio, and every call is in the client's transcript.
6. **Restart** any open session: a session loads its plugins, hooks and MCP servers when it starts.

### Check it

| Run | Expect |
|:---|:---|
| `claude plugin list` | `m3trik@m3trik`, scope project, enabled |
| `claude mcp list` | `plugin:m3trik:ops` and `plugin:m3trik:ops-apply` connected |
| `.venv\Scripts\python -m pythontk ops list` | `instructions.*`, `maya.*` and `blender.*`, no warning lines |
| `python -m pythontk ops run operations.check` | status `done`, no issues (exit code 0) |
| `python m3trik/scripts/sync_workspace.py --check` | every line OK |
| `/agents`, in a session | `m3trik:reviewer` and `m3trik:sweep`, each once |

### Elsewhere

- **A repo cloned alone** carries its own rules and the shared packs: `AGENTS.md`, a `CLAUDE.md` stub, its packs and a SessionStart hook that adds them to a session rooted in it. The hook runs `python` with no shell: a virtual environment provides it, as does `python-is-python3` on Debian and Ubuntu; without it the packs are not added, and `AGENTS.md` still links them. The workspace's rules ([`agents/workspace.md`](../agents/workspace.md), rendered to the root `AGENTS.md`: operations, release, workspace specifics, the backlog) and the links from one repo to another resolve only in the workspace, which `setup_workspace.py` builds around a clone of `m3trik`. For the agents, `/backlog` and the MCP servers there too, add the plugin from that clone (step 4, pointing at a checkout of `m3trik`).
- **Any other project** gets the operations and the whole API of the packages it installs, with no workspace and no plugin (Python 3.10 or later, in the environment that has them):

  ```powershell
  python -m pip install "pythontk[mcp]" mayatk blendertk     # the packages whose tools you want
  claude mcp add ops -- python -m pythontk ops mcp
  claude mcp add ops-apply -- python -m pythontk ops mcp --apply
  ```

  Name that environment's `python` by its full path, so the servers start in it whatever the client's working directory. Permissions as in step 5 (`mcp__ops__*`, `mcp__ops-apply__*`).
- **Another agent** (Copilot, Codex, Cursor) reads `AGENTS.md`, whose pointer block names the packs. For the operations, register the same two commands as stdio MCP servers in its configuration, or call the command line.

### The challenge plugin

A second plugin in this marketplace, [`m3trik/claude-challenge/`](../claude-challenge/skills/challenge/SKILL.md): `/challenge` (`/challenge:challenge` where another skill shares the name) stress-tests a design, plan or proposal with independent agents. Critics attack it from named seats, advocates argue rival designs, scenarios are walked through every design, findings are verified and a judge scores. It has no hooks and names nothing of this workspace, so it installs at user scope and works in every project:

```
claude plugin install challenge@m3trik --scope user
```

The marketplace is declared for this workspace (step 4), so in another project add it at user scope first: `claude plugin marketplace add <path of the m3trik checkout> --scope user`.

Every reviewer is told to use no tools. Where a frame sets `critic_agent`, the reviewers on the critic model run as the [`critic`](../claude-challenge/agents/critic.md) agent, which holds the Read tool alone; reviewers on the session's model keep its tools. The `plan` and `stub` modes spend nothing; a `run` is a workflow and needs the user's opt-in.

## Use

### What a Claude Code session has

| Piece | What it does | Reach for it |
|:---|:---|:---|
| `AGENTS.md` and the packs | the rules: the workspace's, plus a repo's own once the session touches it | always loaded |
| `m3trik:reviewer` | an independent, read-only review of one change, briefed with the diff, never the author's conclusions | each release-sized change (Sonnet first pass, Opus verifies) |
| `m3trik:sweep` | a read-only inventory across the repos (callers of a name, saved names, parity) | a broad search whose conclusion you act on |
| `/m3trik:backlog` | works `.claude/BACKLOG.md`: picks the next entry, re-measures it, critiques its fix, then stops for approval | "what's next on the backlog" |
| SessionStart hook | grades the backlog in one line: open entries, expired ones, those awaiting a decision; commits the ledgers' changes where `.claude/` keeps their history ([below](#keep-the-ledgers-history)) | each session start |
| Stop hook | after a turn that changed files: lints them, plans their affected tests and runs the selection itself when it is small and plain Python, never an application (a pass costs the model nothing, a failure arrives with its output), then asks for one critique pass; nothing after a turn that changed only docs; logs each decision | each turn that edits |
| `ops` / `ops-apply` | the operations as MCP tools: reads and plans on `ops`, changes and code on `ops-apply`, Maya, Blender, Unity and Python calls in this session's own instances; `api_search` / `api_describe` find any function, `*_python_exec` runs code there, `*_scene_view` shows the scene | instead of writing a script |

### Run an operation

```bash
python -m pythontk ops list                                   # every operation
python -m pythontk ops search scene view                      # by words
python -m pythontk ops describe instructions.sync              # its arguments and result
python -m pythontk ops run instructions.sync root=.               # the plan
python -m pythontk ops apply instructions.sync root=.             # the change
```

`run` only plans an operation that changes anything: its outcome's `changes` is the plan. `apply` makes the changes, and a live run saves the scenes it changed. Code has no plan, so a `*.python.exec` is applied only (`run` refuses it). Arguments are `NAME=VALUE` pairs (JSON, else text) or `--args` (a JSON object; `@file` reads one, `-` reads stdin). Over MCP each operation is one tool per server, named by its id with `_` for `.`: call it on `ops` for the plan, then the tool of the same name on `ops-apply` for the change.

### Reach the whole API

No library function is wrapped one by one. Everything a registered or editable-installed package publishes (here all seven: thousands of symbols) is found, then called from code run where it runs:

```bash
python -m pythontk ops run api.search query="triangle count"     # targets, kinds, signatures, summaries, the host each runs in, the exec that calls it
python -m pythontk ops run api.describe target=mayatk.env_utils._env_utils:EnvUtils.scene_triangle_count   # its whole docstring
python -m pythontk ops apply maya.python.exec code="import mayatk as mtk; mtk.EnvUtils.scene_triangle_count()" --scene C:/shots/a.ma
```

`api.search` and `api.describe` read the source and import nothing; a package read once is kept in the per-user cache until its source changes, so a session's first search takes under a second (the first ever, about fifteen), and the server reads them again at start. `maya.python.exec` and `blender.python.exec` run code in the host's console (`ptk.PythonConsole`), and `python.exec` in a plain Python for a function no application owns (pythontk, uitk, unitytk's Python half): the value of its last expression and what it printed come back, and the names it defines last as long as its instance does. Code has no plan, so these are on the `ops-apply` server alone (`apply`); a cancel interrupts the code as Ctrl+C does in a console, and the names stay. Code that opens windows (a Qt panel) is not for these instances. `maya.scene.view` and `blender.scene.view` capture an image of the scene (a playblast, a Workbench render), framing the objects named or all of them; over MCP the image comes back with the result. Unity runs no Python: `unity.csharp.exec` runs C# statements in the editor (`return x;` hands x back, `Vars` keeps values until the editor reloads its scripts, a compile error names its line), `unity.scene.view` renders the open scenes, and `unity.project.doctor` reads the editor, the render pipeline and the packages.

### Sessions (MCP)

Over MCP a host's calls run in one instance per Claude Code session, kept between calls: the first call starts it (a few seconds), and after that a call costs what its operation costs (under a tenth of a second for a read). Both servers share it, so what `maya_python_exec` builds on `ops-apply`, `maya_scene_view` on `ops` shows. It is never a session a person opened, it ends with the session, and it restarts when code it loaded changes on disk (that call's result says what was lost). `scenes` opens scene files first, replacing what it holds, and is refused while it holds unsaved changes, as an application asks before it discards them (save or discard them from code first); a tool called without them works on what it holds; a live run of a tool that plans saves the scenes it opened and changed. To work on a scene without saving it, open it with a read (`maya_scene_view` with `scenes`), then call tools without `scenes`; save from code when you mean to. Code has no plan, so it saves only what it saves itself (in a fresh instance from the command line too, which ends with the call); it counts as a change (it keeps no journal) unless it did not compile, and a save it makes of the open file clears that. A cancel interrupts code after two seconds, as Ctrl+C does; an operation that plans stops at its next checkpoint. Unity keeps one editor per project: `scenes` names the project folder or `.unity` scenes inside it; with none, the project the session last worked in, else the owned project in the per-user cache (`unity_project_build`: made once per editor version by Unity's CLI, about four minutes, and linked to the checkout's package). A project opens only in the editor version it names, and needs unitytk's package: `unity_project_install` writes the one manifest line that installs it.

### Add a codebase

Onboarding and upkeep are operations themselves, so they run the same way from the command line, over MCP or from a script:

```bash
python -m pythontk ops run operations.init package=mypkg     # the plan: what it would create
python -m pythontk ops apply operations.init package=mypkg   # mypkg/operations.py, its entry point in pyproject.toml, the first catalog
pip install -e <the project folder>                          # registers the entry point (until then: --provider mypkg.operations)
```

Registered, its whole public API is reached through `api.search` and code ([Reach the whole API](#reach-the-whole-api)); what it declares is only what code cannot reach ([Add an operation](#add-an-operation)).

### Keep it in line

`python -m pythontk ops run operations.check` checks every registered package (or `modules='["mypkg.operations"]'`; a catalog file another language writes is checked by its path, from the file alone): its catalog matches its declarations, a change can plan, every argument is typed, and twins (`maya.x` and `blender.x`) share their effect and their common arguments. Each problem is an error issue, so the command exits 1; a stale catalog's fix is `python -m pythontk ops apply operations.catalog module=mypkg.operations`. In this workspace `sync_workspace.py` runs both for every package (`--check` in CI), and `affected_tests.py` selects that check whenever a change touches a declared function's module or an `operations.py`, so drift shows in the edit's own test run.

### Add an operation

An operation is what code cannot reach on its own, so a library function is never wrapped as one: an agent finds it with `api.search` and calls it in a host's `python.exec` ([Reach the whole API](#reach-the-whole-api)). Three kinds are declared:

- **A Python host's two**: its console (`<host>.python.exec`) and an image of its scene (`<host>.scene.view`), declared by the host's library (mayatk, blendertk), since only it knows its host runs Python and how it renders.
- **A host Python cannot run**: the same two plus a doctor, declared in that host's language: the Unity kernel's C# `[Operation]` methods (`unity.csharp.exec`, `unity.scene.view`, `unity.project.doctor`), whose catalog the editor writes. A Unity feature's actions are its public C# API, reached through `unity.csharp.exec` like any library function.
- **The tooling's own actions**: work on the codebase itself (`instructions.*`, `operations.*`, `api.*`).

Each one:

1. **Plain values in and out**: names, paths and plain options, typed, with a docstring. Never a live object, never "the selection": an instance the tooling runs has nothing selected, so its caller names the objects. A parameter that takes code (a callable with a default) is left out. It runs headless.
2. **A dry run**: a function that changes anything takes an optional `ctx` (unannotated, or annotated `ptk.OpContext`) and guards every change site with `if ctx is None or ctx.should_change(...)` (`should_create`, `should_delete`, `should_write`), so it plans with a context and works without one.
3. **Twins match**: the same action on two hosts takes the same arguments (`maya.scene.view`, `blender.scene.view`), except where the hosts differ in kind.
4. **A test**: run the dry run and check it changed nothing, then run it live and check the change.
5. **Declare it** in its package's `operations.py` ([Operations](#operations) below), then rewrite its catalog: `operations.catalog`, or `python m3trik/scripts/sync_workspace.py` for every package here. `operations.check` holds steps 2, 3 and 5.

A panel calls the library function itself, never through an operation.

### Change a rule

Edit its pack in [`m3trik/agents/packs/`](../agents/packs/) (a rule every repo shares), [`m3trik/agents/workspace.md`](../agents/workspace.md) (the workspace's: the root `AGENTS.md` is its render and is never edited) or the repo `AGENTS.md` it belongs to, plus CODE_STANDARD and the [README](../README.md)'s pitch where it describes the rule, then run `python m3trik/scripts/sync_workspace.py` ([Keeping it in line](#keeping-it-in-line)).

### Keep the ledgers' history

`.claude/BACKLOG.md`, `FUTURE.md` and the hygiene denylist sit in no repo: they may name clients, and every repo here publishes or may. Their history is a repository of their own, made once by hand: `git init` inside `.claude/`, with a `.gitignore` there for what is no ledger (`receipts.json`, `settings.local.json`, `*.lock`, `worktrees/`). The SessionStart hook then commits what changed at each session start, after it has written the backlog's line, locally and nowhere else (it needs a git identity, `user.name` and `user.email`; without one it commits nothing, silently), and `git -C .claude log -S "<words>"` finds an entry a session deleted. A hidden folder is no unit, so no gate scans it, `push.ps1 -All` never takes it and the manifest never lists it.

### Troubleshooting

| Symptom | Fix |
|:---|:---|
| `claude` is not found | `%USERPROFILE%\.local\bin` on the user `PATH`; open a new terminal (VS Code: restart it) |
| an `ops` server is not connected | run `uv run --no-project python -m pythontk ops list` from the workspace root: its error names what is missing (uv, the `.venv`, a package in it) |
| an operation is missing | its package is not installed in the `.venv`, or `ops list` printed a warning naming the provider that failed to load |
| `nothing runs 'maya' operations here` | the host's library (mayatk, blendertk) is not installed in the Python that ran it |
| `cannot start this session's maya instance` | the error names why (no Maya found, a licence); the instance's own output is `instance.log` in `%TEMP%\ptk\ops_session\ops_session_<host>_<session>` |
| `... imports as an empty namespace here` | a repo folder hides its package: install it with `editable_mode=compat` ([Set up](#set-up), step 1), or put that folder on `PYTHONPATH` |
| an agent or `/backlog` listed twice, or a hook running twice | the copies the plugin replaced are still in the workspace: delete `.claude/agents`, `.claude/skills` and `.claude/hooks`, and any `hooks` block in `.claude/settings.json` |

## Instructions

### The layout

| File | Holds | Read by |
|:---|:---|:---|
| `AGENTS.md` | a folder's rules, at every level that has any (a nested one scopes its rules to its folder); the workspace root's is a render of [`m3trik/agents/workspace.md`](../agents/workspace.md) | every agent (the open convention) |
| `CLAUDE.md` | a stub, `@AGENTS.md` (the workspace root's also imports its packs) | Claude Code, which reads `AGENTS.md` only while no `CLAUDE.md` exists at or above the session root |
| `.agents/packs/<name>.md` | a vendored pack: rules several repos share | the pack hook, the root stub, and any agent following the pointer block |
| `.claude/rules/<name>.md` | a path-scoped pack (`paths:` frontmatter), or a repo's own rule for one kind of file | Claude Code, only when a matching file is touched |
| `.agents/session_hook.py` + `.claude/settings.json` | a repo's SessionStart hook, adding its packs to a session rooted in it | Claude Code (only the session root's settings run) |

`AGENTS.md` never `@imports` (other agents do not expand them). A pointer block at its top, written by the tooling, names the repo's packs for every agent.

### Packs

A pack is one Markdown file of rules shared word for word, written once in [`m3trik/agents/packs/`](../agents/packs/) and vendored, under a drift check, into each repo that takes it:

- [principles](../agents/packs/principles.md): every repo, whatever its language;
- [python](../agents/packs/python.md): how the principles are spelled in Python;
- [csharp](../agents/packs/csharp.md): the same for C#, path-scoped to `*.cs` / `*.asmdef` (unitytk).

The three layers are principles (packs, shared), spellings (one pack per language) and shapes (each repo's own `AGENTS.md`). Rules for a pack: one line each, the rationale cited as CODE_STANDARD `§N`, no work history, dates or counts (churn defeats prompt caching), no `@imports`; the only frontmatter key is `paths:`. Together a repo's unconditional packs stay under 10,000 characters, the most a SessionStart hook may add. Any rule, in a pack or an `AGENTS.md`, spends its words on design, architecture and tool behavior: it names an established standard (SOLID, Nielsen's heuristics) rather than restating it, and leaves what a tool checks (formatting, lint, a validator) to that tool, run at review.

### How a session gets them (measured, Claude Code)

- **In the workspace**, the root stub imports the root's packs, so they load once however many repos a session touches. A repo's hook never fires there: only the session root's settings run, and a session rooted in a repo inside the workspace finds the root's packs above and adds none. It knows them by their `.agents/packs` folder, which is why the root vendors its packs and never imports their source.
- **In a standalone clone** (local, cloud, CI), the repo's hook adds its packs at session start and after compaction.
- **A path-scoped pack** loads natively when a matching file is touched, in any layout.
- **Another agent** reads `AGENTS.md`, whose pointer block names the packs.

### Keeping it in line

[`m3trik/workspace.json`](../workspace.json) declares each unit's packs (and the root's). [`sync_workspace.py`](../scripts/sync_workspace.py) applies the declaration through `AgentInstructions.sync` (moving a `CLAUDE.md`'s rules into `AGENTS.md`, writing stubs, vendoring packs, the pointer block, the hook) and `--check` holds it: stubs, packs against their source, pointer blocks, hooks, `§N` citations against [CODE_STANDARD](CODE_STANDARD.md), dated lines, and every package's `operations.json` against its declarations. To change a shared rule, edit its pack in `m3trik/agents/packs/`, then run `python m3trik/scripts/sync_workspace.py`.

Every instruction file is a source or a render. The workspace root is not a repository, so it holds only renders: its `AGENTS.md` is [`m3trik/agents/workspace.md`](../agents/workspace.md) with each link re-based (the source's links are valid where it sits, its Dispatch table rewritten from the manifest), its stub and packs written by the same sync. `--check` builds the root in a temporary folder and checks that build, so CI holds the workspace's rules with no root to read; where a root exists, it must be the build. The write copies that build over the root's own files (`AGENTS.md`, the stub, the packs) and touches nothing else: no other folder is walked, and an `AGENTS.md` there that is another project's stops it, never overwritten. A folder is the workspace when the cascade's first package is checked out beside this repo; a lone clone of `m3trik` writes nothing outside itself and treats no neighbouring folder as a unit.

The same engine is a set of operations any codebase can use:

```bash
python -m pythontk ops run instructions.check root=.             # report problems
python -m pythontk ops run instructions.sync root=. source=PACKS packs='["principles"]'   # the plan
python -m pythontk ops apply instructions.sync root=. source=PACKS packs='["principles"]' # write it
python -m pythontk ops run instructions.measure root=. touched='["pkg/mod.py"]'          # what loads
python -m pythontk ops run instructions.duplicates root=.        # rules written more than once
```

## Operations

A package declares its operations in `<package>/operations.py` (a tuple `OPERATIONS` of `ptk.Operation`) and commits the catalog `operations.catalog` writes beside it (`ptk.OperationProvider`, which also onboards a package and checks it); `pyproject.toml` registers the module under the `pythontk.operations` entry points. Each operation is an existing library function: its typed signature is the argument schema, its docstring the description, and an optional `ctx` (`ptk.OpContext`) gives it a dry run (`should_change` / `should_create` / `should_delete` / `should_write`). The declaration adds only what the code cannot say: the id, the effect and the host.

```python
OPERATIONS = (
    Operation("maya.python.exec", "pythontk:PythonConsole.run", effect="code", host="maya"),
    Operation("maya.scene.view", "mayatk:CamUtils.capture_view", host="maya"),
)
```

- **Ids** are `<area>.<action>`, at most 34 characters: the plugin serves one as the tool `mcp__plugin_m3trik_<server>__<id>`, and Claude caps a tool name at 64. One a host application runs starts with its host (`maya.scene.view`, `blender.scene.view`, `unity.scene.view`), and no other id may.
- **Effects** say what an operation may change, and so what undoes it: `read` (nothing; agents run it freely), `state` (what the running application holds, its open scenes and their objects: one undo step), `files` (a dry run lists every file first; version control is the way back) and `code` (a host's console: it may change anything, has no plan and no undo, so only `apply` runs it).
- **Hosts**: mayatk and blendertk register a runner under `pythontk.operation_hosts` (`MayaSceneFiles`, `BlenderSceneFiles`), and pythontk one for plain Python (`python`, `PureSceneFiles`, which opens no scenes): a call runs in a mayapy, background Blender or Python the tooling started, a NEW one per call from the command line (`ptk.BatchOperationHost`) or one kept per session over MCP (`ptk.SessionOperationHost`: the same run folders, served in order from a `ptk.JobQueue`, bound to the server that started it, restarted when code it loaded changes). It opens the scenes named with `--scene` (`scenes` over MCP) and saves those a finished live run of an operation that plans changed. A person's open session is never reached.
- **Command line**: `python -m pythontk ops list | search | describe | run | apply | mcp`; the upkeep is `operations.init`, `catalog` and `check`. `--provider` adds a declaration module (built live from a checkout) or a catalog file (`.json`, read as it stands: one a Unity project's editor writes into the project, with no Python package).
- **The whole API**: `ptk.ApiSurface` behind `api.search` and `api.describe` reads every public symbol of every registered or editable-installed package from its source, importing nothing, and the public C# a package declares (`CSHARP_SOURCES` in its root `__init__.py`: unitytk's, read with no editor): the same reader checks each release's delta (`check_api_surface.py`) and serves `help()` on a class. Each row names the operation whose code calls it (`exec`: a host's `python.exec`, or `unity.csharp.exec` with a static C# member's `call`), so a client lists a few tools per host, never thousands.
- **MCP**: `python -m pythontk ops mcp` serves reads and dry runs; `ops mcp --apply` serves only the tools that make changes, so a permission rule per server allows every plan and still asks before each change. A host's calls run in the client's session instance ([Sessions](#sessions-mcp)): `CLAUDE_CODE_SESSION_ID` (or `PYTHONTK_OPS_SESSION`) names it, and without one each server keeps its own. A result that is an image the run made comes back as the image. The plugin registers both; another client runs them with the SDK (`pip install "pythontk[mcp]"`, Python 3.10+, or `uv run --with "mcp>=2.3,<3" python -m pythontk ops mcp`).

The contract (ids, effects, `OpRequest`, `Outcome`, `Issue`, `Change`) is shared with the Unity package, whose C# types are generated from these payloads' JSON Schema.
