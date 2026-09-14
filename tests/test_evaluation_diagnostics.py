import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate  # noqa: E402


class EvaluationDiagnosticTests(unittest.TestCase):
    def test_compile_failure_is_explained(self):
        item = {"passed_match": False, "exit_code": 2}
        reason, excerpt = evaluate.failure_diagnostic(
            item,
            "FAIL project [build failed]\n./object_test.go:10: d.Strict undefined\n",
        )
        self.assertEqual(reason, "build_or_compile_failed")
        self.assertEqual(len(excerpt), 2)

    def test_success_has_no_failure_reason(self):
        reason, excerpt = evaluate.failure_diagnostic(
            {"passed_match": True, "exit_code": 1},
            "an unrelated package failed",
        )
        self.assertIsNone(reason)
        self.assertEqual(excerpt, [])

    def test_evaluator_error_is_preserved(self):
        reason, excerpt = evaluate.failure_diagnostic(
            {"passed_match": False, "error": "container image unavailable"}, ""
        )
        self.assertEqual(reason, "evaluator_error")
        self.assertEqual(excerpt, ["container image unavailable"])

    def test_evaluator_log_is_copied_into_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluator = root / "evaluator"
            run_dir = root / "run"
            (evaluator / "logs").mkdir(parents=True)
            run_dir.mkdir()
            (evaluator / "logs" / "task_log.txt").write_text(
                "compile failed\n", encoding="utf-8"
            )
            with patch.object(evaluate, "EVALUATOR_DIR", evaluator):
                name, text = evaluate.preserve_evaluation_log(
                    {"log_path": "logs/task_log.txt"}, run_dir
                )
            self.assertEqual(name, "evaluation.log")
            self.assertEqual(text, "compile failed\n")
            self.assertEqual(
                (run_dir / "evaluation.log").read_text(encoding="utf-8"),
                "compile failed\n",
            )


if __name__ == "__main__":
    unittest.main()
