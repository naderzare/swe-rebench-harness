from datasets import load_dataset
from pathlib import Path
import json

INSTANCE_ID = "aws-cloudformation__cfn-lint-3965"

FILTERED_DATASET = "PrimeIntellect/SWE-rebench-V2-Filtered-Verified"
FULL_DATASET = "PrimeIntellect/SWE-rebench-V2"

print("Loading Filtered Verified dataset...")

filtered = load_dataset(
    FILTERED_DATASET,
    split="train"
)

matches = [
    dict(row)
    for row in filtered
    if row["instance_id"] == INSTANCE_ID
]

if len(matches) != 1:
    raise RuntimeError(
        f"Expected exactly one filtered task for {INSTANCE_ID}, "
        f"found {len(matches)}"
    )

row = matches[0]

print("Found filtered task:")
print("  instance:", row["instance_id"])
print("  repo:", row["repo"])
print("  commit:", row["base_commit"])
print("  language:", row["language"])

meta = row.get("meta") or {}
difficulty = (
    meta.get("llm_metadata", {}).get("difficulty")
    if isinstance(meta, dict)
    else None
)

print("  difficulty:", difficulty)

#
# Filtered Verified rewrites image names for Prime infrastructure.
# Find the same instance in the full mirror, which preserves the
# original Docker Hub SWE-rebench V2 image name.
#
print()
print("Finding original Docker image...")

full = load_dataset(
    FULL_DATASET,
    split="train",
    streaming=True
)

source_row = None

for candidate in full:
    if candidate["instance_id"] == INSTANCE_ID:
        source_row = candidate
        break

if source_row is None:
    raise RuntimeError(
        f"Could not find {INSTANCE_ID} in full SWE-rebench-V2"
    )

row["image_name"] = source_row["image_name"]

print("  image:", row["image_name"])

repo_dir = row["repo"].split("/")[-1]

out = Path("tasks") / INSTANCE_ID
out.mkdir(parents=True, exist_ok=True)

#
# PRIVATE:
# Contains the benchmark's real solution.
# Never expose this to the agent.
#
(out / "private_gold.json").write_text(
    json.dumps([row], indent=2, default=str),
    encoding="utf-8"
)

#
# EVALUATOR:
# Contains hidden tests and expected results,
# but deliberately removes the gold solution.
#
eval_row = row.copy()
eval_row["patch"] = ""

(out / "eval.json").write_text(
    json.dumps([eval_row], indent=2, default=str),
    encoding="utf-8"
)

#
# AGENT:
# Safe metadata.
#
agent_row = {
    "instance_id": row["instance_id"],
    "repo": row["repo"],
    "base_commit": row["base_commit"],
    "language": row["language"],
    "difficulty": difficulty,
    "problem_statement": row["problem_statement"],
}

(out / "agent.json").write_text(
    json.dumps(agent_row, indent=2, default=str),
    encoding="utf-8"
)

(out / "problem.txt").write_text(
    row["problem_statement"],
    encoding="utf-8"
)

#
# Make PowerShell variables we can import easily.
#
vars_text = f'''$TASK = "{row["instance_id"]}"
$IMAGE = "{row["image_name"]}"
$REPO_DIR = "{repo_dir}"
$BASE_COMMIT = "{row["base_commit"]}"
'''

(out / "vars.ps1").write_text(
    vars_text,
    encoding="utf-8"
)

print()
print("Prepared successfully:")
print(" ", out)
print()
print("Files:")
print("  private_gold.json  <- NEVER give to agent")
print("  eval.json          <- NEVER give to agent")
print("  agent.json         <- safe")
print("  problem.txt        <- safe")
print("  vars.ps1")