"""三种对手接入方式：

  py:<文件路径>                  import 该文件，调 choosemove(board, me_name)
  http:<引擎地址>                Battlesnake 协议 POST /move（500ms 超时）
  replay:<回放 json 或 game_id>:<蛇名>
                                 把官方 arena 回放里这条蛇的每回合动作逐帧重放

回放数据源：https://arena.battlesnake.com/api/games/<game_id>/frames?offset=N
（每页 100 帧，翻到不满 100 帧为止）
"""
import hashlib
import http.client
import importlib.util
import inspect
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

from . import SNAKE_DIR, arena

DIRS = arena.DIRS
ARENA_API = "https://arena.battlesnake.com/api"
FRAME_PAGE = 100
MOVE_ATTRS = ("choosemove", "choose_move", "move", "next_move")


# ---------------------------------------------------------------- 工具

def _pts(body):
    out = []
    for p in body or []:
        if isinstance(p, dict):
            out.append((p.get("x", p.get("X")), p.get("y", p.get("Y"))))
        else:
            out.append((p[0], p[1]))
    return out


def _dir_of(a, b):
    for d, (dx, dy) in DIRS.items():
        if (a[0] + dx, a[1] + dy) == b:
            return d
    return None


def ok(move, ms=0.0):
    return {"move": move, "ms": ms, "error": None, "status": None}


def err(reason, ms=0.0, status=None):
    return {"move": None, "ms": ms, "error": reason, "status": status}


def resolve_py_path(path):
    """兼容 py:..\\core.py 这种相对写法（相对 cwd / snake/ / 文件名兜底）。"""
    cands = [path]
    if not os.path.isabs(path):
        cands += [
            os.path.join(SNAKE_DIR, path),
            os.path.join(SNAKE_DIR, os.path.basename(path)),
            os.path.join(os.getcwd(), path),
        ]
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    raise SystemExit("找不到 py 对手文件：%s" % path)


