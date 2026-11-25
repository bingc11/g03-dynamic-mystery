"""Serve the full API and production React build with an isolated playthrough DB."""

import argparse
from contextlib import contextmanager, nullcontext
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import dotenv_values

from local_demo import DialogueFixture


ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = "127.0.0.1"
BUILD = ROOT / "web" / "build"


def free_port():
    with socket.socket() as server:
        server.bind((LOOPBACK, 0))
        return server.getsockname()[1]


@contextmanager
def serve(handler, port):
    with ThreadingHTTPServer((LOOPBACK, port), handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join(timeout=5)


@contextmanager
def serve_api(data_dir, port, fixture_port, *, live=False):
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ") if key in os.environ}
    env.update(
        PYTHONUTF8="1",
        PYTHON_DOTENV_DISABLED="1",
        INFERENCE_SERVICE="ollama",
        MODEL="local-fixture",
        OLLAMA_URL=f"http://{LOOPBACK}:{fixture_port}",
        NPC_DECISION_MODE="mock",
        NPC_DB_PATH=str(data_dir / "npc.db"),
        DATABASE_URL=f"sqlite:///{data_dir / 'game.db'}",
    )
    if live:
        env.pop("PYTHON_DOTENV_DISABLED")
        env.update(INFERENCE_SERVICE="deepseek", NPC_DECISION_MODE="llm")
        for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
                    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
                    "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            if key in os.environ:
                env[key] = os.environ[key]
    log_path = data_dir / "fastapi.log"
    with log_path.open("ab") as log, subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(ROOT / "api"),
         "--host", LOOPBACK, "--port", str(port)],
        cwd=data_dir, env=env, stdout=log, stderr=subprocess.STDOUT,
    ) as app:
        try:
            for _ in range(160):
                if app.poll() is not None:
                    raise RuntimeError(f"FastAPI exited; see {log_path}")
                try:
                    with urlopen(f"http://{LOOPBACK}:{port}/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except URLError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"FastAPI did not become ready; see {log_path}")
            yield app.pid
        finally:
            if app.poll() is None:
                app.terminate()
                try:
                    app.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    app.kill()
                    app.wait(timeout=5)


class ProductionReact(SimpleHTTPRequestHandler):
    def do_GET(self):
        # BrowserRouter handles application paths; missing static files remain 404.
        if self.headers.get("Sec-Fetch-Dest") == "document" and not Path(self.translate_path(self.path)).exists():
            self.path = "/index.html"
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=10000)
    parser.add_argument("--web-port", type=int, default=5001)
    parser.add_argument("--live", action="store_true", help="Use the server's configured DeepSeek game runtime.")
    args = parser.parse_args()
    if not (BUILD / "index.html").is_file():
        parser.error("Run the React production build before starting this harness.")
    if args.live and not (os.environ.get("DEEPSEEK_API_KEY")
                          or dotenv_values(ROOT / "api" / ".env").get("DEEPSEEK_API_KEY")):
        parser.error("Set DEEPSEEK_API_KEY in the server environment or api/.env to use --live.")
    fixture = nullcontext(None) if args.live else serve(DialogueFixture, 0)
    with fixture as fixture_port:
        with serve_api(args.data_dir, args.api_port, fixture_port, live=args.live) as api_pid:
            with serve(partial(ProductionReact, directory=BUILD), args.web_port):
                mode = "DeepSeek" if args.live else "Mock"
                print(f"{mode} API PID {api_pid}: http://{LOOPBACK}:{args.api_port}", flush=True)
                print(f"Production browser: http://{LOOPBACK}:{args.web_port}/library", flush=True)
                print(f"NPC database: {args.data_dir.resolve() / 'npc.db'}", flush=True)
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    pass


if __name__ == "__main__":
    main()
