![M3trik GitHub Image](m3trik_github.png)

Tech-art tooling for game-art and DCC pipelines — one ecosystem, built in layers:

**[pythontk](https://github.com/m3trik/pythontk) → [uitk](https://github.com/m3trik/uitk) → [mayatk](https://github.com/m3trik/mayatk) → [tentacle](https://github.com/m3trik/tentacle)**

| Repo | What it is |
|---|---|
| [pythontk](https://github.com/m3trik/pythontk) | Composable Python primitives — files, images, video, audio, geometry, math. The DCC-agnostic foundation everything else builds on. |
| [uitk](https://github.com/m3trik/uitk) | Convention-driven Qt framework: *name it, and it connects.* Qt Designer files + slot classes become working tools with zero glue code. |
| [mayatk](https://github.com/m3trik/mayatk) | Maya 2025+ tech-art toolkit (`cmds` + OpenMaya, no PyMEL) — tool panels, scene automation, and bridges into Marmoset, Substance, RizomUV, Blender, and Unity. |
| [tentacle](https://github.com/m3trik/tentacle) | Marking-menu launcher for DCC apps — hold a key, flick toward a wedge, release. ~60 Maya tool panels; Blender port in progress. |
| [extapps](https://github.com/m3trik/extapps) | Standalone Switchboard panels — texture compositing and conversion, photogrammetry, Substance / Marmoset automation. |

## This repo

PowerShell DevOps for the ecosystem — release automation, repo-maintenance scripts, and cross-package reference docs.

- **[`push.ps1`](push.ps1)** — the release path for the ecosystem packages (`pythontk`, `uitk`, `mayatk`, `tentacle`): dependency sync, PyPI guard, version tags, GitHub Releases with changelog-delta notes.
- **[`scripts/`](scripts/)** — maintenance tooling: API-registry generation, Maya↔Blender parity sweeps, docs sweeps, context-budget guard, workspace inventory.
- **[`docs/`](docs/)** — cross-package reference: API shadow report, context-budget rules, docs standard.

Conventions and usage: [`CLAUDE.md`](CLAUDE.md).
