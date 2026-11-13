"""Local, dependency-free control plane for J4. Never drives the game inside HTTP handlers.

Only explicit user POSTs start the existing CLI. A controller lock in tm.py protects the
single game instance, including commands launched from another terminal.
"""
from __future__ import annotations

import fcntl
import inspect
import json
import math
import os
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen

from .actions import make_codec
from .compare import compare_runs, trend
from .controller_guard import legacy_controller
from .reward import RewardConfig
from .training import validate_config

ROOT = pathlib.Path(__file__).resolve().parents[2]
ASSETS = pathlib.Path(__file__).with_name("webui_assets")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,110}\Z")


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _tail(path, count):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", errors="replace") as stream:
        lines = list(deque((s for s in stream if s.strip()), maxlen=count))
    result = []
    for index, line in enumerate(lines):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
            # A writer may still be appending its final line during this read.
    return result


def _positive_int(value, label, maximum=100_000_000):
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f"{label} doit être un entier entre 1 et {maximum}")
    return value


def _number(value, label, lower=0, upper=10):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower < value <= upper:
        raise ValueError(f"{label} doit être dans ]{lower}, {upper}]")
    return value


def _flag(value, label):
    if type(value) is not bool:
        raise ValueError(f"{label} doit être un booléen")
    return value


