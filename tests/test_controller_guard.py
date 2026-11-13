"""SYNTHETIC /proc entries: the uv launcher does not itself control the game."""

import pathlib
import tempfile
import unittest

from trackmania_rl.controller_guard import _controller_process


class ControllerGuard(unittest.TestCase):
    def test_uv_parent_is_not_mistaken_for_its_python_eval_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            root = base / "repo"
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "tm.py").touch()
            proc = base / "proc"
            proc.mkdir()
            (proc / "cwd").symlink_to(root)
            (proc / "cmdline").write_bytes(b"uv\0run\0python\0scripts/tm.py\0eval\0")
            (base / "uv").touch()
            (proc / "exe").symlink_to(base / "uv")
            self.assertIsNone(_controller_process(root, proc))

            (proc / "exe").unlink()
            (base / "python3.13").touch()
            (proc / "exe").symlink_to(base / "python3.13")
            (proc / "cmdline").write_bytes(b"python\0scripts/tm.py\0eval\0")
            self.assertEqual(_controller_process(root, proc), "eval")
