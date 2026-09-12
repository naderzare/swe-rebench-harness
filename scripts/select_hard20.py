from datasets import load_dataset
from collections import defaultdict, Counter
from pathlib import Path
import pandas as pd
import random
import json

DATASET = "PrimeIntellect/SWE-rebench-V2-Filtered-Verified"

SEED = 20260911
TASK_COUNT = 20

# Use the 6 languages with the largest number of HARD tasks.
TOP_LANGUAGES = 6

# No language can dominate the benchmark.
MAX_PER_LANGUAGE = 4

# Things already exposed during our testing.
EXCLUDE_TASKS = {
    "aws-cloudformation__cfn-lint-3965",
    "qiskit__qiskit-terra-8741",
    "qiskit__qiskit-terra-8799",
    "qiskit__qiskit-terra-8983",
}

# To make the new benchmark particularly clean, also avoid repos
# we've already used/examined heavily.
EXCLUDE_REPOS = {
    "aws-cloudformation/cfn-lint",
    "Qiskit/qiskit-terra",
    "platers/obsidian-linter",
    "dtolnay/cxx",
}


def get_difficulty(meta):
    if isinstance(meta, str):
        meta = json.loads(meta)

    if not isinstance(meta, dict):
        return None

    return meta.get("llm_metadata", {}).get("difficulty")


print("Loading dataset...")

ds = load_dataset(DATASET, split="train")
df = ds.to_pandas()

df["difficulty"] = df["meta"].apply(get_difficulty)
df["language"] = df["language"].str.lower()

# HARD only.
df = df[
    (df["difficulty"] == "hard")
    & (~df["instance_id"].isin(EXCLUDE_TASKS))
    & (~df["repo"].isin(EXCLUDE_REPOS))
].copy()


print()
print("Hard tasks by language:")
counts = df["language"].value_counts()
print(counts)

languages = list(counts.head(TOP_LANGUAGES).index)

print()
print("Languages selected:")
for lang in languages:
    print(f"  {lang}: {counts[lang]} hard tasks")


#
# Deterministically shuffle every language independently.
#
rng = random.Random(SEED)

pools = {}

for lang in languages:
    rows = df[df["language"] == lang].to_dict("records")
    rng.shuffle(rows)
    pools[lang] = rows


selected = []
used_repos = set()
language_counts = Counter()


#
# Round-robin languages.
#
# Rules:
#   - hard only
#   - one task per repository
#   - max 4 tasks per language
#
while len(selected) < TASK_COUNT:

    made_progress = False

    for lang in languages:

        if len(selected) >= TASK_COUNT:
            break

        if language_counts[lang] >= MAX_PER_LANGUAGE:
            continue

        pool = pools[lang]

        while pool:

            row = pool.pop()

            if row["repo"] in used_repos:
                continue

            selected.append(row)
            used_repos.add(row["repo"])
            language_counts[lang] += 1

            made_progress = True
            break

    if not made_progress:
        raise RuntimeError(
            f"Could only find {len(selected)} tasks "
            "under the diversity constraints."
        )


print()
print("=" * 100)
print("REBENCH HARD-20 V1")
print("=" * 100)

output = []

for n, row in enumerate(selected, start=1):

    item = {
        "n": n,
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "language": row["language"],
        "difficulty": "hard",
        "base_commit": row["base_commit"],
        "created_at": str(row["created_at"]),
        "image_name": row["image_name"],
    }

    output.append(item)

    print(
        f"{n:02d} "
        f"{row['language']:8} "
        f"{row['repo']:40} "
        f"{row['instance_id']}"
    )


print()
print("Language distribution:")

for lang, count in language_counts.items():
    print(f"  {lang}: {count}")

print()
print("Repositories:", len(used_repos))


Path("hard20_candidates.json").write_text(
    json.dumps(output, indent=2, default=str),
    encoding="utf-8",
)

pd.DataFrame(output).to_csv(
    "hard20_candidates.csv",
    index=False,
)

print()
print("Saved:")
print("  hard20_candidates.json")
print("  hard20_candidates.csv")