# Release runner

The cascade's Release workflow (`pythontk`, `uitk`, `mayatk`, `blendertk`, `tentacle`), run by a self-hosted runner on the machine that has Maya and Blender. This repo is private on purpose: a self-hosted runner never serves a public repo.

Everything here is published from [m3trik](https://github.com/m3trik/m3trik) by `scripts/Install-ReleaseRunner.ps1`; edit `release_runner/` there. How it works and how to use it: [docs/RELEASE_RUNNER.md](https://github.com/m3trik/m3trik/blob/main/docs/RELEASE_RUNNER.md).

```powershell
gh workflow run release.yml --repo m3trik/release-runner -f dry_run=true                 # the plan, and the reviewed= value
gh workflow run release.yml --repo m3trik/release-runner -f reviewed=<package@sha,...>   # release what you reviewed
```
