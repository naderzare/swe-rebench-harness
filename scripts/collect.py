import argparse, json, subprocess
from pathlib import Path
from _common import *

def task_number_from_dir(run_dir):
    try:
        return int(run_dir.name.split("-", 1)[0])
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("start", type=int, nargs="?", default=None)
    ap.add_argument("end", type=int, nargs="?", default=None)
    args = ap.parse_args()

    if (args.start is None) != (args.end is None):
        raise SystemExit("Provide both start and end, or neither.")

    config_dir = RUNS_DIR / args.config
    if not config_dir.exists():
        raise SystemExit(f"No runs found for config: {args.config}")

    count = 0
    for run_dir in sorted(p for p in config_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        n = task_number_from_dir(run_dir)
        if args.start is not None and (n is None or not (args.start <= n <= args.end)):
            continue

        meta_path = run_dir / "run.json"
        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        container = meta["container"]
        rdir = meta["repo_dir"]

        if not docker_container_exists(container):
            print(f"SKIP {run_dir.name}: container not running/present")
            continue

        # Capture all modifications, including untracked files.
        cmd = f"cd /{rdir} && git add -A && git diff --cached --binary > /tmp/agent.patch"
        run(["docker", "exec", container, "bash", "-lc", cmd])
        run(["docker", "cp", f"{container}:/tmp/agent.patch", str((run_dir / "agent.patch").resolve())])

        # Record changed files and flag likely test-file modifications.
        p = subprocess.run(
            ["docker", "exec", container, "bash", "-lc",
             f"cd /{rdir} && git diff --cached --name-only"],
            text=True, capture_output=True, check=True
        )
        changed = [x.strip() for x in p.stdout.splitlines() if x.strip()]
        test_like = [
            x for x in changed
            if (
                x.startswith("test/") or x.startswith("tests/")
                or "/test/" in x or "/tests/" in x
                or x.endswith(".spec.ts") or x.endswith(".test.ts")
                or x.endswith("_test.py")
            )
        ]

        meta["changed_files"] = changed
        meta["test_file_changes"] = test_like
        meta["status"] = "collected"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        size = (run_dir / "agent.patch").stat().st_size
        print(f"{run_dir.name}: patch={size} bytes, changed={len(changed)}, test_files={len(test_like)}")
        if test_like:
            print("  WARNING test-file changes:", ", ".join(test_like))
        count += 1

    print(f"\nCollected {count} run(s).")

if __name__ == "__main__":
    main()
