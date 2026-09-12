import argparse, json, subprocess, sys
from pathlib import Path
from _common import *

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    config_dir = RUNS_DIR / args.config
    if not config_dir.exists():
        raise SystemExit(f"No runs found for config: {args.config}")

    suite = load_suite()
    config_meta_path = config_dir / "config.json"
    if config_meta_path.exists():
        config_meta = json.loads(config_meta_path.read_text(encoding="utf-8"))
        if config_meta.get("suite_fingerprint") != suite_fingerprint(suite):
            raise SystemExit(
                f"Run config '{args.config}' was prepared for suite "
                f"'{config_meta.get('suite_name', 'unknown')}', not '{suite['name']}'."
            )

    eval_rows = []
    predictions = []
    run_dirs = []

    for run_dir in sorted(p for p in config_dir.iterdir() if p.is_dir()):
        patch_path = run_dir / "agent.patch"
        run_meta_path = run_dir / "run.json"
        if not patch_path.exists() or not run_meta_path.exists():
            continue

        patch = patch_path.read_text(encoding="utf-8")
        if not patch.strip():
            print(f"SKIP {run_dir.name}: empty patch")
            continue

        meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
        task_id = meta["instance_id"]

        eval_path = TASKS_DIR / task_id / "eval.json"
        if not eval_path.exists():
            raise RuntimeError(f"Missing eval.json for {task_id}")

        eval_rows.extend(json.loads(eval_path.read_text(encoding="utf-8")))
        predictions.append({"instance_id": task_id, "patch": patch})
        run_dirs.append(run_dir)

    if not predictions:
        raise SystemExit("No collected non-empty patches found.")

    out_dir = config_dir / "_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_json = out_dir / "completed_eval.json"
    pred_json = out_dir / "predictions.json"
    report_json = out_dir / "report.json"

    eval_json.write_text(json.dumps(eval_rows, indent=2, default=str), encoding="utf-8")
    pred_json.write_text(json.dumps(predictions, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(EVALUATOR_DIR / "scripts" / "eval.py"),
        "--json", str(eval_json.resolve()),
        "--patches", str(pred_json.resolve()),
        "--max-workers", str(args.workers),
        "--report-json", str(report_json.resolve()),
    ]

    print(f"Evaluating {len(predictions)} completed task(s)...")
    subprocess.run(cmd, cwd=str(EVALUATOR_DIR), check=True)

    report = json.loads(report_json.read_text(encoding="utf-8"))
    by_id = {x["instance_id"]: x for x in report["items"]}

    solved = 0
    rows = []
    print("\nRESULTS")
    print("-" * 90)
    for run_dir in run_dirs:
        meta_path = run_dir / "run.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        item = by_id.get(meta["instance_id"], {})
        ok = bool(item.get("passed_match"))
        solved += int(ok)

        result = {
            "instance_id": meta["instance_id"],
            "task_number": meta["task_number"],
            "difficulty": meta["difficulty"],
            "repo": meta["repo"],
            "resolved": ok,
            "exit_code": item.get("exit_code"),
            "from_fail_to_pass": item.get("from_fail_to_pass", []),
            "failed_from_pass_to_pass": item.get("failed_from_pass_to_pass", []),
            "error": item.get("error", ""),
            "test_file_changes": meta.get("test_file_changes", []),
        }
        (run_dir / "result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        rows.append(result)
        print(
            f'{meta["task_number"]:02d}  '
            f'{"PASS" if ok else "FAIL":4}  '
            f'{meta["difficulty"]:6}  '
            f'{meta["instance_id"]}'
        )

    summary = {
        "config": args.config,
        "suite_name": suite["name"],
        "suite_fingerprint": suite_fingerprint(suite),
        "completed": len(rows),
        "suite_total": len(suite["tasks"]),
        "solved": solved,
        "score": solved / len(rows) if rows else 0.0,
        "results": rows,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("-" * 90)
    print(f"Completed: {len(rows)}/{len(suite['tasks'])}")
    print(f"Solved:    {solved}/{len(rows)}")
    print(f"Score:     {100 * summary['score']:.1f}%")
    print(f"Summary:   {out_dir / 'summary.json'}")

if __name__ == "__main__":
    main()
