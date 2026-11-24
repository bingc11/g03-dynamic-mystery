"""Start the original FastAPI app on loopback with an explicit local dialogue fixture."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


class DialogueFixture(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return
        self.rfile.read(int(self.headers["Content-Length"]))
        packet = json.dumps({"response": "【本机模拟对话】已收到询问。可以通过证物夹向人物出示材料。"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(packet)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=10000)
    args = parser.parse_args()
    stub = ThreadingHTTPServer(("127.0.0.1", 0), DialogueFixture)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA"
    }}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHON_DOTENV_DISABLED="1",
               INFERENCE_SERVICE="ollama", MODEL="local-fixture", OLLAMA_URL=f"http://127.0.0.1:{stub.server_port}")
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                        "--port", str(args.port)], check=True, cwd=ROOT / "api", env=env)
    finally:
        stub.shutdown()
        stub.server_close()


if __name__ == "__main__":
    main()
