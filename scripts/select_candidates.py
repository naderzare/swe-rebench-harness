from datasets import load_dataset
import pandas as pd
import json

DATASET = "PrimeIntellect/SWE-rebench-V2-Filtered-Verified"

LANGUAGES = [
    "python",
    "go",
    "js",
    "ts",
    "rust",
    "java",
    "kotlin",
    "php",
]

MINIMUM = {
    "easy": 2,
    "medium": 2,
    "hard": 1,
}

TASKS_PER_REPO = 10

EXCLUDE = {
    "aws-cloudformation__cfn-lint-3965",
}


def difficulty(meta):
    if isinstance(meta, str):
        meta = json.loads(meta)

    if not isinstance(meta, dict):
        return None

    return meta.get("llm_metadata", {}).get("difficulty")


def valid(window):
    if len(window) < TASKS_PER_REPO:
        return False

    counts = window["difficulty"].value_counts()

    return all(
        counts.get(level, 0) >= required
        for level, required in MINIMUM.items()
    )


def best_cluster(group):
    group = (
        group.sort_values("created_at")
        .reset_index(drop=True)
    )

    best = None

    for left in range(len(group)):
        for right in range(
            left + TASKS_PER_REPO - 1,
            len(group)
        ):
            window = group.iloc[left:right + 1]

            if not valid(window):
                continue

            span = (
                window["created_at"].max()
                - window["created_at"].min()
            )

            if best is None or span < best["span"]:
                best = {
                    "window": window.copy(),
                    "span": span,
                }

            # Any larger window from same left point
            # will have a larger/equal date span.
            break

    if best is None:
        return None

    window = best["window"]

    chosen_indexes = []

    # First guarantee 2 easy + 2 medium + 2 hard.
    for level, count in MINIMUM.items():
        rows = (
            window[window["difficulty"] == level]
            .sort_values("created_at")
            .head(count)
        )

        chosen_indexes.extend(rows.index.tolist())

    # Fill remaining 4 positions with tasks closest
    # in time from this already-small window.
    remaining = (
        window.drop(index=chosen_indexes)
        .sort_values("created_at")
    )

    needed = TASKS_PER_REPO - len(chosen_indexes)

    chosen_indexes.extend(
        remaining.head(needed).index.tolist()
    )

    selected = (
        window.loc[chosen_indexes]
        .sort_values("created_at")
        .reset_index(drop=True)
    )

    return selected


print("Loading dataset...")

ds = load_dataset(DATASET, split="train")
df = ds.to_pandas()

df["difficulty"] = df["meta"].apply(difficulty)

df["created_at"] = pd.to_datetime(
    df["created_at"],
    errors="coerce",
)

df["language"] = df["language"].str.lower()

df = df[
    df["language"].isin(LANGUAGES)
    & df["difficulty"].isin(["easy", "medium", "hard"])
    & (~df["instance_id"].isin(EXCLUDE))
    & df["created_at"].notna()
].copy()


all_results = {}

for language in LANGUAGES:

    print()
    print("=" * 100)
    print(f"BEST {language.upper()} REPOSITORIES")
    print("=" * 100)

    language_df = df[df["language"] == language]

    results = []

    for repo, group in language_df.groupby("repo"):

        selected = best_cluster(group)

        if selected is None:
            continue

        counts = selected["difficulty"].value_counts()

        span = (
            selected["created_at"].max()
            - selected["created_at"].min()
        )

        results.append({
            "repo": repo,
            "span_days": span.total_seconds() / 86400,
            "easy": int(counts.get("easy", 0)),
            "medium": int(counts.get("medium", 0)),
            "hard": int(counts.get("hard", 0)),
            "selected": selected,
        })

    results.sort(key=lambda x: x["span_days"])

    all_results[language] = results

    for rank, result in enumerate(results[:10], start=1):

        print()
        print(
            f"#{rank:02d} {result['repo']} "
            f"| span={result['span_days']:.1f} days "
            f"| E={result['easy']} "
            f"M={result['medium']} "
            f"H={result['hard']}"
        )

        for _, row in result["selected"].iterrows():
            print(
                f"    {row['difficulty']:6} "
                f"{str(row['created_at'])[:10]} "
                f"{row['instance_id']} "
                f"{row['base_commit'][:10]}"
            )


# Save all top candidates too.
rows = []

for language, results in all_results.items():

    for rank, result in enumerate(results[:10], start=1):

        for _, row in result["selected"].iterrows():

            rows.append({
                "language": language,
                "rank": rank,
                "repo": result["repo"],
                "span_days": result["span_days"],
                "difficulty": row["difficulty"],
                "created_at": row["created_at"],
                "instance_id": row["instance_id"],
                "base_commit": row["base_commit"],
                "image_name": row["image_name"],
            })


pd.DataFrame(rows).to_csv(
    "candidate_tasks.csv",
    index=False,
)

print()
print("Saved candidate_tasks.csv")