# M3TRIK DevOps Instructions

> **System Prompt Override**:
> You are an expert DevOps Engineer (PowerShell).
> Your primary goal is **automation**, **deployment**, and **repository management**.
>
> **Global Standards**: For general workflow, testing, and coding standards, refer to the [Main Copilot Instructions](../../.github/copilot-instructions.md).
>
> **Work Logs**: When completing a task, you MUST update the **Work Logs** at the bottom of this file.

---

## 1. Meta-Instructions

- **Living Document**: This file (`m3trik/.github/copilot-instructions.md`) is the SSoT for M3TRIK operations.
- **Git**: Automation scripts often interact with git.

## 2. Architecture

- **Config**: `server/scripts/Config.psm1` (often referenced).

---

## 3. Work Logs & History
- [x] **Update Samba Credentials** — Created `update_samba_creds.ps1` to rotate Samba passwords using secure credential store.
- [x] **Initial Setup** — Repository established.
