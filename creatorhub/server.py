"""REST API + static file server. Keeps the Notion token server-side (never exposed to the browser).

GET  /api/posts            all posts
GET  /api/analytics        engagement analytics, best posting hours, pipeline counts
POST /api/schedule         {"apply": bool} -> auto-schedule Ready posts (preview or write back)
POST /api/posts/<id>       {"status"?, "publish_at"?, "caption"?} -> update a post
POST /api/suggest/<id>     AI caption suggestion
"""
from __future__ import annotations

import json
import mimetypes
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .insights import analytics, auto_schedule, suggest_caption
from .notion import make_store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
ALLOWED_STATUS = {"Idea", "Drafting", "Ready", "Scheduled", "Published"}


def build_handler(store, mode: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = min(int(self.headers.get("Content-Length", 0)), 20_000)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            if self.path == "/api/posts":
                return self._json(200, {"mode": mode, "posts": store.list_posts()})
            if self.path == "/api/analytics":
                return self._json(200, analytics(store.list_posts()))
            # static files, confined to the web/ folder
            rel = "index.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0]
            target = (WEB / rel).resolve()
            if WEB not in target.parents and target != WEB / "index.html" or not target.is_file():
                return self._json(404, {"error": "not found"})
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            posts = store.list_posts()
            if self.path == "/api/schedule":
                plan = auto_schedule(posts, datetime.now().replace(minute=0, second=0, microsecond=0))
                if body.get("apply"):
                    for item in plan:
                        store.update_post(item["id"], {"status": "Scheduled", "publish_at": item["publish_at"]})
                return self._json(200, {"applied": bool(body.get("apply")), "plan": plan})
            if self.path.startswith("/api/suggest/"):
                post = next((p for p in posts if p["id"] == self.path.rsplit("/", 1)[1]), None)
                return self._json(200, suggest_caption(post, posts)) if post else self._json(404, {"error": "no such post"})
            if self.path.startswith("/api/posts/"):
                post_id = self.path.rsplit("/", 1)[1]
                if not any(p["id"] == post_id for p in posts):
                    return self._json(404, {"error": "no such post"})
                fields = {k: body[k] for k in ("status", "publish_at", "caption") if k in body}
                if "status" in fields and fields["status"] not in ALLOWED_STATUS:
                    return self._json(400, {"error": f"status must be one of {sorted(ALLOWED_STATUS)}"})
                store.update_post(post_id, fields)
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            pass

    return Handler


def main(port: int = 8000) -> None:
    store, mode = make_store(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", port), build_handler(store, mode))
    print(f"CreatorHub AI ({mode} mode) running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
