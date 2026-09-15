import argparse, json, subprocess
from contextlib import contextmanager
from pathlib import Path
from _common import *


@contextmanager
def collection_container(meta, config, task_number, workspace_path=None):
    """Provide a running container while preserving its original state."""
    original = meta["container"]
    state = docker_container_state(original)

    if state == "running":
        print(f"  CONTAINER RUNNING: {original}")
        yield original
        return

    if state in {"created", "exited"}:
        print(f"  CONTAINER STARTED TEMPORARILY: {original} (was {state})")
        run(["docker", "start", original])
        try:
            if docker_container_state(original) != "running":
                raise RuntimeError(f"Container did not stay running: {original}")
            yield original
        finally:
            run(["docker", "stop", "--time", "2", original], check=False)
        return

    if state == "paused":
        print(f"  CONTAINER UNPAUSED TEMPORARILY: {original}")
        run(["docker", "unpause", original])
        try:
            yield original
        finally:
            run(["docker", "pause", original], check=False)
        return

    if state is not None:
        raise RuntimeError(
            f"Container {original} is in unsupported state '{state}'. "
            "Wait for Docker to finish changing its state, then collect again."
        )

    workspace = Path(workspace_path or meta["workspace"]).resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Run workspace is missing: {workspace}")

    temporary = container_name(config, task_number, purpose="collect")
    if docker_container_state(temporary) is not None:
        raise RuntimeError(
            f"Temporary collection container already exists: {temporary}. "
            "Another collection may be running."
        )

    rdir = meta["repo_dir"]
    print(f"  CONTAINER CREATED TEMPORARILY: {temporary} (original missing)")
    run([
        "docker", "run", "-d", "--rm",
        "--name", temporary,
        "--label", f"rebench.root={ROOT.resolve()}",
        "--label", f"rebench.config={config}",
        "--label", "rebench.purpose=collect",
        "--network", "none",
        "-v", f"{workspace}:/{rdir}",
        "-w", f"/{rdir}",
        meta["image_name"],
        "sleep", "infinity",
    ])
    try:
        run([
            "docker", "exec", temporary,
            "git", "config", "--global", "--add", "safe.directory", f"/{rdir}",
        ])
        yield temporary
    finally:
        run(["docker", "stop", "--time", "2", temporary], check=False)

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
    for run_dir in sorted(p for p in config_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        n = task_number_from_dir(run_dir)
        if args.start is not None and (n is None or not (args.start <= n <= args.end)):
            continue

        meta_path = run_dir / "run.json"
        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rdir = meta["repo_dir"]

        # Capture all modifications, including untracked files. The internal
        # workspace prompt must stay ignored and out of the submitted patch.
        cmd = (
            f"cd /{rdir} && "
            "if test -e .rebench/task.md && ! git check-ignore -q .rebench/task.md; "
            "then echo '.rebench/task.md is not ignored' >&2; exit 3; fi && "
            "git add -A && "
            "if git diff --cached --name-only | grep -q '^\\.rebench/'; "
            "then echo '.rebench content was staged' >&2; exit 4; fi && "
            "git diff --cached --binary > /tmp/agent.patch"
        )
        with collection_container(
            meta, args.config, meta["task_number"], run_dir / "workspace"
        ) as container:
            run(["docker", "exec", container, "bash", "-lc", cmd])
            run([
                "docker", "cp", f"{container}:/tmp/agent.patch",
                str((run_dir / "agent.patch").resolve()),
            ])

            # Record changed files before a temporary container is stopped.
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

        size = (run_dir / "agent.patch").stat().st_size
        meta["changed_files"] = changed
        meta["test_file_changes"] = test_like
        meta["status"] = "collected" if size else "no_changes"
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

    print(f"\nCollected {count} non-empty run(s); {empty} empty run(s).")

if __name__ == "__main__":
    main()
