from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import EVALUATOR_DIR, ROOT, RUNS_DIR, SCRIPTS_DIR, TASKS_DIR
from .suites import SuiteError, load_suite, resolve_suite, suite_files, suite_summary, validate_suite


def _print_summary(path: Path, suite: dict) -> None:
    summary = suite_summary(suite)
    print(f"Suite:        {summary['name']}")
    print(f"File:         {path}")
    print(f"Dataset:      {summary['dataset']}")
    print(f"Tasks:        {summary['tasks']}")
    print(f"Repositories: {summary['repositories']}")
    print("Languages:    " + ", ".join(f"{k}={v}" for k, v in summary["languages"].items()))
    print("Difficulties: " + ", ".join(f"{k}={v}" for k, v in summary["difficulties"].items()))


def _validated_suite(value: str | None) -> tuple[Path, dict]:
    path, suite = load_suite(value)
    errors = validate_suite(suite)
    if errors:
        raise SuiteError("Suite validation failed:\n- " + "\n- ".join(errors))
    return path, suite


def command_suite_list(_: argparse.Namespace) -> int:
    files = suite_files()
    if not files:
        print("No suites found.")
        return 0
    for path in files:
        try:
            _, suite = load_suite(path)
            errors = validate_suite(suite)
            state = "valid" if not errors else f"invalid ({len(errors)} errors)"
            print(f"{path.stem:20} {len(suite.get('tasks', [])):4} tasks  {state}")
        except SuiteError as exc:
            print(f"{path.stem:20} invalid: {exc}")
    return 0


def command_suite_show(args: argparse.Namespace) -> int:
    path, suite = _validated_suite(args.suite)
    _print_summary(path, suite)
    if args.tasks:
        print("\n #  LANGUAGE  DIFFICULTY  INSTANCE")
        for task in suite["tasks"]:
            print(f"{task['n']:2}  {task['language']:8}  {task['difficulty']:10}  {task['instance_id']}")
    return 0


def command_suite_validate(args: argparse.Namespace) -> int:
    path, suite = load_suite(args.suite)
    errors = validate_suite(suite)
    if errors:
        print(f"INVALID: {path}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VALID: {path}")
    _print_summary(path, suite)
    return 0


def command_suite_copy(args: argparse.Namespace) -> int:
    source_path, suite = _validated_suite(args.source)
    target = resolve_suite(args.name)
    if target.exists() and not args.force:
        raise SuiteError(f"Suite already exists: {target} (use --force to replace)")
    suite["name"] = args.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"Created {target} from {source_path.name}")
    print("Edit its tasks, then run: rebench suite validate " + args.name)
    return 0


def command_suite_add(args: argparse.Namespace) -> int:
    path, suite = _validated_suite(args.suite)
    if any(task["instance_id"] == args.instance_id for task in suite["tasks"]):
        raise SuiteError(f"Task is already in the suite: {args.instance_id}")

    from datasets import load_dataset

    print(f"Looking up {args.instance_id} in {suite['dataset']}...")
    dataset = load_dataset(suite["dataset"], split="train")
    matches = [row for row in dataset if row["instance_id"] == args.instance_id]
    if len(matches) != 1:
        raise SuiteError(f"Expected one dataset row for {args.instance_id}; found {len(matches)}")
    row = matches[0]
    metadata = row.get("meta") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    inferred_difficulty = metadata.get("llm_metadata", {}).get("difficulty") if isinstance(metadata, dict) else None
    suite["tasks"].append({
        "n": len(suite["tasks"]) + 1,
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "language": str(row["language"]).lower(),
        "difficulty": args.difficulty or inferred_difficulty or "unknown",
    })
    errors = validate_suite(suite)
    if errors:
        raise SuiteError("Updated suite would be invalid:\n- " + "\n- ".join(errors))
    path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"Added task {len(suite['tasks'])}: {args.instance_id}")
    print(f"Validate with: rebench suite validate {path.stem}")
    return 0


