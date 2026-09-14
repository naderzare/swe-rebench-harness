import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect import is_test_like_path, official_test_paths, patch_paths  # noqa: E402


class CollectPolicyTests(unittest.TestCase):
    def test_patch_paths_reads_added_deleted_and_space_names(self):
        patch = """diff --git a/tests/old.py b/tests/new.py
--- a/tests/old.py
+++ b/tests/new.py
diff --git a/deleted_test.go b/deleted_test.go
--- a/deleted_test.go
+++ /dev/null
diff --git a/spec/file with spaces.js b/spec/file with spaces.js
--- a/spec/file with spaces.js
+++ b/spec/file with spaces.js
"""
        self.assertEqual(
            patch_paths(patch),
            {"tests/old.py", "tests/new.py", "deleted_test.go", "spec/file with spaces.js"},
        )

    def test_patch_paths_ignores_header_like_source_content(self):
        patch = """diff --git a/src/example.py b/src/example.py
--- a/src/example.py
+++ b/src/example.py
@@ -1 +1,2 @@
 value = 1
+++ not/a/patch/header.py
"""
        self.assertEqual(patch_paths(patch), {"src/example.py"})

    def test_patch_paths_reads_binary_patch_names(self):
        patch = """diff --git a/tests/fixture.bin b/tests/fixture.bin
index 1234567..7654321 100644
GIT binary patch
literal 1
abc
"""
        self.assertEqual(patch_paths(patch), {"tests/fixture.bin"})

    def test_official_paths_come_from_test_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            eval_path = Path(directory) / "eval.json"
            eval_path.write_text(
                json.dumps([{
                    "test_patch": "--- a/tests/parser_test.py\n+++ b/tests/parser_test.py\n"
                }]),
                encoding="utf-8",
            )
            self.assertEqual(official_test_paths(eval_path), {"tests/parser_test.py"})

    def test_test_like_names_are_warnings_not_the_protection_source(self):
        examples = [
            "tests/unit/parser.py",
            "src/parser_test.py",
            "pkg/parser_test.go",
            "ui/parser.spec.tsx",
            "features/parser.feature",
            "src/ParserTest.java",
        ]
        for path in examples:
            with self.subTest(path=path):
                self.assertTrue(is_test_like_path(path))
        self.assertFalse(is_test_like_path("src/parser.py"))


if __name__ == "__main__":
    unittest.main()
