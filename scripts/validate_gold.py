from datasets import load_dataset
from pathlib import Path
import subprocess
import json
import sys

from _common import (
    ROOT,
    load_suite,
    public_image_name,
    EVALUATOR_DIR,
)

suite = load_suite()

print("Suite:", suite["name"])
print("Loading dataset...")

ds = load_dataset(
    suite["dataset"],
    split="train",
)

by_id = {
    row["instance_id"]: dict(row)
    for row in ds
}

rows = []

for task in suite["tasks"]:
    task_id = task["instance_id"]

    if task_id not in by_id:
        raise RuntimeError(
            f"Missing task: {task_id}"
        )

    row = by_id[task_id]

    row["image_name"] = public_image_name(
        row["image_name"]
    )

    rows.append(row)

out = ROOT / "gold_validation"
out.mkdir(exist_ok=True)

gold_json = out / "gold_tasks.json"
report_json = out / "gold_report.json"

gold_json.write_text(
    json.dumps(
        rows,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

print()
print(f"Gold-evaluating {len(rows)} tasks...")

cmd = [
    sys.executable,
    str(EVALUATOR_DIR / "scripts" / "eval.py"),

    "--json",
    str(gold_json.resolve()),

    "--golden-eval",

    "--max-workers",
    "2",

    "--report-json",
    str(report_json.resolve()),
]

subprocess.run(
    cmd,
    cwd=str(EVALUATOR_DIR),
    check=False,
)

report = json.loads(
    report_json.read_text(encoding="utf-8")
)

print()
print("=" * 80)
print("GOLD VALIDATION")
print("=" * 80)

for item in report["items"]:
    ok = item.get("passed_match", False)

    print(
        ("PASS" if ok else "FAIL"),
        item["instance_id"],
    )

print()
print(
    f"Overall: "
    f"{sum(x.get('passed_match', False) for x in report['items'])}"
    f"/{len(report['items'])}"
)

print("all_ok:", report["all_ok"])

if not report["all_ok"]:
    raise SystemExit(1)
