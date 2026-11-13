"""Local web UI tests. Fixtures are synthetic; no game is launched or controlled."""
import copy
import fcntl
import http.client
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from trackmania_rl import webui

CFG = {"name": "synthetic", "map": "configs/maps/test.json", "action_codec": "threshold_v1",
       "seed": 1, "speed": 1, "budget": {"transitions": 100, "cap_transitions": 200},
       "reward": {"progress_mode": "delta", "finish_bonus": 20}, "sac": {"batch_size": 32}}


class WebUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "configs/training").mkdir(parents=True)
        (self.root / "configs/maps").mkdir(parents=True)
        (self.root / "configs/maps/test.json").write_text("{}")
        (self.root / "configs/training/base.json").write_text(json.dumps(CFG))
        self.app = webui.ControlPlane(self.root)
        self.server = webui.ThreadingHTTPServer(("127.0.0.1", 0), webui.Handler)
        self.server.app = self.app
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self, method, path, data=None, token=True, host="127.0.0.1"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Host": host}
        if data is not None:
            headers["Content-Type"] = "application/json"
            if token:
                headers["X-CSRF-Token"] = self.app.secret
        conn.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response.status, json.loads(body) if path.startswith("/api/") else body

    def make_run(self, name="first"):
        run = self.app.runs / name
        run.mkdir(parents=True)
        (run / "config.json").write_text(json.dumps({"config": CFG}))
        (run / "status.json").write_text(json.dumps({"phase": "finished_budget", "pid": 123,
                                                    "timesteps": 100, "episodes": 1}))
        (run / "episodes.jsonl").write_text(json.dumps({"episode": 1, "progress_max": .1}) + "\n")
        (run / "checkpoints/00000100").mkdir(parents=True)
        (run / "checkpoints/00000100/trainer_state.json").write_text(json.dumps({"timesteps": 100}))
        (run / "checkpoints/latest.json").write_text(json.dumps({"dir": "checkpoints/00000100"}))
        return run

    def test_overview_and_run_details(self):
        run = self.make_run()
        (run / "evals/example").mkdir(parents=True)
        (run / "evals/example/eval_summary.json").write_text(json.dumps({"finishes": 0, "episodes": 1}))
        status, body = self.call("GET", "/api/overview")
        self.assertEqual(status, 200)
        self.assertEqual(body["runs"][0]["id"], "first")
        self.assertEqual(body["templates"][0]["id"], "base")
        status, body = self.call("GET", "/api/runs/first")
        self.assertEqual(status, 200)
        self.assertEqual(body["checkpoints"][0]["id"], "00000100")
        self.assertEqual(body["evals"][0]["id"], "example")
        self.assertEqual(len(body["episodes"]), 1)

    def test_security_and_non_destructive_configs(self):
        self.assertEqual(self.call("GET", "/api/overview", host="example.com")[0], 403)
        self.assertEqual(self.call("POST", "/api/actions/stop", {"run": "first"}, token=False)[0], 403)
        self.assertEqual(self.call("GET", "/api/runs/..%2fsecret")[0], 400)
        original = (self.root / "configs/training/base.json").read_bytes()
        custom = copy.deepcopy(CFG)
        custom["name"] = "custom"
        custom["reward"]["progress_scale"] = 65
        self.assertEqual(self.call("POST", "/api/configs", {"id": "custom", "config": custom})[0], 200)
        self.assertEqual(self.call("GET", "/api/configs/custom")[1]["reward"]["progress_scale"], 65)
        self.assertEqual(self.call("POST", "/api/configs", {"id": "custom", "config": custom})[0], 400)
        self.assertEqual((self.root / "configs/training/base.json").read_bytes(), original)
        invalid = copy.deepcopy(custom)
        invalid["reward"]["discount_per_second"] = 2
        self.assertEqual(self.call("POST", "/api/configs", {"id": "invalid", "config": invalid})[0], 400)
        self.assertFalse((self.root / "configs/training/invalid.json").exists())
        invalid["reward"].pop("discount_per_second")
        invalid["map"] = "../../outside.json"
        self.assertEqual(self.call("POST", "/api/configs", {"id": "invalid", "config": invalid})[0], 400)
        invalid["map"] = CFG["map"]
        invalid["sac"]["gamma"] = .99
        self.assertEqual(self.call("POST", "/api/configs", {"id": "invalid", "config": invalid})[0], 400)
        self.assertFalse((self.root / "configs/training/invalid.json").exists())

    def test_controller_guard_and_whitelisted_actions(self):
        self.make_run()
        launched = []
        def fake_launch(kind, label, args):
            launched.append((kind, label, args))
            return {"pid": 42}
        with patch.object(self.app, "_launch", side_effect=fake_launch):
            status, body = self.call("POST", "/api/actions/eval", {"run": "first", "episodes": 1,
                "checkpoint": "00000100", "mode": "realtime", "speed": 1})
            self.assertEqual(status, 200)
            self.assertIn("--checkpoint", launched[0][2])
            self.assertEqual(launched[0][2][launched[0][2].index("--episodes") + 1], "1")
            self.assertEqual(self.call("POST", "/api/actions/eval", {"run": "first", "checkpoint": "../../evil"})[0], 400)
            self.assertEqual(self.call("POST", "/api/actions/train", {"config": "base", "budget": 30})[0], 200)
            self.assertEqual(launched[-1][2][-2:], ["--budget", "30"])
            self.assertEqual(self.call("POST", "/api/actions/resume", {"run": "first", "until_stopped": True})[0], 200)
            self.assertEqual(launched[-1][2][-1], "--until-stopped")
            self.assertEqual(self.call("POST", "/api/actions/compare", {"runs": ["first", "../../etc"]})[0], 400)

    def test_stop_only_active_matching_run(self):
        run = self.make_run()
        self.assertEqual(self.call("POST", "/api/actions/stop", {"run": "first"})[0], 400)
        status = json.loads((run / "status.json").read_text())
        status.update(phase="running", pid=123)
        (run / "status.json").write_text(json.dumps(status))
        with patch.object(self.app, "controller", return_value={"pid": 999}):
            self.assertEqual(self.call("POST", "/api/actions/stop", {"run": "first"})[0], 400)
        with patch.object(self.app, "controller", return_value={"pid": 123}):
            self.assertEqual(self.call("POST", "/api/actions/stop", {"run": "first"})[0], 200)
        self.assertTrue((run / "STOP").exists())

    def test_trend_endpoint_on_synthetic_episodes(self):
        run = self.make_run()
        rows = [{"episode": i, "progress_max": i / 10, "return": float(i),
                 "timesteps": i * 10, "finish_ms": None,
                 "action_share": {"coast": .1, "gas": .7, "brake": .1, "gas_brake": .1},
                 "steer_abs_mean": .2} for i in range(1, 6)]
        (run / "episodes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        status, result = self.call("POST", "/api/actions/trend", {"run": "first", "slices": 5})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["slices"]), 5)
        self.assertEqual(result["slices"][-1]["timesteps_end"], 50)

    def test_existing_tensorboard_is_reused_not_stopped(self):
        with patch.object(self.app, "tensorboard_presence", return_value="tensorboard"):
            with patch.object(self.app, "_launch") as launch:
                status, body = self.call("POST", "/api/actions/dashboard", {})
                self.assertEqual(status, 200)
                self.assertIn("déjà disponible", body["message"])
                launch.assert_not_called()
            self.assertEqual(self.call("POST", "/api/actions/dashboard-stop", {})[0], 400)
        with patch.object(self.app, "tensorboard_presence", return_value="occupied"):
            self.assertEqual(self.call("POST", "/api/actions/dashboard", {})[0], 400)

    def test_cli_lock_blocks_second_controller(self):
        # No bridge connection: only check the cross-file-descriptor advisory lock.
        path = self.app.runs / ".controller.lock"
        path.parent.mkdir(parents=True)
        with path.open("a+") as owner, path.open("a+") as contender:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(owner, fcntl.LOCK_UN)
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(contender, fcntl.LOCK_UN)

    def test_subprocess_launch_and_log_are_real_but_synthetic(self):
        script = self.root / "scripts/tm.py"
        script.parent.mkdir()
        script.write_text("import sys\nprint('SYNTHETIC', *sys.argv[1:], flush=True)\n")
        result = self.app.action("train", {"config": "base", "budget": 30})
        job = self.app.jobs["controller"]
        self.assertEqual(job[0].wait(timeout=5), 0)
        lines = self.app.log("controller")["lines"]
        self.assertIn("SYNTHETIC train", "".join(lines))
        self.assertIn("--budget 30", "".join(lines))
        self.assertEqual(result["pid"], job[0].pid)

    def test_legacy_evaluation_process_without_status_is_detected(self):
        from trackmania_rl.controller_guard import legacy_controller
        script = self.root / "scripts/tm.py"
        script.parent.mkdir()
        script.write_text("import time\ntime.sleep(5)\n")
        process = subprocess.Popen([sys.executable, "scripts/tm.py", "eval"], cwd=self.root)
        try:
            self.assertEqual(legacy_controller(self.root)["command"], "eval")
            self.assertEqual(legacy_controller(self.root)["pid"], process.pid)
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_active_lock_rejects_new_controller(self):
        self.app.runs.mkdir(parents=True)
        path = self.app.runs / ".controller.lock"
        with path.open("w+") as lock:
            lock.write(json.dumps({"pid": 42, "command": "resume"}))
            lock.flush()
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            status, body = self.call("POST", "/api/actions/train", {"config": "base"})
            self.assertEqual(status, 400)
            self.assertIn("déjà contrôlé", body["error"])
            fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
