# Test badge standard — one meaning for every package's number

Every repo in `_scripts/` stamps a shields.io **Tests** badge into its README. This is the
contract for what that number counts, so a reader can compare `pythontk`'s badge with
`server`'s and get a true picture.

**Nav**: [← m3trik](../CLAUDE.md) · [Docs standard](DOCS_STANDARD.md) · [Context budget](CONTEXT_BUDGET.md)

## The rule

> **Count individual test cases — never suites, modules, scripts or categories.
> Skips are not passes.**

A repo whose five test scripts assert two hundred things reports **200 passed**, not
`5 passed`. Suite-level counting is the failure this standard exists to prevent: it
understates coverage by an order of magnitude and makes two packages' badges
non-comparable, which is exactly how `server` came to advertise "5 Passing" for a
36-check diagnostic and `mayatk` came to fold environment-skipped tests into its
`passed` total.

| Term | Definition |
|:--|:--|
| **passed** | Individual test cases that ran and passed. `testsRun - failures - errors - skipped`. |
| **failed** | `failures + errors`. |
| **skipped** | Excluded from `passed`, and never turns a passing run a worse colour — an all-green run with environment-gated skips still reads green. (If *everything* skipped, `passed` and `failed` are both 0, which lands in "nothing ran" below — correctly, since nothing did.) |

## Badge format

```markdown
[![Tests](https://img.shields.io/badge/Tests-<message>-<color>.svg)](<path-to-test-dir>)
```

| Run | Message | Colour |
|:--|:--|:--|
| No failures | `N passed` | `brightgreen` |
| Some of each | `N passed, M failed` | `orange` |
| Nothing passed | `M failed` | `red` |
| Nothing ran at all | `0 passed` | `lightgrey` |

"Nothing ran" means zero passes *and* zero failures — CI could not reach the host, or
discovery matched no tests. It is **unknown**, not green: a green badge over a run that
produced no results is the worst reading of the four, so every implementation (Python and
shell alike) tests this case first.

- Label is `Tests` (capital T), alt text is `Tests`, and the badge links to the repo's
  `test/` directory — resolved **relative to the README's own location**, so
  `docs/README.md` yields `../test/` and a moved README can't break the link.
- Shields **style** (`?style=flat-square` vs the plain `.svg` suffix) is a per-README
  cosmetic choice — match the rest of that README's badge row. `server` and `comfyui`
  use `flat-square`; the Python packages use `.svg`.
- A **partial run must not stamp the badge** — whether scoped by argument (one module) or
  by environment (no DCC available, so the DCC-dependent half skips wholesale). This is not
  cosmetic: a plain tentacle run publishing its 197-of-541 count replaced a canonical
  `534 passed, 2 failed` with a green `197 passed`, erasing two real failures. Every runner
  guards itself — mayatk requires every in-scope module to have run, blendertk and unitytk
  require a full sweep, tentacle requires the Maya suite, and pythontk and uitk gate on
  `StatusBadge.gate` (below) — and all expose `--no-badge`.
- An **environment-gated skip is still green**, and must stay green whichever idiom
  expressed it. A module skipped via `@unittest.skipUnless` and one skipped by raising
  `SkipTest` in `setUpClass`/`setUpModule` both *ran*; only a module that never imported
  (unittest substitutes a `unittest.loader` stand-in) did not. Conflating the two blocked
  the badge permanently for any module whose cases are all `setUpClass`-gated.
- A repo keeping **two front doors** (uitk: a landing `README.md` plus the packaged
  `docs/README.md`) stamps *both* — one showing a badge the other lacks, or a stale
  count, is the same inconsistency in miniature.

## Implementation — one shared writer

`ptk.StatusBadge` ([`pythontk/core_utils/status_badge.py`](../../pythontk/pythontk/core_utils/status_badge.py))
is the single source of truth. Every Python runner calls it; none of them re-derive the
wording, colours, escaping or insert position:

```python
from pythontk.core_utils.status_badge import StatusBadge

StatusBadge.update_test_badge(readme_path, passed, failed, test_dir=TEST_DIR)
```

The **run-completeness gate** lives there too, for the same reason — six runners stamp
badges, so "did this run cover everything?" has to be one implementation:

```python
expected = StatusBadge.discover_module_names(TEST_DIR)   # derived from disk, never stale
ran      = {StatusBadge.module_of(t) for t in cases
            if not StatusBadge.is_import_standin(t)}
allowed, reason = StatusBadge.gate(expected, ran, passed, failed)
if not allowed:
    print(f"[INFO] Badge not updated ({reason}).")
```

It replaces an existing badge in place (matching any alt text or label casing, linked or
bare, so legacy badges migrate rather than duplicate), and on first use inserts at the end
of the README's leading badge block — or above the title when there is none.

Tests: [`pythontk/test/test_status_badge.py`](../../pythontk/test/test_status_badge.py).

## Who writes what

| Repo | Runner | Unit counted |
|:--|:--|:--|
| `pythontk` · `uitk` · `tentacle` | `test/run_tests.py` | unittest test cases |
| `mayatk` | `test/run_tests.py` (chunked mayapy + GUI pass) | unittest test cases, aggregated across chunks |
| `blendertk` | `test/run_tests.py` (fresh headless Blender per suite) | the suite's own `===RESULT: … === (ok/attempted)` sentinel, else its `OK` / `FAIL` check lines |
| `unitytk` | `test/run_tests.py` | unittest test cases |
| `server` | `test/run-tests.ps1` → `.github/workflows/daily-tests.yml` | per-check `Items` across the five categories |
| `comfyui` | `test/test-desktop-install.ps1` → `.github/workflows/ci.yml` | per-check `[PASS]` / `[FAIL]` markers |

The two CI-driven repos write their badge from shell, so they reimplement the wording
above rather than importing `StatusBadge` — keep them in step with this page when the
format changes. `server/test/run-tests.ps1` prints a machine-readable
`TESTS: <n> passed, <m> failed` line unconditionally (a `-Quiet` run must stay parseable);
the workflow reads that line rather than grepping display markers.

**Blendertk's sentinel contract.** A suite reports `===RESULT: PASS=== (ok/attempted)` —
`attempted` excludes skips, so a fully skipped suite says `(skipped)` and contributes
nothing. The suite's own tally wins over line-counting when present (it knows things the
runner can't, e.g. that a multi-line traceback is *one* failed check). A suite that passes
while reporting no checks is a silent hole in the totals, so the runner names it in a
warning instead of letting it blend into the green.

## Not badged

`androidtk`, `extapps`, `m3trik` and `www` ship test files but no runner that stamps a
badge. That is a gap, not a different convention — if one gains a badge it follows this
page.
