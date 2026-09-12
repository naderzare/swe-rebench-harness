import tempfile
import unittest
from pathlib import Path

from rebench.selection import (
    filter_candidates,
    load_selector,
    select_balanced,
    select_random,
    validate_selection,
)
from rebench.suites import SuiteError


def candidates():
    return [
        {
            "instance_id": f"task-{number}",
            "repo": f"owner/repo-{number}",
            "language": language,
            "difficulty": "hard" if number != 6 else "medium",
            "created_at": f"2026-01-{number:02d}",
        }
        for number, language in enumerate(
            ["python", "go", "python", "go", "rust", "rust"], start=1
        )
    ]


class SelectionTests(unittest.TestCase):
    def test_common_filters(self):
        result = filter_candidates(
            candidates(),
            difficulty="hard",
            languages=["python", "rust"],
            excluded_tasks={"task-1"},
            excluded_repos={"owner/repo-5"},
        )
        self.assertEqual([item["instance_id"] for item in result], ["task-3"])

    def test_balanced_selection_is_reproducible(self):
        pool = filter_candidates(candidates(), difficulty="hard", languages=None)
        options = {
            "languages": ["python", "go", "rust"],
            "unique_repositories": True,
            "max_per_language": None,
        }
        first = select_balanced(pool, count=3, seed=42, options=options)
        second = select_balanced(pool, count=3, seed=42, options=options)
        self.assertEqual(first, second)
        self.assertEqual({item["language"] for item in first}, {"python", "go", "rust"})

    def test_random_selection_honors_limit(self):
        pool = filter_candidates(candidates(), difficulty="hard", languages=None)
        result = select_random(
            pool,
            count=3,
            seed=7,
            options={"unique_repositories": True, "max_per_language": 1},
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(len({item["language"] for item in result}), 3)

    def test_selection_requires_exact_count(self):
        pool = candidates()
        with self.assertRaisesRegex(SuiteError, "expected exactly 2"):
            validate_selection(
                pool[:1],
                pool,
                count=2,
                unique_repositories=False,
                max_per_language=None,
            )

    def test_custom_selector_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.py"
            path.write_text(
                "def select_tasks(candidates, *, count, seed, options):\n"
                "    return list(reversed(candidates))[:count]\n",
                encoding="utf-8",
            )
            selector = load_selector(path)
            result = selector(candidates(), count=2, seed=0, options={})
            self.assertEqual([item["instance_id"] for item in result], ["task-6", "task-5"])


if __name__ == "__main__":
    unittest.main()
