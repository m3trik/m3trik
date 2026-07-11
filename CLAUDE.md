# m3trik

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../CLAUDE.md) · [README](README.md) · [docs](docs/) · **Related**: [server](../server/CLAUDE.md) · **Publishes**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Primary tool — `push.ps1`

**The** release path for ecosystem packages. Handles dependency sync, PyPI publication, version bumps. Never `git push` these packages manually. On publish it also tags `vX.Y.Z` + cuts a GitHub Release (notes = `CHANGELOG.md` lines added since the last release, via `Get-ChangelogDelta`/`git diff origin/main..dev`); additive + non-fatal.

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge
```

## Style

- PascalCase verbs (Verb-Noun).
- Config reads: `server/scripts/Config.psm1` is the SSoT for server hostname/user — import rather than hardcode.

## Sub-scripts

- [scripts/](scripts/CLAUDE.md) — Repo-maintenance helpers (inventory, API registry, credential rotation).

See [CHANGELOG.md](CHANGELOG.md) for history.
