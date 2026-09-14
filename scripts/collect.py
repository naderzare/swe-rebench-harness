import argparse, ast, json, shlex, shutil, subprocess
from pathlib import Path
from _common import *


def patch_paths(patch_text):
    """Return every old/new path named by a unified Git patch."""
    paths = set()
    expecting_old_header = False
    expecting_new_header = False
    saw_diff_header = False

    def add_path(raw):
        raw = raw.split("\t", 1)[0].strip()
        if raw == "/dev/null":
            return
        if raw.startswith('"'):
            try:
                raw = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                pass
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        if raw:
            paths.add(raw.replace("\\", "/"))

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            saw_diff_header = True
            expecting_old_header = True
            expecting_new_header = False
            # These names are a fallback for binary patches, which have no
            # ---/+++ headers. Git separates the pair with the final " b/".
            names = line[len("diff --git "):]
            quoted_names = shlex.split(names)
            if len(quoted_names) == 2:
                add_path(quoted_names[0])
                add_path(quoted_names[1])
            else:
                separator = names.rfind(" b/")
                if separator != -1:
                    add_path(names[:separator])
                    add_path(names[separator + 1:])
            continue
        if (expecting_old_header or (not saw_diff_header and not paths)) and line.startswith("--- "):
            add_path(line[4:])
            expecting_old_header = False
            expecting_new_header = True
            continue
        if expecting_new_header and line.startswith("+++ "):
            add_path(line[4:])
            expecting_new_header = False
            continue
        if line.startswith("rename from ") or line.startswith("rename to "):
            add_path(line.split(" ", 2)[2])
    return paths


def official_test_paths(eval_path):
    """Read the exact paths the evaluator's hidden test patch will touch."""
    if not eval_path.is_file():
        raise RuntimeError(f"Missing evaluation data: {eval_path}")
    rows = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"Expected one evaluation row in {eval_path}")
    test_patch = rows[0].get("test_patch")
    if not isinstance(test_patch, str):
        raise RuntimeError(f"Missing test_patch in {eval_path}")
    return patch_paths(test_patch)


def is_test_like_path(path):
    """Conservatively flag common test names without treating them as authoritative."""
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    name = parts[-1]
    return (
        any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith((
            "_test.py", "_tests.py", "_test.go", "_test.rs",
            ".test.js", ".test.jsx", ".test.ts", ".test.tsx",
            ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
            "test.java", "tests.java", ".feature",
        ))
    )

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
    empty = 0
    conflicts = 0
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

        # Capture all modifications, including untracked files. The internal
        # workspace prompt must stay ignored and out of the submitted patch.
        cmd = (
            f"cd /{rdir} && "
            "if test -e .rebench/task.md && ! git check-ignore -q .rebench/task.md; "
            "then echo '.rebench/task.md is not ignored' >&2; exit 3; fi && "
            "git add -A && "
            "if git diff --cached --name-only | grep -q '^\\.rebench/'; "
            "then echo '.rebench content was staged' >&2; exit 4; fi && "
            "git diff --cached --binary > /tmp/agent-full.patch"
        )
        run(["docker", "exec", container, "bash", "-lc", cmd])
        full_patch_path = run_dir / "agent-full.patch"
        agent_patch_path = run_dir / "agent.patch"
        run(["docker", "cp", f"{container}:/tmp/agent-full.patch", str(full_patch_path.resolve())])

        # Record changed files and flag likely test-file modifications.
        p = subprocess.run(
            ["docker", "exec", container, "bash", "-lc",
             f"cd /{rdir} && git diff --cached --name-only -z"],
            capture_output=True, check=True
        )
        changed = [
            x.decode("utf-8", errors="surrogateescape").replace("\\", "/")
            for x in p.stdout.split(b"\0") if x
        ]
        test_like = [x for x in changed if is_test_like_path(x)]
        protected = official_test_paths(TASKS_DIR / meta["instance_id"] / "eval.json")
        submitted_paths = patch_paths(
            full_patch_path.read_bytes().decode("utf-8", errors="surrogateescape")
        )
        protected_conflicts = sorted(submitted_paths & protected)

        collection = {
            "instance_id": meta["instance_id"],
            "changed_files": changed,
            "test_like_files": test_like,
            "protected_test_files": sorted(protected),
            "protected_test_conflicts": protected_conflicts,
        }

        meta["changed_files"] = changed
        meta["test_file_changes"] = test_like
        meta["protected_test_files"] = sorted(protected)
        meta["protected_test_conflicts"] = protected_conflicts

        if protected_conflicts:
            if agent_patch_path.exists():
                agent_patch_path.unlink()
            result_path = run_dir / "result.json"
            if result_path.exists():
                result_path.unlink()
            meta["status"] = "test_conflict"
            collection["status"] = "test_conflict"
            (run_dir / "collection.json").write_text(
                json.dumps(collection, indent=2), encoding="utf-8"
            )
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(f"{run_dir.name}: ERROR - agent changed protected evaluator test files")
            print("  Conflicts:", ", ".join(protected_conflicts))
            print(f"  Full patch preserved at: {full_patch_path}")
            conflicts += 1
            continue

        shutil.copyfile(full_patch_path, agent_patch_path)
        full_patch_path.unlink()

        size = agent_patch_path.stat().st_size
        meta["status"] = "collected" if size else "no_changes"
        collection["status"] = meta["status"]
        (run_dir / "collection.json").write_text(
            json.dumps(collection, indent=2), encoding="utf-8"
        )
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        if not size:
            result_path = run_dir / "result.json"
            if result_path.exists():
                result_path.unlink()
            print(f"{run_dir.name}: EMPTY - no agent code changes found")
            empty += 1
            continue

        print(f"{run_dir.name}: patch={size} bytes, changed={len(changed)}, test_files={len(test_like)}")
        if test_like:
            print("  WARNING test-file changes:", ", ".join(test_like))
        count += 1

    print(
        f"\nCollected {count} non-empty run(s); {empty} empty run(s); "
        f"{conflicts} protected-test conflict(s)."
    )
    if conflicts:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
