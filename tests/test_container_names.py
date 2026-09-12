import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _common  # noqa: E402


class ContainerNameTests(unittest.TestCase):
    def test_default_name_is_checkout_scoped_and_deterministic(self):
        first = _common.container_name("codex-default", 1)
        second = _common.container_name("codex-default", 1)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("sr-swe-rebench-harness-"))
        self.assertTrue(first.endswith("-codex-default-01"))

    def test_namespace_can_be_overridden(self):
        with patch.dict(os.environ, {"REBENCH_NAMESPACE": "CI worker #2"}):
            self.assertEqual(
                _common.container_name("codex/default", 7),
                "sr-CI-worker-2-codex-default-07",
            )

    def test_long_names_stay_within_docker_limit(self):
        name = _common.container_name("configuration-" * 20, 12)
        self.assertLessEqual(len(name), 128)
        self.assertTrue(name.startswith("sr-"))


if __name__ == "__main__":
    unittest.main()
