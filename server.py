"""Battlesnake 服务器：只用标准库，python server.py 就能跑。

端点：
  GET  /        返回蛇的外观配置
  POST /start   开局（回空 JSON 即可）
  POST /move    每回合要一个方向
  POST /end     结束

本地测试：http://127.0.0.1:8000
给官方平台用：需要公网 HTTPS 地址（cloudflared / 部署到云）
"""
import hashlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import choose_move

CORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core.py")
try:
    with open(CORE_PATH, "rb") as _fh:
        CORE_SHA = hashlib.sha256(_fh.read()).hexdigest()[:12]
except Exception:
    CORE_SHA = "unknown"

META = {
    "apiversion": "1",
    "author": "soft",
    "color": "#7C9CF5",
    "head": "default",
    "tail": "default",
    "version": "0.1.1",
}

MOVE_LIMIT_MS = 500.0

# 最近一次决策的快照，方便出事后回看「我到底看见了什么」
LAST = {}

# 调试用：打开后每步把收到的棋盘原样落到 last_move.json
DUMP = False
DUMP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_move.json")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode())
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", ""):
            self._send(META)
        elif path == "/diag":
            self._send({
                "version": META["version"],
                "core_sha": CORE_SHA,
                "move_limit_ms": MOVE_LIMIT_MS,
                "last": LAST,
            })
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        t0 = time.time()
        data = self._read_json()
        path = self.path.split("?")[0]

        if path in ("/start", "/end"):
            self._send({})
            return

        if path == "/move":
            if DUMP:
                try:
                    with open(DUMP_PATH, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False)
                except Exception:
                    pass
            board = data.get("board") or {}
            me = (data.get("you") or {}).get("name")
            try:
                move = choose_move(board, me)
            except Exception as e:                      # 绝不能因为异常被判负
                sys.stderr.write("choose_move failed: %r\n" % (e,))
                move = "up"
            if move not in ("up", "down", "left", "right"):
                move = "up"
            try:
                yb = (data.get("you") or {}).get("body") or []
                LAST.clear()
                LAST.update({
                    "turn": data.get("turn"),
                    "move": move,
                    "head": yb[0] if yb else None,
                    "tail": yb[-1] if yb else None,
                    "body_len": len(yb),
                    "food": sorted((f.get("x"), f.get("y")) for f in board.get("food", [])),
                })
            except Exception:
                pass
            ms = (time.time() - t0) * 1000.0
            if ms > MOVE_LIMIT_MS:
                sys.stderr.write("SLOW %.0fms\n" % ms)
            self._send({"move": move})
            return

        self._send({"error": "not found"}, 404)


def main():
    global DUMP
    port = int(os.environ.get("PORT", "8000"))
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif a == "--dump":
            DUMP = True
        elif a.isdigit():
            port = int(a)
    if os.environ.get("SNAKE_DUMP"):
        DUMP = True
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("battlesnake 在 http://127.0.0.1:%d   (Ctrl+C 停)" % port)
    print("  外观: %s" % json.dumps(META, ensure_ascii=False))
    print("  公网测试时把 cloudflared 给的地址填到 battlesnake 的 create game 里")
    sys.stdout.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
