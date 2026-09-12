from datasets import load_dataset
from pathlib import Path
import random
import json

DATASET = "PrimeIntellect/SWE-rebench-V2-Filtered-Verified"
SEED = 20260911

FAILED = {
    "raml-org__raml-java-parser-155",
    "rwjblue__ember-template-lint-134",
    "mageddo__dns-proxy-server-375",
}


def get_difficulty(meta):
    if isinstance(meta, str):
        meta = json.loads(meta)

    return meta.get("llm_metadata", {}).get("difficulty")


suite_path = Path("suite.json")
suite = json.loads(suite_path.read_text(encoding="utf-8"))

# Backup current suite.
Path("suite-hard20-before-replacements.json").write_text(
    json.dumps(suite, indent=2),
    encoding="utf-8",
)

ds = load_dataset(DATASET, split="train")

rows = []
for row in ds:
    if get_difficulty(row["meta"]) != "hard":
        continue
    rows.append(dict(row))

used_tasks = {x["instance_id"] for x in suite["tasks"]}
used_repos = {x["repo"] for x in suite["tasks"]}

by_language = {}

for row in rows:
    lang = row["language"].lower()

    if row["instance_id"] in used_tasks:
        continue

    if row["repo"] in used_repos:
        continue

    by_language.setdefault(lang, []).append(row)


rng = random.Random(SEED)

for pool in by_language.values():
    rng.shuffle(pool)


replacements = []

for task in suite["tasks"]:

    if task["instance_id"] not in FAILED:
        continue

    lang = task["language"].lower()

    if not by_language.get(lang):
        raise RuntimeError(
            f"No replacement available for language {lang}"
        )

    replacement = by_language[lang].pop()

    # Prevent later replacements from using same repo.
    used_repos.add(replacement["repo"])

    for language, pool in by_language.items():
        by_language[language] = [
            x for x in pool
            if x["repo"] != replacement["repo"]
        ]

    old = task["instance_id"]

    task["instance_id"] = replacement["instance_id"]
    task["repo"] = replacement["repo"]
    task["language"] = replacement["language"].lower()
    task["difficulty"] = "hard"

    replacements.append({
        "task_number": task["n"],
        "old": old,
        "new": replacement["instance_id"],
        "repo": replacement["repo"],
        "language": replacement["language"],
    })


suite_path.write_text(
    json.dumps(suite, indent=2),
    encoding="utf-8",
)

print("\nREPLACEMENTS")
print("=" * 80)

for r in replacements:
    print(
        f'{r["task_number"]:02d}: '
        f'{r["old"]} -> {r["new"]} '
        f'[{r["language"]}]'
    )

print("\nUpdated suite.json")