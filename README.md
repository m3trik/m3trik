![M3trik GitHub Image](m3trik_github.png)

# m3trik

Repository management, deployment, and workspace automation for the `_scripts` monorepo.

## Workspace Inventory

The generated monorepo inventory lives in `docs/workspace_repo_inventory.md` with a machine-readable companion at `docs/workspace_repo_inventory.json`.

Regenerate it from the workspace root with:

```powershell
.\m3trik\Generate-WorkspaceInventory.ps1
```

You can still run the Python generator directly when needed:

```powershell
o:\Cloud\Code\_scripts\.venv\Scripts\python.exe o:\Cloud\Code\_scripts\m3trik\scripts\generate_workspace_inventory.py
```
