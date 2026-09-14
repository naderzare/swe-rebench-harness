import argparse, json, shutil
from pathlib import Path
from datasets import load_dataset
from _common import *

WORKSPACE_PROMPT = Path(".rebench") / "task.md"


def build_prompt(problem_statement, container, repo_dir):
    return (
        "# Task\n\n"
        + problem_statement.rstrip()
        + "\n\n"
        + "Implement the requested fix directly in this repository.\n\n"
        + "Do not only analyze, explain, or report what should be changed. "
        + "Complete the implementation and leave the resulting code changes in the workspace.\n\n"
        + "You may read and run existing tests. You may create temporary tests or "
        + "diagnostic scripts under `.rebench/dev-tests/`; that directory is not included "
        + "in the submitted patch.\n\n"
        + "Do not leave changes in the repository's existing test files. If you modify "
        + "existing tests temporarily, restore those changes before finishing.\n\n"
        + "If you need to run Python, tests, builds, or other project commands, "
        + "use this Docker container:\n"
        + f"{container}\n\n"
        + f"Repository path inside Docker: /{repo_dir}\n\n"
        + "Command format:\n"
        + f'docker exec {container} bash -lc "cd /{repo_dir} && <COMMAND>"\n\n'
        + "Do not commit the changes. Leave the completed code changes in the workspace.\n"
    )


def install_workspace_prompt(workspace, prompt):
    tracked = subprocess.run(
        ["git", "-C", str(workspace), "ls-files", ".rebench"],
        text=True,
        capture_output=True,
        check=True,
    )
    if tracked.stdout.strip():
        raise RuntimeError("Repository already tracks the reserved .rebench path")

    exclude_path = workspace / ".git" / "info" / "exclude"
    if not exclude_path.is_file():
        raise RuntimeError(f"Missing Git exclude file: {exclude_path}")
    exclude_lines = exclude_path.read_text(encoding="utf-8").splitlines()
    if ".rebench/" not in exclude_lines:
        with exclude_path.open("a", encoding="utf-8", newline="\n") as handle:
            if exclude_path.stat().st_size:
                handle.write("\n")
            handle.write(".rebench/\n")

    prompt_path = workspace / WORKSPACE_PROMPT
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    (workspace / ".rebench" / "dev-tests").mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path

