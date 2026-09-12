from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import ROOT, SUITES_DIR


class SuiteError(ValueError):
    pass


def suite_files() -> list[Path]:
    return sorted(SUITES_DIR.glob("*.json")) if SUITES_DIR.exists() else []


def resolve_suite(value: str | Path | None = None) -> Path:
    if value is None:
        default = SUITES_DIR / "hard20.json"
        return default if default.exists() else ROOT / "suite.json"

    candidate = Path(value)
    if candidate.suffix.lower() == ".json" or candidate.parent != Path("."):
        if not candidate.is_absolute():
            candidate = ROOT / candidate
    else:
        candidate = SUITES_DIR / f"{candidate.name}.json"
    return candidate.resolve()


def load_suite(value: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = resolve_suite(value)
    if not path.is_file():
        raise SuiteError(f"Suite does not exist: {path}")
    try:
        suite = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SuiteError(f"Invalid JSON in {path}: {exc}") from exc
    return path, suite


def validate_suite(suite: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(suite, dict):
        return ["suite must be a JSON object"]

    name = suite.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")
    dataset = suite.get("dataset")
    if not isinstance(dataset, str) or not dataset.strip():
        errors.append("dataset must be a non-empty string")

    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list")
        return errors

    required = ("n", "instance_id", "repo", "language", "difficulty")
    numbers: list[Any] = []
    ids: list[Any] = []
    repos: list[Any] = []
    for index, task in enumerate(tasks, start=1):
        label = f"tasks[{index - 1}]"
        if not isinstance(task, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in required:
            if field not in task or task[field] in (None, ""):
                errors.append(f"{label}.{field} is required")
        numbers.append(task.get("n"))
        ids.append(task.get("instance_id"))
        repos.append(task.get("repo"))

    expected = list(range(1, len(tasks) + 1))
    if numbers != expected:
        errors.append(f"task numbers must be consecutive and ordered: {expected}")
    duplicates = sorted(str(v) for v, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate instance_id values: {', '.join(duplicates)}")

    constraints = suite.get("constraints", {})
    if isinstance(constraints, dict) and constraints.get("unique_repositories"):
        duplicates = sorted(str(v) for v, count in Counter(repos).items() if count > 1)
        if duplicates:
            errors.append(f"duplicate repo values: {', '.join(duplicates)}")
    return errors


def suite_summary(suite: dict[str, Any]) -> dict[str, Any]:
    tasks = suite.get("tasks", [])
    return {
        "name": suite.get("name", ""),
        "dataset": suite.get("dataset", ""),
        "tasks": len(tasks),
        "repositories": len({task.get("repo") for task in tasks}),
        "languages": dict(sorted(Counter(task.get("language") for task in tasks).items())),
        "difficulties": dict(sorted(Counter(task.get("difficulty") for task in tasks).items())),
    }
