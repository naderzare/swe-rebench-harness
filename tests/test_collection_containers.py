import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect  # noqa: E402


class CollectionContainerTests(unittest.TestCase):
    def test_running_container_is_not_restarted(self):
        meta = {"container": "prepared"}
        with (
            patch.object(collect, "docker_container_state", return_value="running"),
            patch.object(collect, "run") as run,
        ):
            with collect.collection_container(meta, "config", 1) as container:
                self.assertEqual(container, "prepared")
        run.assert_not_called()

    def test_stopped_container_is_started_then_stopped(self):
        meta = {"container": "prepared"}
        with (
            patch.object(
                collect, "docker_container_state", side_effect=["exited", "running"]
            ),
            patch.object(collect, "run") as run,
        ):
            with collect.collection_container(meta, "config", 1) as container:
                self.assertEqual(container, "prepared")
        self.assertEqual(
            run.call_args_list,
            [
                call(["docker", "start", "prepared"]),
                call(["docker", "stop", "--time", "2", "prepared"], check=False),
            ],
        )

    def test_paused_container_is_unpaused_then_paused(self):
        meta = {"container": "prepared"}
        with (
            patch.object(collect, "docker_container_state", return_value="paused"),
            patch.object(collect, "run") as run,
        ):
            with collect.collection_container(meta, "config", 1) as container:
                self.assertEqual(container, "prepared")
        self.assertEqual(
            run.call_args_list,
            [
                call(["docker", "unpause", "prepared"]),
                call(["docker", "pause", "prepared"], check=False),
            ],
        )

    def test_missing_container_uses_temporary_container(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            meta = {
                "container": "missing",
                "workspace": str(workspace),
                "repo_dir": "project",
                "image_name": "example/image:tag",
            }
            with (
                patch.object(collect, "docker_container_state", return_value=None),
                patch.object(collect, "container_name", return_value="temporary"),
                patch.object(collect, "run") as run,
            ):
                with collect.collection_container(meta, "config", 1) as container:
                    self.assertEqual(container, "temporary")

            self.assertEqual(
                run.call_args_list[-1],
                call(["docker", "stop", "--time", "2", "temporary"], check=False),
            )
            docker_run = run.call_args_list[0].args[0]
            self.assertEqual(docker_run[:4], ["docker", "run", "-d", "--rm"])
            self.assertIn("example/image:tag", docker_run)


if __name__ == "__main__":
    unittest.main()