def write_task_files(row, suite_task):
    task_id = suite_task["instance_id"]
    out = TASKS_DIR / task_id
    out.mkdir(parents=True, exist_ok=True)

    row = dict(row)
    row["image_name"] = public_image_name(row["image_name"])

    # Full private benchmark row, useful for golden checks only.
    (out / "private_gold.json").write_text(
        json.dumps([row], indent=2, default=str), encoding="utf-8"
    )

    # Evaluation row: keep hidden tests, remove gold solution.
    eval_row = row.copy()
    eval_row["patch"] = ""
    (out / "eval.json").write_text(
        json.dumps([eval_row], indent=2, default=str), encoding="utf-8"
    )

    agent_row = {
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "base_commit": row["base_commit"],
        "language": row["language"],
        "difficulty": suite_task["difficulty"],
        "problem_statement": row["problem_statement"],
    }
    (out / "agent.json").write_text(
        json.dumps(agent_row, indent=2, default=str), encoding="utf-8"
    )
    (out / "problem.txt").write_text(row["problem_statement"], encoding="utf-8")

    metadata = {
        "task_number": suite_task["n"],
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "repo_dir": repo_dir(row["repo"]),
        "base_commit": row["base_commit"],
        "language": row["language"],
        "difficulty": suite_task["difficulty"],
        "image_name": row["image_name"],
    }
    (out / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", help="e.g. codex-default, codex-high, copilot-default")
    ap.add_argument("start", type=int, help="first task number, inclusive")
    ap.add_argument("end", type=int, help="last task number, inclusive")
    ap.add_argument("--force", action="store_true", help="replace existing run workspace/container")
    args = ap.parse_args()

    suite = load_suite()
    wanted = [t for t in suite["tasks"] if args.start <= t["n"] <= args.end]
    if not wanted:
        raise SystemExit("No tasks in that range.")

    config_dir = RUNS_DIR / args.config
    config_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = suite_fingerprint(suite)
    config_meta_path = config_dir / "config.json"
    config_meta = {
        "config": args.config,
        "suite_name": suite["name"],
        "suite_file": str(SUITE_PATH.resolve()),
        "suite_fingerprint": fingerprint,
        "dataset": suite["dataset"],
        "suite_total": len(suite["tasks"]),
    }
    if config_meta_path.exists():
        existing = json.loads(config_meta_path.read_text(encoding="utf-8"))
        if existing.get("suite_fingerprint") != fingerprint:
            raise SystemExit(
                f"Run config '{args.config}' belongs to suite "
                f"'{existing.get('suite_name', 'unknown')}'. Use a new config name "
                "when changing suites."
            )
    else:
        config_meta_path.write_text(
            json.dumps(config_meta, indent=2), encoding="utf-8"
        )

    print("Loading benchmark dataset once...")
    ds = load_dataset(suite["dataset"], split="train")
    rows = {r["instance_id"]: r for r in ds}

    for st in wanted:
        task_id = st["instance_id"]
        if task_id not in rows:
            raise RuntimeError(f"Task not found in dataset: {task_id}")

        meta = write_task_files(rows[task_id], st)
        image = meta["image_name"]
        rdir = meta["repo_dir"]

        run_dir = config_dir / f'{st["n"]:02d}-{task_id}'
        workspace = run_dir / "workspace"
        container = container_name(args.config, st["n"])

        if run_dir.exists() and not args.force:
            meta_path = run_dir / "run.json"
            if meta_path.is_file() and workspace.is_dir():
                existing = json.loads(meta_path.read_text(encoding="utf-8"))
                prompt = build_prompt(
                    rows[task_id]["problem_statement"],
                    existing["container"],
                    existing["repo_dir"],
                )
                prompt_path = install_workspace_prompt(workspace, prompt)
                (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                print(f"\nSKIP {st['n']:02d}: workspace already exists; refreshed {prompt_path}")
            else:
                print(f"\nSKIP {st['n']:02d}: {run_dir} already exists (use --force to replace)")
            continue

        if docker_container_exists(container):
            if not args.force:
                raise RuntimeError(f"Container already exists: {container}")
            run(["docker", "rm", "-f", container], check=False)

        if run_dir.exists():
            shutil.rmtree(run_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        print(f"\n=== Preparing task {st['n']:02d}: {task_id} ===")
        run(["docker", "pull", image])

        tmp = container_name(args.config, st["n"], purpose="extract")
        if docker_container_exists(tmp):
            run(["docker", "rm", "-f", tmp], check=False)

        run(["docker", "create", "--name", tmp, image])
        run(["docker", "cp", f"{tmp}:/{rdir}/.", str(workspace.resolve())])
        run(["docker", "rm", tmp])

        # Start isolated persistent container for the agent.
        run([
            "docker", "run", "-d",
            "--name", container,
            "--label", f"rebench.root={ROOT.resolve()}",
            "--label", f"rebench.config={args.config}",
            "--label", f"rebench.suite={suite['name']}",
            "--network", "none",
            "-v", f"{workspace.resolve()}:/{rdir}",
            "-w", f"/{rdir}",
            image,
            "sleep", "infinity",
        ])

        # Clean and verify repository inside Linux container.
        verify = (
            f"git config --global --add safe.directory /{rdir} && "
            f"cd /{rdir} && "
            f"git config core.filemode false && "
            f"git reset --hard {meta['base_commit']} >/dev/null && "
            f"git clean -fd >/dev/null && "
            f"test \"$(git rev-parse HEAD)\" = \"{meta['base_commit']}\" && "
            f"test -z \"$(git status --porcelain)\""
        )
        p = subprocess.run(
            ["docker", "exec", container, "bash", "-lc", verify],
            text=True,
            capture_output=True,
        )

        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr)
            raise RuntimeError(f"Workspace verification failed for {task_id}")

        prompt = build_prompt(rows[task_id]["problem_statement"], container, rdir)
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        workspace_prompt = install_workspace_prompt(workspace, prompt)

        run_meta = {
            **meta,
            "config": args.config,
            "suite_name": suite["name"],
            "suite_fingerprint": fingerprint,
            "container": container,
            "workspace": str(workspace.resolve()),
            "status": "prepared",
        }
        (run_dir / "run.json").write_text(
            json.dumps(run_meta, indent=2), encoding="utf-8"
        )

        print(f"Prepared: {run_dir}")
        print(f"Container: {container}")
        print(f"Prompt: {workspace_prompt}")

if __name__ == "__main__":
    main()
