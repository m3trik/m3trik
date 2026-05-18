# m3trik

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../CLAUDE.md) · **Related**: [server](../server/CLAUDE.md) · **Publishes**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · [mayatk](../mayatk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Primary tool — `push.ps1`

**The** release path for ecosystem packages. Handles dependency sync, PyPI publication, version bumps. Never `git push` these packages manually.

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge
```

## Style

- PascalCase verbs (Verb-Noun).
- Config reads: `server/scripts/Config.psm1` is the SSoT for server hostname/user — import rather than hardcode.

## Sub-scripts

- [scripts/](scripts/CLAUDE.md) — Repo-maintenance helpers (inventory, API registry, credential rotation).

See [CHANGELOG.md](CHANGELOG.md) for history.
