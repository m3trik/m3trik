# The Claude Code plugin

The ecosystem's Claude Code machinery, versioned here instead of living only in the workspace's unversioned `.claude/`. Rules are not here: they are each repo's `AGENTS.md` and the packs, which every agent reads and every clone carries. **Setting it up, using it and fixing it: [AGENT_INSTRUCTIONS.md](../docs/AGENT_INSTRUCTIONS.md#set-up)** (install it at project scope, step 4).

| Part | In a session | What |
|:---|:---|:---|
| [`agents/reviewer.md`](agents/reviewer.md) | `m3trik:reviewer` | an independent review of one change |
| [`agents/sweep.md`](agents/sweep.md) | `m3trik:sweep` | read-only inventories across the repos |
| [`skills/backlog/`](skills/backlog/SKILL.md) | `/m3trik:backlog` | works `.claude/BACKLOG.md` as a gated pipeline |
| `hooks/` | SessionStart, PostToolUse, Stop | grades the project's backlog; the auto-critique of a turn's edits (`hooks.py`, stdlib Python run through `uv` with no shell, so on every OS; the edit marker is async, so no tool call waits on it) |
| `.mcp.json` | `plugin:m3trik:ops`, `plugin:m3trik:ops-apply` | the operations' MCP servers: reads and plans, and only the tools that make changes; Maya, Blender and plain-Python calls run in this session's own instances, `api_search` / `api_describe` find any function and `python_exec` / `maya_python_exec` / `blender_python_exec` run code there |

## Editing it

The marketplace is a local directory, so the plugin is read from this folder as it stands and an edit reaches the next session. `claude plugin validate m3trik/claude` checks the plugin (`claude plugin validate m3trik` the marketplace). The hook scripts find the project through `CLAUDE_PROJECT_DIR`, never through their own location: a plugin's scripts live outside the project. A tool here is named `mcp__plugin_m3trik_<server>__<tool>`, 30 characters of prefix for `ops-apply` within Claude's 64, which is why an operation id is at most 34 (`Operation.ID_MAX`).

## What it replaced

The workspace's `.claude/agents/`, `.claude/skills/backlog/`, `.claude/hooks/` and the `hooks` block of `.claude/settings.json`. The workspace keeps what is its own: `BACKLOG.md`, `FUTURE.md`, `receipts.json`, and in `settings.json` its `permissions` and the plugin's enablement.
