# Rebench20

Rebench20 is a reproducible harness for comparing coding-agent configurations on
[SWE-rebench V2](https://huggingface.co/datasets/PrimeIntellect/SWE-rebench-V2-Filtered-Verified).
Suites are ordinary JSON files, so the benchmark can grow beyond the original
Hard-20 without changing the Python scripts.

The current baseline is `configs/suites/hard20.json`. Its gold validation is
20/20 as of 2026-09-11.

## Install

From PowerShell in this repository:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
rebench doctor
```

If the evaluator is not already present, clone it once:

```powershell
git clone https://github.com/SWE-rebench/SWE-rebench-V2.git
```

`rebench doctor` checks Python, Docker, the evaluator checkout, directories,
dependencies, and the selected suite before a benchmark run.

## Standard workflow

Inspect and validate the suite:

```powershell
rebench suite list
rebench suite show hard20 --tasks
rebench suite validate hard20
rebench gold --suite hard20
```

Prepare a batch for an agent configuration:

```powershell
rebench prepare codex-default 1 5 --suite hard20
```

Give each agent the corresponding `prompt.txt` and `workspace` under
`runs\codex-default\`. After the agents finish:

```powershell
rebench collect codex-default 1 5 --suite hard20
rebench evaluate codex-default --suite hard20 --workers 2
rebench status --suite hard20
```

Evaluation is cumulative: only runs with collected, non-empty patches are
evaluated.

## Create or change a suite

Copy an existing suite to get a valid starting point:

```powershell
rebench suite copy hard20 hard30
```

Tasks can then be added directly from the configured dataset or removed by ID:

```powershell
rebench suite add hard30 owner__repository-123
rebench suite remove hard30 owner__repository-456
```

`suite add` looks up repository, language, and difficulty metadata. `suite remove`
renumbers the remaining tasks automatically.

Edit `configs\suites\hard30.json`, add or remove task objects, and make `n`
consecutive starting at 1. Then validate it:

```powershell
rebench suite validate hard30
rebench suite show hard30 --tasks
rebench gold --suite hard30
```

A suite task requires:

```json
{
  "n": 1,
  "instance_id": "owner__repository-123",
  "repo": "owner/repository",
  "language": "python",
  "difficulty": "hard"
}
```

The validator rejects missing fields, duplicate task IDs, and
unordered/non-consecutive task numbers. A suite can additionally set
`"constraints": {"unique_repositories": true}` to reject repeated repositories. Gold validation
should pass before a new suite is used for agent comparisons.

Use a different run configuration name when changing either the agent settings
or suite. For example, prefer `codex-default-hard30` over reusing
`codex-default`; this prevents results from different suites being mixed.

## Repository layout

```text
configs/suites/     Versioned benchmark definitions
src/rebench/        Unified command-line interface and validation
scripts/            Benchmark implementation (kept compatible)
tests/              Fast tests that do not run Docker evaluations
tasks/              Generated private/evaluation task data (ignored)
runs/               Generated workspaces, patches, and results (ignored)
repos/              Local repository checkouts (ignored)
SWE-rebench-V2/     External evaluator checkout (ignored)
```

Selection utilities such as `select_hard20.py` remain under `scripts/` for now.
They will be moved behind explicit suite-generation commands in a later phase.

## Safety notes

- Do not use `--force` unless replacing an existing run workspace intentionally.
- Do not commit `tasks/`; it can contain private gold data.
- Do not let agents modify tests. The collector reports test-like file changes.
- Preserve the generated report and suite name when publishing benchmark scores.