def command_suite_remove(args: argparse.Namespace) -> int:
    path, suite = _validated_suite(args.suite)
    original_count = len(suite["tasks"])
    suite["tasks"] = [task for task in suite["tasks"] if task["instance_id"] != args.instance_id]
    if len(suite["tasks"]) == original_count:
        raise SuiteError(f"Task is not in the suite: {args.instance_id}")
    for number, task in enumerate(suite["tasks"], start=1):
        task["n"] = number
    if not suite["tasks"]:
        raise SuiteError("Refusing to create an empty suite")
    path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"Removed {args.instance_id}; {len(suite['tasks'])} tasks remain")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0]))
    checks.append(("Docker command", shutil.which("docker") is not None, shutil.which("docker") or "not found"))
    checks.append(("Evaluator", (EVALUATOR_DIR / "scripts" / "eval.py").is_file(), str(EVALUATOR_DIR)))
    checks.append(("Scripts", SCRIPTS_DIR.is_dir(), str(SCRIPTS_DIR)))
    checks.append(("Tasks directory", TASKS_DIR.is_dir(), str(TASKS_DIR)))
    checks.append(("Runs directory", RUNS_DIR.is_dir(), str(RUNS_DIR)))
    try:
        path, suite = load_suite(args.suite)
        errors = validate_suite(suite)
        checks.append(("Suite", not errors, str(path) if not errors else "; ".join(errors)))
    except SuiteError as exc:
        checks.append(("Suite", False, str(exc)))
    try:
        import datasets  # noqa: F401
        checks.append(("datasets package", True, "available"))
    except ImportError:
        checks.append(("datasets package", False, "install the project dependencies"))

    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'FAIL':4}  {name:18} {detail}")
    failed = sum(not ok for _, ok, _ in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


def _run_legacy(script: str, arguments: list[str], suite_value: str | None) -> int:
    suite_path, _ = _validated_suite(suite_value)
    env = os.environ.copy()
    env["REBENCH_SUITE"] = str(suite_path)
    command = [sys.executable, str(SCRIPTS_DIR / script), *arguments]
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def command_prepare(args: argparse.Namespace) -> int:
    values = [args.config, str(args.start), str(args.end)]
    if args.force:
        values.append("--force")
    return _run_legacy("prepare_runs.py", values, args.suite)


def command_collect(args: argparse.Namespace) -> int:
    values = [args.config]
    if args.start is not None:
        values.extend((str(args.start), str(args.end)))
    return _run_legacy("collect.py", values, args.suite)


def command_evaluate(args: argparse.Namespace) -> int:
    return _run_legacy("evaluate.py", [args.config, "--workers", str(args.workers)], args.suite)


def command_status(args: argparse.Namespace) -> int:
    return _run_legacy("status.py", [], args.suite)


def command_gold(args: argparse.Namespace) -> int:
    return _run_legacy("validate_gold.py", [], args.suite)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rebench", description="Manage reproducible SWE-rebench suites and runs")
    sub = parser.add_subparsers(dest="command", required=True)

    suite = sub.add_parser("suite", help="inspect and manage benchmark suites")
    suite_sub = suite.add_subparsers(dest="suite_command", required=True)
    suite_list = suite_sub.add_parser("list", help="list available suites")
    suite_list.set_defaults(func=command_suite_list)
    suite_show = suite_sub.add_parser("show", help="show a suite summary")
    suite_show.add_argument("suite", nargs="?", default=None)
    suite_show.add_argument("--tasks", action="store_true", help="list every task")
    suite_show.set_defaults(func=command_suite_show)
    suite_validate = suite_sub.add_parser("validate", help="validate suite structure")
    suite_validate.add_argument("suite", nargs="?", default=None)
    suite_validate.set_defaults(func=command_suite_validate)
    suite_copy = suite_sub.add_parser("copy", help="copy a suite as a starting point")
    suite_copy.add_argument("source")
    suite_copy.add_argument("name")
    suite_copy.add_argument("--force", action="store_true")
    suite_copy.set_defaults(func=command_suite_copy)
    suite_add = suite_sub.add_parser("add", help="add a dataset task to a suite")
    suite_add.add_argument("suite")
    suite_add.add_argument("instance_id")
    suite_add.add_argument("--difficulty", default=None)
    suite_add.set_defaults(func=command_suite_add)
    suite_remove = suite_sub.add_parser("remove", help="remove and renumber a suite task")
    suite_remove.add_argument("suite")
    suite_remove.add_argument("instance_id")
    suite_remove.set_defaults(func=command_suite_remove)

    doctor = sub.add_parser("doctor", help="check the local benchmark environment")
    doctor.add_argument("--suite", default=None)
    doctor.set_defaults(func=command_doctor)

    prepare = sub.add_parser("prepare", help="prepare task workspaces")
    prepare.add_argument("config")
    prepare.add_argument("start", type=int)
    prepare.add_argument("end", type=int)
    prepare.add_argument("--suite", default=None)
    prepare.add_argument("--force", action="store_true")
    prepare.set_defaults(func=command_prepare)

    collect = sub.add_parser("collect", help="collect agent patches")
    collect.add_argument("config")
    collect.add_argument("start", type=int, nargs="?", default=None)
    collect.add_argument("end", type=int, nargs="?", default=None)
    collect.add_argument("--suite", default=None)
    collect.set_defaults(func=command_collect)

    evaluate = sub.add_parser("evaluate", help="evaluate collected patches")
    evaluate.add_argument("config")
    evaluate.add_argument("--suite", default=None)
    evaluate.add_argument("--workers", type=int, default=2)
    evaluate.set_defaults(func=command_evaluate)

    status = sub.add_parser("status", help="show progress for all configurations")
    status.add_argument("--suite", default=None)
    status.set_defaults(func=command_status)

    gold = sub.add_parser("gold", help="validate a suite against gold patches")
    gold.add_argument("--suite", default=None)
    gold.set_defaults(func=command_gold)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.func(args)
    except SuiteError as exc:
        parser.exit(2, f"error: {exc}\n")
    raise SystemExit(result or 0)
