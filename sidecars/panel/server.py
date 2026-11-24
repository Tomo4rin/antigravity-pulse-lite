#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""星轨猫猫仪表盘 Sidecar HTTP 服务（纯 Python 标准库，仅监听 127.0.0.1）。"""

import sys

sys.dont_write_bytecode = True

import json
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from collector import PulseCollector

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"
AVATARS_DIR = HERE / "avatars"
COLLECTOR = PulseCollector()


class PanelHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 静默处理访问日志，不产生日志刷屏
        return

    def _send_bytes(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            body = INDEX_HTML.read_bytes()
            self._send_bytes(200, "text/html; charset=utf-8", body)
            return

        if path in ("/avatars/happy.png", "/avatars/curious.png", "/avatars/sleepy.png", "/avatars/smug.jpg"):
            target = AVATARS_DIR / Path(path).name
            if target.is_file():
                ctype = "image/jpeg" if target.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                self._send_bytes(200, ctype, target.read_bytes())
                return

        if path == "/preload.js":
            self._send_bytes(200, "application/javascript; charset=utf-8", b"// sidecar preload stub\n")
            return

        if path == "/health":
            self._send_bytes(200, "application/json; charset=utf-8", b'{"ok":true}')
            return

        if path == "/api/metrics":
            qs = parse_qs(parsed.query)
            force = qs.get("force", ["0"])[0] in ("1", "true")
            cid = (qs.get("conversationId", [""])[0] or "").strip() or None
            data = COLLECTOR.snapshot(force_quota=force, conversation_id=cid)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send_bytes(200, "application/json; charset=utf-8", body)
            return

        self._send_bytes(404, "text/plain; charset=utf-8", b"Not Found")


def main():
    port = int(os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT") or os.environ.get("AG_PULSE_LITE_PORT") or "17892")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), PanelHandler)

    def _shutdown(_signum, _frame):
        httpd.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    print(f"星轨猫猫仪表盘已启动: http://127.0.0.1:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
