![M3trik GitHub Image](m3trik_github.png)

PowerShell DevOps for the m3trik ecosystem — release automation, repo-maintenance scripts, and cross-package reference docs.

- **[`push.ps1`](push.ps1)** — the release path for the ecosystem packages (`pythontk`, `uitk`, `mayatk`, `tentacle`): dependency sync, PyPI guard, version tags, GitHub Releases with changelog-delta notes.
- **[`scripts/`](scripts/)** — maintenance tooling: API-registry generation, Maya↔Blender parity sweeps, docs sweeps, context-budget guard, workspace inventory.
- **[`docs/`](docs/)** — cross-package reference: API shadow report, context-budget rules, docs standard.

Conventions and usage: [`CLAUDE.md`](CLAUDE.md).