def _load_module(path):
    path = os.path.abspath(path)
    name = "duel_py_" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("无法 import：%s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- py:

class PyPlayer:
    """本地 python 蛇。决策逻辑原样 import，不复制。"""
    scripted = False
    kind = "py"
    # 本地 python 蛇没有网络开销，预算就按 --step-ms 算
    budget_ms = 0.0

    def __init__(self, path):
        self.path = resolve_py_path(path)
        self.label = os.path.basename(self.path)
        mod = _load_module(self.path)
        self.fn = None
        for attr in MOVE_ATTRS:
            fn = getattr(mod, attr, None)
            if callable(fn):
                self.fn = fn
                break
        if self.fn is None:
            raise SystemExit("%s 里没有 choosemove / choose_move 函数" % self.path)
        # 兼容两种签名：choose_move(board, me) 和 Battlesnake 式 choose_move(payload)
        self.one_arg = self._has_one_arg()

    def _has_one_arg(self):
        try:
            ps = list(inspect.signature(self.fn).parameters.values())
        except (TypeError, ValueError):
            return False
        if any(p.kind == p.VAR_POSITIONAL for p in ps):
            return False
        pos = [p for p in ps if p.kind in (p.POSITIONAL_ONLY,
                                           p.POSITIONAL_OR_KEYWORD)]
        return len(pos) == 1

    def move(self, api, name, turn=0):
        t0 = time.perf_counter()
        try:
            if self.one_arg:
                you = None
                for s in api.get("snakes", []):
                    if s.get("name") == name:
                        you = s
                        break
                mv = self.fn({"board": api, "you": you})
                if isinstance(mv, dict):
                    mv = mv.get("move")
            else:
                mv = self.fn(api, name)
        except Exception as e:                      # 决策炸了不能拖垮整局
            return err("py_error:%s: %s" % (type(e).__name__, e),
                       (time.perf_counter() - t0) * 1000.0)
        ms = (time.perf_counter() - t0) * 1000.0
        if mv not in DIRS:
            return err("py_bad_move:%r" % (mv,), ms)
        return ok(mv, ms)


# ---------------------------------------------------------------- http:

class HttpPlayer:
    """线上 Battlesnake 引擎，POST /move（保持长连接，省掉每次握手的往返）。"""
    scripted = False
    kind = "http"
    # Battlesnake 协议本身给 500ms，--step-ms 调得更小时不能反过来罚它
    budget_ms = 500.0

    def __init__(self, url, step_ms=50.0):
        self.raw = url
        u = url if "://" in url else "https://" + url
        scheme, _, rest = u.partition("://")
        hostport, _, path = rest.partition("/")
        path = "/" + path
        if not path.rstrip("/").endswith("/move"):
            path = path.rstrip("/") + "/move"
        host, _, port = hostport.partition(":")
        self.scheme = scheme.lower()
        self.host = host
        self.port = int(port) if port else (443 if self.scheme == "https" else 80)
        self.path = path
        # 协议本身给 500ms；step-ms 更大时按更宽的那个算
        self.timeout = max(float(step_ms), 500.0) / 1000.0
        self.conn = None
        self.label = "http:" + hostport

    def _conn(self):
        if self.conn is None:
            cls = (http.client.HTTPSConnection if self.scheme == "https"
                   else http.client.HTTPConnection)
            self.conn = cls(self.host, self.port, timeout=self.timeout)
        return self.conn

    def _drop(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def move(self, api, name, turn=0):
        you = None
        for s in api.get("snakes", []):
            if s.get("name") == name:
                you = s
                break
        payload = json.dumps({"board": api, "you": you}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        t0 = time.perf_counter()
        last = None
        for _ in (0, 1):            # 长连接可能被对端关掉，重连一次再放弃
            conn = self._conn()
            try:
                conn.request("POST", self.path, body=payload, headers=headers)
                resp = conn.getresponse()
                status, raw = resp.status, resp.read()
            except (socket.timeout, TimeoutError):
                self._drop()
                return err("http_timeout", (time.perf_counter() - t0) * 1000.0)
            except (http.client.HTTPException, OSError) as e:
                self._drop()
                last = e
                continue
            ms = (time.perf_counter() - t0) * 1000.0
            if status != 200:
                return err("http_status:%s" % status, ms, status)
            try:
                obj = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return err("http_bad_json", ms, status)
            mv = obj.get("move") if isinstance(obj, dict) else None
            if mv not in DIRS:
                return err("http_bad_move:%r" % (mv,), ms, status)
            return ok(mv, ms)
        return err("http_net:%s" % (last,), (time.perf_counter() - t0) * 1000.0)


# ---------------------------------------------------------------- replay:

def _norm_snake(s):
    death = s.get("Death", s.get("death"))
    return {
        "body": _pts(s.get("Body") or s.get("body") or []),
        "health": s.get("Health", s.get("health", 100)),
        "death": death.get("Cause") if isinstance(death, dict) else death,
        "death_turn": death.get("Turn") if isinstance(death, dict) else None,
        "status": s.get("StatusCode", s.get("status")),
    }


def _norm_frame(f):
    snakes = {}
    raw = f.get("Snakes") or f.get("snakes") or []
    if isinstance(raw, dict):
        for name, s in raw.items():
            ss = _norm_snake(s)
            ss["name"] = name
            snakes[name] = ss
    else:
        for s in raw:
            ss = _norm_snake(s)
            ss["name"] = s.get("Name", s.get("name"))
            snakes[ss["name"]] = ss
    food = _pts(f.get("Food") or f.get("food") or [])
    return {"turn": int(f.get("Turn", f.get("turn", 0))), "food": food, "snakes": snakes}


def _fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _fetch_game(game_id):
    """按 game_id 拉全部帧 + 棋盘尺寸。"""
    meta = _fetch_json("%s/games/%s" % (ARENA_API, game_id))
    game = meta.get("Game", meta.get("game", meta)) if isinstance(meta, dict) else {}
    frames = []
    offset = 0
    while True:
        data = _fetch_json("%s/games/%s/frames?offset=%d" % (ARENA_API, game_id, offset))
        page = data.get("Frames") or data.get("frames") or []
        frames.extend(page)
        if len(page) < FRAME_PAGE:
            break
        offset += FRAME_PAGE
        if offset > 100000:
            break
    return frames, game


def load_replay(source):
    """source = 本地 json 路径 / game_id / 完整 URL。"""
    if source.startswith(("http://", "https://")):
        data = _fetch_json(source)
        raw, game = None, {}
        meta = {"url": source}
    elif os.path.isfile(source):
        with open(source, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        raw, game = None, {}
        meta = {"path": os.path.abspath(source)}
    else:
        raw, game = _fetch_game(source)
        data = None
        meta = {"id": source}

    if data is None:                    # game_id 分支：帧已拿到
        pass
    elif isinstance(data, list):
        raw, game = data, {}
    elif "Frames" in data or "frames" in data:
        raw, game = (data.get("Frames") or data.get("frames")), (data.get("Game") or data.get("game") or {})
    elif "LastFrame" in data:
        raise SystemExit(
            "这份 json 只有 LastFrame、没有逐帧 Frames，重放不了：%s\n"
            "请用 game_id（会自动拉全部帧），或先访问 "
            "https://arena.battlesnake.com/api/games/<id>/frames" % source
        )
    else:
        raise SystemExit("认不出这份回放 json 的结构：%s" % source)

    frames = [_norm_frame(f) for f in raw]
    if len(frames) < 2:
        raise SystemExit("回放帧数不足（%d 帧），至少要 2 帧才能推出走法" % len(frames))
    frames.sort(key=lambda f: f["turn"])
    width = game.get("Width") or game.get("width")
    height = game.get("Height") or game.get("height")
    if not width or not height:
        width = max([p[0] for f in frames for p in f["food"]] +
                    [p[0] for f in frames for s in f["snakes"].values() for p in s["body"]]) + 1
        height = max([p[1] for f in frames for p in f["food"]] +
                     [p[1] for f in frames for s in f["snakes"].values() for p in s["body"]]) + 1
    meta.update({"game": game, "width": int(width), "height": int(height)})
    return {"frames": frames, "width": int(width), "height": int(height),
            "game": game, "meta": meta}


def replay_names(replay):
    return list(replay["frames"][0]["snakes"].keys())


def replay_initial_board(replay, replay_name, opp_name):
    """用回放第 0 帧当棋盘：陪练蛇保留原位，另一条由我们的蛇顶替。"""
    frames = replay["frames"]
    names = replay_names(replay)
    if replay_name not in names:
        raise SystemExit("回放里没有叫 %r 的蛇，只有：%s" % (replay_name, ", ".join(names)))
    others = [n for n in names if n != replay_name]
    if not others:
        raise SystemExit("回放里只有 %r 一条蛇，没法当对手（需要至少 2 条）" % replay_name)
    other = others[0]
    f0 = frames[0]
    snakes = []
    # 先放我们的蛇（A），再放回放蛇 —— 长度打平时 A 赢，和 arena 对 soft 的偏好一致
    for name, src in ((opp_name, other), (replay_name, replay_name)):
        s = f0["snakes"][src]
        snakes.append({"name": name, "body": list(s["body"]),
                       "health": int(s["health"]), "length": len(s["body"])})
    return {
        "width": replay["width"],
        "height": replay["height"],
        "food": [{"x": x, "y": y} for x, y in f0["food"]],
        "snakes": snakes,
    }


class ReplayPlayer:
    """按官方回放逐帧重放动作。非法动作由引擎判死并记原因。"""
    scripted = True
    kind = "replay"

    def __init__(self, replay, name):
        self.name = name
        self.replay = replay
        self.label = "replay:%s" % name
        self.moves = {}
        self.death_note = {}
        frames = replay["frames"]
        for i in range(len(frames) - 1):
            f0, f1 = frames[i], frames[i + 1]
            a = f0["snakes"].get(name)
            b = f1["snakes"].get(name)
            if not a or not b or not a["body"] or not b["body"]:
                continue
            d = _dir_of(a["body"][0], b["body"][0])
            if d:
                # 引擎第 1 回合 = 回放第 0 帧 -> 第 1 帧
                self.moves[f0["turn"] + 1] = d
        # 记录官方死因，方便说明「为什么这里没动作了」
        for f in frames:
            s = f["snakes"].get(name)
            if s and s.get("death_turn"):
                self.death_note[s["death_turn"]] = s.get("death") or "unknown"
        self.last_turn = frames[-1]["turn"]

    def move(self, api, name, turn=0):
        d = self.moves.get(turn)
        if d is None:
            note = self.death_note.get(turn - 1) or self.death_note.get(turn)
            if note:
                return err("replay_end:录制里第 %d 回合已死亡(%s)" % (turn, note))
            return err("replay_end:回放只有 %d 帧，第 %d 回合没动作了"
                       % (self.last_turn + 1, turn))
        return ok(d)


# ---------------------------------------------------------------- 工厂

def is_replay_spec(spec):
    return spec.startswith("replay:")


def parse_spec(spec):
    if spec.startswith("py:"):
        return "py", spec[3:]
    if spec.startswith("http:"):
        return "http", spec[5:]
    if spec.startswith("replay:"):
        body = spec[7:]
        if ":" not in body:
            raise SystemExit("replay: 写法是 replay:<回放json或game_id>:<蛇名>")
        src, name = body.rsplit(":", 1)
        return "replay", (src, name)
    raise SystemExit("不认识的对手写法：%s（支持 py: / http: / replay:）" % spec)


def make_player(spec, step_ms=50.0, replay=None):
    kind, arg = parse_spec(spec)
    if kind == "py":
        return PyPlayer(arg)
    if kind == "http":
        return HttpPlayer(arg, step_ms=step_ms)
    src, name = arg
    if replay is None:
        raise SystemExit("replay 对手需要先加载回放：%s" % src)
    return ReplayPlayer(replay, name)
