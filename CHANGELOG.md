# m3trik — Changelog

- **Update Samba Credentials** — `update_samba_creds.ps1` rotates Samba passwords using the secure credential store.
- **Workspace Repo Inventory** — `scripts/generate_workspace_inventory.py` + `Generate-WorkspaceInventory.ps1` scan direct child repos under `_scripts/` and write Markdown/JSON inventory to `m3trik/docs/` (repo breakdowns, package roots, code roots, tracked LOC).
