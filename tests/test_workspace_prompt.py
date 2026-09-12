import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_runs import build_prompt, install_workspace_prompt  # noqa: E402


class WorkspacePromptTests(unittest.TestCase):
    def test_prompt_is_minimal_and_conditional(self):
        prompt = build_prompt("Fix the parser.", "task-container", "project")
        self.assertIn("Implement the requested fix directly", prompt)
        self.assertIn("If you need to run Python", prompt)
        self.assertNotIn("Run Python, test, build", prompt)
        self.assertNotIn("for collection", prompt)
        self.assertIn("Do not commit", prompt)

    def test_installed_prompt_is_ignored_by_git(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            prompt_path = install_workspace_prompt(workspace, "task text\n")

            self.assertEqual(prompt_path, workspace / ".rebench" / "task.md")
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), "task text\n")
            ignored = subprocess.run(
                ["git", "-C", str(workspace), "check-ignore", ".rebench/task.md"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(ignored.returncode, 0)
            status = subprocess.run(
                ["git", "-C", str(workspace), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout, "")


if __name__ == "__main__":
    unittest.main()
