"""
A FAKE BACKEND THAT ONLY EXISTS TO ANSWER /health.

seed_demo.py decides whether to write by asking a running server which
datastore it is on. That decision is the thing worth testing, and testing it
against the real backend would mean either seeding real Firestore or not
testing it at all.

So this serves a /health of our choosing and swallows every other call. The
seeder can be pointed at it with CARTPILOT_SEED_BASE and run for real: if it
proceeds, it writes into this stub and nowhere else; if it refuses, that
refusal is a genuine execution rather than a reading of the source.

    python tests/stub_health_server.py <port> <datastore-value|->

A "-" means: reply to /health with no datastore key at all, which is what an
older backend would do.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DATASTORE = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            payload = {"status": "ok"}
            if DATASTORE is not None:
                payload["datastore"] = DATASTORE
            self._send(payload)
            return
        if self.path.startswith("/venues"):
            # Enough shape for the seeder's last step to finish, so that a
            # run which PROCEEDS exits 0 and a run which REFUSES exits 1.
            # Without this both exit 1 and the exit code proves nothing.
            self._send({"venues": [{"name": "stub", "available": True,
                                    "can_fulfil": True}],
                        "searchable": 1, "fulfillable": 1})
            return
        self._send({"stub": True, "path": self.path})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        # Shapes the seeder's steps expect, so a proceeding run gets far
        # enough to prove it really did proceed.
        self._send({"products": 6, "ok": True, "seeded": True, "id": "stub"})

    def log_message(self, *args):
        pass       # the seeder's own output is what is being read


if __name__ == "__main__":
    port = int(sys.argv[1])
    DATASTORE = None if sys.argv[2] == "-" else sys.argv[2]
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
