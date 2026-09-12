from __future__ import annotations

import os
from pathlib import Path


def find_root() -> Path:
    configured = os.environ.get("REBENCH_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "scripts").is_dir():
            return parent
    raise RuntimeError("Could not locate the Rebench repository root")


ROOT = find_root()
SUITES_DIR = ROOT / "configs" / "suites"
SELECTORS_DIR = ROOT / "selectors"
SCRIPTS_DIR = ROOT / "scripts"
RUNS_DIR = ROOT / "runs"
TASKS_DIR = ROOT / "tasks"
EVALUATOR_DIR = ROOT / "SWE-rebench-V2"
