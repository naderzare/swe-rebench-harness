import json
from pathlib import Path
from _common import *

def main():
    suite_total = len(load_suite()["tasks"])
    if not RUNS_DIR.exists():
        print("No runs directory yet.")
        return

    print(f"{'CONFIG':28} {'PREP':>5} {'PATCH':>5} {'EVAL':>5} {'SOLVED':>7} {'SCORE':>8}")
    print("-" * 66)

    for cfg in sorted(p for p in RUNS_DIR.iterdir() if p.is_dir()):
        run_dirs = [p for p in cfg.iterdir() if p.is_dir() and not p.name.startswith("_")]
        prep = sum((p / "run.json").exists() for p in run_dirs)
        patch = sum((p / "agent.patch").exists() and (p / "agent.patch").stat().st_size > 0 for p in run_dirs)
        results = []
        for p in run_dirs:
            rp = p / "result.json"
            if rp.exists():
                results.append(json.loads(rp.read_text(encoding="utf-8")))
        solved = sum(bool(r.get("resolved")) for r in results)
        score = f"{100*solved/len(results):.1f}%" if results else "-"
        print(f"{cfg.name:28} {prep:5d} {patch:5d} {len(results):5d} {solved:7d} {score:>8}")

    print(f"\nSuite total: {suite_total}")

if __name__ == "__main__":
    main()