class ControlPlane:
    def __init__(self, root=ROOT):
        self.root = pathlib.Path(root)
        self.runs = self.root / "runs" / "j4"
        self.configs = self.root / "configs" / "training"
        self.secret = secrets.token_urlsafe(32)
        self.jobs = {}
        self.mutex = threading.RLock()

    def _name(self, name):
        if not isinstance(name, str) or not IDENT.fullmatch(name) or name in (".", ".."):
            raise ValueError("Identifiant invalide")
        return name

    def run(self, name):
        path = self.runs / self._name(name)
        if not (path / "config.json").is_file() and not (path / "status.json").is_file():
            raise ValueError("Run inconnu")
        return path

    def config(self, name):
        path = self.configs / (self._name(name) + ".json")
        if not path.is_file():
            raise ValueError("Configuration inconnue")
        return _json(path)

    def controller(self):
        path = self.runs / ".controller.lock"
        if not path.exists():
            return legacy_controller(self.root)
        with path.open("r+") as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                try:
                    file.seek(0)
                    return json.load(file)
                except (ValueError, OSError):
                    return {"command": "démarrage"}
            else:
                fcntl.flock(file, fcntl.LOCK_UN)
        return legacy_controller(self.root)

    def _job_state(self, kind):
        job = self.jobs.get(kind)
        if not job:
            return None
        proc, log, label = job
        return {"label": label, "pid": proc.pid, "running": proc.poll() is None,
                "returncode": proc.poll(), "log": str(log.relative_to(self.root))}

    def tensorboard_presence(self):
        try:
            with socket.create_connection(("127.0.0.1", 6006), timeout=0.3):
                pass
        except OSError:
            return "absent"
        try:
            with urlopen("http://127.0.0.1:6006/data/plugins_listing", timeout=0.5) as response:
                listing = json.load(response)
            return "tensorboard" if isinstance(listing, dict) and "scalars" in listing else "occupied"
        except (OSError, ValueError):
            return "occupied"

    def overview(self):
        with self.mutex:
            templates = []
            for path in sorted(self.configs.glob("*.json")):
                try:
                    cfg = _json(path)
                    templates.append({"id": path.stem, "name": cfg.get("name", path.stem),
                                      "description": cfg.get("description", ""),
                                      "codec": cfg.get("action_codec"), "reward": cfg.get("reward", {}),
                                      "budget": cfg.get("budget", {}).get("transitions")})
                except (ValueError, OSError):
                    continue
            runs = []
            if self.runs.exists():
                for path in self.runs.iterdir():
                    if path.is_dir() and (path / "status.json").is_file():
                        try:
                            s = _json(path / "status.json")
                            runs.append({"id": path.name, **s})
                        except (ValueError, OSError):
                            continue
            runs.sort(key=lambda x: x["id"], reverse=True)
            return {"templates": templates, "runs": runs, "controller": self.controller(),
                    "job": self._job_state("controller"), "dashboard": self._job_state("dashboard"),
                    "tensorboard_presence": self.tensorboard_presence()}

    def details(self, name):
        path = self.run(name)
        checkpoints = []
        ckdir = path / "checkpoints"
        if ckdir.is_dir():
            for p in ckdir.iterdir():
                if p.is_dir() and IDENT.fullmatch(p.name) and (p / "trainer_state.json").is_file():
                    try:
                        s = _json(p / "trainer_state.json")
                        checkpoints.append({"id": p.name, "timesteps": s.get("timesteps")})
                    except (ValueError, OSError):
                        pass
        checkpoints.sort(key=lambda c: (c["timesteps"] or 0, c["id"]), reverse=True)
        evals = []
        for p in (path / "evals").glob("*/eval_summary.json"):
            try:
                evals.append({"id": p.parent.name, **_json(p)})
            except (ValueError, OSError):
                pass
        evals.sort(key=lambda e: e["id"], reverse=True)
        try:
            series = trend(path) if len(_tail(path / "episodes.jsonl", 5)) == 5 else None
        except (ValueError, KeyError, OSError):
            series = None
        return {"id": name, "status": _json(path / "status.json"),
                "config": _json(path / "config.json"), "checkpoints": checkpoints,
                "episodes": _tail(path / "episodes.jsonl", 80),
                "incidents": _tail(path / "incidents.jsonl", 20), "evals": evals,
                "trend": series}

    def save_config(self, data):
        if not isinstance(data, dict):
            raise ValueError("Objet JSON attendu")
        name = self._name(data.get("id"))
        cfg = data.get("config")
        if not isinstance(cfg, dict):
            raise ValueError("Configuration JSON attendue")
        if not isinstance(cfg.get("budget"), dict) or not isinstance(cfg.get("sac"), dict):
            raise ValueError("budget et sac doivent être des objets JSON")
        # Validate before opening the file. Restrict references to known map profiles.
        validate_config(cfg)
        from stable_baselines3 import SAC
        supplied = {"policy", "env", "gamma", "policy_kwargs", "seed", "device",
                    "verbose", "tensorboard_log", "_init_setup_model", "self"}
        allowed = set(inspect.signature(SAC.__init__).parameters) - supplied
        allowed |= {"net_arch", "hybrid_critic", "hybrid_target_entropy"}
        unknown = set(cfg["sac"]) - allowed
        if unknown:
            raise ValueError(f"Paramètre SAC inconnu ou réservé : {', '.join(sorted(unknown))}")
        RewardConfig(**cfg.get("reward", {}))
        make_codec(cfg["action_codec"], int(cfg.get("action_ticks", 5)))
        if not isinstance(cfg.get("name"), str) or not IDENT.fullmatch(cfg["name"]):
            raise ValueError("config.name doit être un identifiant simple")
        map_path = cfg["map"]
        if not isinstance(map_path, str) or not re.fullmatch(r"configs/maps/[A-Za-z0-9_.-]+\.json", map_path):
            raise ValueError("Profil de map invalide")
        if not (self.root / map_path).is_file():
            raise ValueError("Profil de map absent")
        _number(cfg.get("speed", 1), "speed")
        _positive_int(cfg.get("action_ticks", 5), "action_ticks", 100)
        if cfg["budget"].get("cap_transitions") is not None:
            _positive_int(cfg["budget"]["cap_transitions"], "cap_transitions")
        _positive_int(cfg["seed"] + 1 if type(cfg["seed"]) is int and cfg["seed"] >= 0 else None,
                      "seed + 1")
        path = self.configs / (name + ".json")
        # x mode prevents accidental replacement of a template or prior experiment.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(cfg, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        return {"id": name}

    def _launch(self, kind, label, args):
        with self.mutex:
            if kind == "controller" and self.controller() is not None:
                raise ValueError("Jeu déjà contrôlé : arrêter la commande en cours avant de continuer")
            prior = self.jobs.get(kind)
            if prior and prior[0].poll() is None:
                raise ValueError("Commande déjà en cours")
            logdir = self.runs / ".webui-logs"
            logdir.mkdir(parents=True, exist_ok=True)
            log = logdir / f"{int(time.time())}-{secrets.token_hex(5)}.log"
            command = ([sys.executable, str(self.root / "scripts" / "tm.py"), *args]
                       if kind == "controller" else
                       [sys.executable, "-m", "tensorboard.main", "--logdir", str(self.runs),
                        "--port", "6006", "--host=127.0.0.1"])
            with log.open("w", encoding="utf-8") as output:
                proc = subprocess.Popen(command, cwd=self.root, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            self.jobs[kind] = (proc, log, label)
            return {"pid": proc.pid, "label": label, "log": str(log.relative_to(self.root))}

    def action(self, name, data):
        if not isinstance(data, dict):
            raise ValueError("Objet JSON attendu")
        if name == "train":
            template = self._name(data.get("config"))
            cfg = self.config(template)
            validate_config(cfg)
            run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + cfg["name"] + "-" + secrets.token_hex(3)
            args = ["train", "--config", str(self.configs / (template + ".json")), "--run-id", run_id]
            self._options(args, data, cfg)
            return {"run": run_id, **self._launch("controller", run_id, args)}
        if name == "resume":
            path = self.run(data.get("run"))
            if not (path / "checkpoints" / "latest.json").is_file():
                raise ValueError("Aucun checkpoint pour reprendre")
            args = ["resume", "--run", str(path)]
            cfg = _json(path / "config.json")["config"]
            self._options(args, data, cfg)
            return self._launch("controller", path.name, args)
        if name == "eval":
            path = self.run(data.get("run"))
            checkpoint = data.get("checkpoint", "latest")
            if checkpoint == "latest":
                if not (path / "checkpoints" / "latest.json").is_file():
                    raise ValueError("Aucun checkpoint disponible")
            elif not (isinstance(checkpoint, str) and IDENT.fullmatch(checkpoint)
                      and (path / "checkpoints" / checkpoint / "trainer_state.json").is_file()):
                raise ValueError("Checkpoint inconnu")
            episodes = _positive_int(data.get("episodes", 1), "episodes", 10000)
            first = _positive_int(data.get("first_episode", 900001), "first_episode")
            mode = data.get("mode", "realtime")
            if mode not in ("sync", "realtime"):
                raise ValueError("Mode inconnu")
            speed = _number(data.get("speed", 1), "speed")
            args = ["eval", "--run", str(path), "--checkpoint", checkpoint,
                    "--episodes", str(episodes), "--first-episode", str(first),
                    "--mode", mode, "--speed", str(speed)]
            for field, flag in (("trace", "--trace"), ("official_finish", "--official-finish")):
                if _flag(data.get(field, False), field):
                    args.append(flag)
            return self._launch("controller", f"Évaluation {path.name}", args)
        if name == "stop":
            path = self.run(data.get("run"))
            owner = self.controller()
            state = _json(path / "status.json")
            if state.get("phase") != "running" or owner is None or owner.get("pid") != state.get("pid"):
                raise ValueError("Ce run n'est pas entraîné actuellement")
            (path / "STOP").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
            return {"message": "Arrêt demandé ; sauvegarde à la fin de la transition"}
        if name == "trend":
            path = self.run(data.get("run"))
            slices = _positive_int(data.get("slices", 5), "slices", 50)
            return trend(path, slices=slices)
        if name == "compare":
            ids = data.get("runs")
            if not isinstance(ids, list) or not 2 <= len(ids) <= 20 or len(set(ids)) != len(ids):
                raise ValueError("Sélectionner 2 à 20 runs distincts")
            fraction = _number(data.get("last_fraction", 0.2), "last_fraction", upper=1)
            return compare_runs([self.run(i) for i in ids], last_fraction=fraction)
        if name == "dashboard":
            presence = self.tensorboard_presence()
            if presence == "tensorboard":
                return {"message": "TensorBoard déjà disponible sur 127.0.0.1:6006"}
            if presence == "occupied":
                raise ValueError("Le port 6006 est occupé par un autre service")
            return self._launch("dashboard", "TensorBoard · :6006", [])
        if name == "dashboard-stop":
            with self.mutex:
                job = self.jobs.get("dashboard")
                if not job or job[0].poll() is not None:
                    raise ValueError("TensorBoard n'est pas lancé par cette interface")
                job[0].terminate()
            return {"message": "Arrêt de TensorBoard demandé"}
        raise ValueError("Action inconnue")

    def _options(self, args, data, cfg):
        if data.get("speed") is not None:
            args.extend(("--speed", str(_number(data["speed"], "speed"))))
        if data.get("budget") is not None and data.get("until_stopped", False):
            raise ValueError("Choisir budget OU sans limite")
        if data.get("budget") is not None:
            budget = _positive_int(data["budget"], "budget")
            cap = cfg["budget"].get("cap_transitions")
            if cap is not None and budget > cap:
                raise ValueError(f"Budget {budget} supérieur au plafond {cap} de la configuration")
            args.extend(("--budget", str(budget)))
        if _flag(data.get("until_stopped", False), "until_stopped"):
            args.append("--until-stopped")
        if _flag(data.get("trace", False), "trace"):
            args.append("--trace")

    def log(self, kind):
        if kind not in ("controller", "dashboard"):
            raise ValueError("Journal inconnu")
        with self.mutex:
            job = self.jobs.get(kind)
            if not job:
                return {"lines": [], "running": False}
            proc, path, _ = job
            with path.open(encoding="utf-8", errors="replace") as stream:
                lines = list(deque(stream, maxlen=100))
            return {"lines": lines, "running": proc.poll() is None, "returncode": proc.poll()}


class Handler(BaseHTTPRequestHandler):
    server_version = "TrackManiaLocalUI/1"

    def _send(self, code, body, mime="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _host(self):
        host = self.headers.get("Host", "")
        return bool(re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?", host))

    def do_GET(self):
        if not self._host():
            return self._send(403, {"error": "Accès local uniquement"})
        path = urlsplit(self.path).path
        app = self.server.app
        try:
            if path == "/api/overview":
                return self._send(200, {"csrf": app.secret, **app.overview()})
            if path.startswith("/api/configs/"):
                return self._send(200, app.config(path.split("/")[-1]))
            if path.startswith("/api/runs/"):
                return self._send(200, app.details(path.split("/")[-1]))
            if path.startswith("/api/log/"):
                return self._send(200, app.log(path.split("/")[-1]))
            if path in ("/", "/index.html", "/style.css", "/app.js"):
                filename = "index.html" if path == "/" else path[1:]
                mime = {"index.html": "text/html", "style.css": "text/css", "app.js": "text/javascript"}[filename]
                return self._send(200, (ASSETS / filename).read_bytes(), mime + "; charset=utf-8")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return self._send(400, {"error": str(exc)})
        self._send(404, {"error": "Page inconnue"})

    def do_POST(self):
        if not self._host() or self.headers.get("X-CSRF-Token") != self.server.app.secret:
            return self._send(403, {"error": "Requête refusée"})
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            return self._send(415, {"error": "JSON attendu"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("Taille de requête invalide")
            data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            path = urlsplit(self.path).path
            if path == "/api/configs":
                result = self.server.app.save_config(data)
            elif path.startswith("/api/actions/"):
                result = self.server.app.action(path.split("/")[-1], data)
            else:
                return self._send(404, {"error": "Action inconnue"})
            self._send(200, result)
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, format, *args):
        # Keep HTTP requests out of training logs; unexpected failures still go to stderr.
        pass


def serve(port=8765, root=ROOT, open_browser=False):
    app = ControlPlane(root)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.app = app
    address = f"http://127.0.0.1:{httpd.server_port}"
    print(f"Interface locale : {address}", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Interface locale TrackMania RL (sans accès réseau externe)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="ouvrir le navigateur au démarrage")
    args = parser.parse_args()
    serve(args.port, open_browser=args.open)
