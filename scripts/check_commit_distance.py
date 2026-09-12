import subprocess
from pathlib import Path

repos = {
    "Qiskit/qiskit-terra": {
        "path": Path("repos/qiskit-terra"),
        "commits": [
            "b35b18a90f",
            "35c4b00c7e",
            "c8a88e7d0c",
            "3fb8939728",
            "77588ff3d3",
            "0d48974a75",
            "6580d96879",
            "471e8b5cda",
            "3ce1737b2c",
            "b4268b9afb",
        ],
    },

    "dtolnay/cxx": {
        "path": Path("repos/cxx"),
        "commits": [
            "dd9e987fd6",
            "0cb4514cfb",
            "cd271f2dc8",
            "028d3d23f9",
            "8e5af76cf0",
            "b03d41d5d4",
            "d00bc40aa7",
            "30d46731ef",
            "7c969ce953",
            "ffa979bd18",
        ],
    },
"platers/obsidian-linter": {
    "path": Path("repos/obsidian-linter"),
    "commits": [
        "fe17d18f48",
        "4cb51de5d8",
        "fa9feaa80c",
        "38d6426cf7",
        "494d16406b",
        "8cc28e8ce9",
        "9c15812300",
        "6127b66afe",
        "deac3241c5",
        "8e0cb2ee77",
    ],
},
}


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args],
        text=True,
    ).strip()


for repo, info in repos.items():

    path = info["path"]
    commits = info["commits"]

    print()
    print("=" * 80)
    print(repo)
    print("=" * 80)

    # Resolve abbreviated commits.
    commits = [
        git(path, "rev-parse", commit)
        for commit in commits
    ]

    print("\nAdjacent task distances:")

    total = 0

    for a, b in zip(commits, commits[1:]):

        try:
            subprocess.check_call(
                [
                    "git", "-C", str(path),
                    "merge-base",
                    "--is-ancestor",
                    a, b,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            distance = int(
                git(path, "rev-list", "--count", f"{a}..{b}")
            )

            relation = "ancestor"

        except subprocess.CalledProcessError:

            merge_base = git(path, "merge-base", a, b)

            da = int(
                git(path, "rev-list", "--count", f"{merge_base}..{a}")
            )

            db = int(
                git(path, "rev-list", "--count", f"{merge_base}..{b}")
            )

            distance = da + db
            relation = "branched"

        total += distance

        print(
            f"{a[:10]} -> {b[:10]} : "
            f"{distance:4} commits ({relation})"
        )

    first = commits[0]
    last = commits[-1]

    merge_base = git(path, "merge-base", first, last)

    first_distance = int(
        git(path, "rev-list", "--count", f"{merge_base}..{first}")
    )

    last_distance = int(
        git(path, "rev-list", "--count", f"{merge_base}..{last}")
    )

    print()
    print("First -> last:")
    print(
        f"{first[:10]} -> {last[:10]} : "
        f"approximately {first_distance + last_distance} commits"
    )

    print("Sum of adjacent distances:", total)