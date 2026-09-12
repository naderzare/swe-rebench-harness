import json
import unittest

from rebench.suites import load_suite, resolve_suite, suite_summary, validate_suite


class SuiteTests(unittest.TestCase):
    def test_hard20_is_valid(self):
        path, suite = load_suite("hard20")
        self.assertEqual(path, resolve_suite("hard20"))
        self.assertEqual(validate_suite(suite), [])
        self.assertEqual(suite_summary(suite)["tasks"], 20)
        self.assertEqual(suite_summary(suite)["repositories"], 20)

    def test_duplicate_task_is_rejected(self):
        task = {
            "n": 1,
            "instance_id": "owner__repo-1",
            "repo": "owner/repo",
            "language": "python",
            "difficulty": "hard",
        }
        duplicate = dict(task, n=2)
        suite = {
            "name": "bad-suite",
            "dataset": "example/dataset",
            "tasks": [task, duplicate],
        }
        errors = validate_suite(suite)
        self.assertTrue(any("duplicate instance_id" in error for error in errors))

    def test_repository_uniqueness_can_be_required(self):
        base = {
            "instance_id": "owner__repo-1",
            "repo": "owner/repo",
            "language": "python",
            "difficulty": "hard",
        }
        suite = {
            "name": "unique-repos",
            "dataset": "example/dataset",
            "constraints": {"unique_repositories": True},
            "tasks": [dict(base, n=1), dict(base, n=2, instance_id="owner__repo-2")],
        }
        self.assertTrue(any("duplicate repo" in error for error in validate_suite(suite)))

    def test_task_numbers_must_be_ordered_and_consecutive(self):
        suite = {
            "name": "bad-numbers",
            "dataset": "example/dataset",
            "tasks": [{
                "n": 2,
                "instance_id": "owner__repo-2",
                "repo": "owner/repo-2",
                "language": "go",
                "difficulty": "medium",
            }],
        }
        self.assertTrue(any("consecutive" in error for error in validate_suite(suite)))

    def test_suite_json_is_serializable(self):
        _, suite = load_suite("hard20")
        self.assertEqual(json.loads(json.dumps(suite))["name"], "rebench-hard20-v1")


if __name__ == "__main__":
    unittest.main()
