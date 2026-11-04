"""本地对战引擎：判定口径逐条对齐 snake/arena.py。

不能改 arena.py，所以这里的回合结算复刻它 run_game() 的判定顺序：
  1. 出界                → wall
  2. 撞身体（尾巴这回合没吃就让开）→ self / body
  3. 头对头（长的活，一样长双死）  → head
  4. 每回合 health-1；吃到食物回满 100
  5. 只剩一条 / 到 max_turns 停；都活着按长度判胜（打平 A 赢，和 arena 一致）

duel/selftest.py 里有一条「和 arena.run_game 逐局对拍」的测试来证明口径没被改松。
"""
import random

from . import arena

DIRS = arena.DIRS

# 死因顺序 = 输出里的展示顺序
CAUSE_ORDER = ("wall", "self", "body", "head", "timeout", "error",
               "http_status", "http_error", "starve", "replay_illegal", "replay_end")


def _spawn_positions(n, size):
    """2 蛇 11x11 完全沿用 arena 的出生点，保证和旧裁判对得上。"""
    if n == 2:
        if size == 11:
            return [("A", 1, 5, "right"), ("B", 9, 5, "left")]
        return [("A", 2, size // 2, "right"), ("B", size - 3, size // 2, "left")]
    if n == 4:
        return [("A", 2, 2, "right"), ("B", size - 3, 2, "left"),
                ("C", 2, size - 3, "right"), ("D", size - 3, size - 3, "left")]
    raise SystemExit("只支持 2 或 4 条蛇（现在是 %d）" % n)


def new_board(n_snakes, size):
    board = {"width": size, "height": size, "food": [], "snakes": []}
    for name, x, y, d in _spawn_positions(n_snakes, size):
        board["snakes"].append(arena.new_snake(name, x, y, d))
    arena.spawn_food(board, 2)
    return board


def _get(board, name):
    for s in board["snakes"]:
        if s["name"] == name:
            return s
    raise KeyError(name)


def _snap(turn, board, deaths):
    return {
        "turn": turn,
        "width": board["width"],
        "height": board["height"],
        "food": [[f["x"], f["y"]] for f in board["food"]],
        "snakes": [
            {"name": s["name"],
             "body": [list(p) for p in s["body"]],
             "health": s["health"],
             "dead": deaths.get(s["name"])}
            for s in board["snakes"]
        ],
    }


def run_game(players, seed, size=11, n_snakes=2, walls=1, max_turns=400,
             step_ms=50.0, board=None, record=False):
    """players: {蛇名: 有 move(api, name, turn) 的对象}。返回一局的明细。"""
    random.seed(seed)
    if board is None:
        board = new_board(n_snakes, size)
    w, h = board["width"], board["height"]
    names = [s["name"] for s in board["snakes"]]
    deaths = {}
    death_turn = {}
    anomalies = []
    frames = []
    maxlen = {s["name"]: len(s["body"]) for s in board["snakes"]}
    if record:
        frames.append(_snap(0, board, {}))

    turns = 0
    while turns < max_turns:
        alive = [s for s in board["snakes"] if s["health"] > 0]
        if len(alive) <= 1:
            break
        turns += 1
        api = arena.to_api(board)
        moves = {}
        forced = {}                       # 这回合直接判死的：timeout / error / replay_end
        for s in alive:
            name = s["name"]
            r = players[name].move(api, name, turn=turns)
            if r.get("error"):
                cause = "error"
                e = str(r["error"])
                if e.startswith("replay_end"):
                    cause = "replay_end"
                elif e.startswith(("http_timeout", "py_timeout")):
                    cause = "timeout"
                elif e.startswith("http_status"):
                    cause = "http_status"
                elif e.startswith(("http_net", "http_bad")):
                    cause = "http_error"
                forced[name] = cause
                anomalies.append("%s %s @ t%d" % (name, r["error"], turns))
                continue
            limit = max(step_ms, getattr(players[name], "budget_ms", 0.0))
            if r.get("ms", 0.0) > limit:
                forced[name] = "timeout"
                anomalies.append("%s timeout %.1fms > %.0fms @ t%d"
                                 % (name, r["ms"], limit, turns))
                continue
            moves[name] = r["move"]

        # --- 1. 算新头（walls=0 时边界环绕） ---
        food = {(f["x"], f["y"]) for f in board["food"]}
        heads = {}
        for name, mv in moves.items():
            body = _get(board, name)["body"]
            dx, dy = DIRS[mv]
            p = (body[0][0] + dx, body[0][1] + dy)
            if not walls:
                p = (p[0] % w, p[1] % h)
            heads[name] = p

        eats = {n: (heads[n] in food) for n in heads}

        # --- 2. 身体占位：这回合没吃到，尾巴让开（arena 口径） ---
        blocked = {}
        for s in alive:
            body = list(s["body"])
            if not eats.get(s["name"], False) and len(body) > 1:
                body = body[:-1]
            blocked[s["name"]] = set(body)

        dead = set(forced)
        cause = dict(forced)

        for n, p in heads.items():
            if not (0 <= p[0] < w and 0 <= p[1] < h):
                dead.add(n)
                cause[n] = "wall"

        for n, p in heads.items():
            if n in dead:
                continue
            for m, cells in blocked.items():
                if p in cells:
                    dead.add(n)
                    cause[n] = "self" if m == n else "body"
                    break

        ns = list(heads)
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                a, b = ns[i], ns[j]
                if heads[a] == heads[b]:
                    la = len(_get(board, a)["body"])
                    lb = len(_get(board, b)["body"])
                    if la > lb:
                        dead.add(b)
                        cause.setdefault(b, "head")
                    elif lb > la:
                        dead.add(a)
                        cause.setdefault(a, "head")
                    else:
                        dead.add(a)
                        dead.add(b)
                        cause.setdefault(a, "head")
                        cause.setdefault(b, "head")

        # 回放蛇：这一帧的动作在当前局面下非法 → 判死并记原因
        for n in list(dead):
            if getattr(players[n], "scripted", False) and cause.get(n) in ("wall", "self", "body"):
                anomalies.append("%s replay_illegal(%s) @ t%d" % (n, cause[n], turns))
                cause[n] = "replay_illegal"

        # --- 3. 结算 ---
        for s in alive:
            n = s["name"]
            s["health"] -= 1
            if n in dead:
                s["health"] = 0
                deaths.setdefault(n, cause.get(n, "unknown"))
                death_turn.setdefault(n, turns)
                continue
            s["body"].insert(0, heads[n])
            if eats.get(n):
                s["health"] = 100
                board["food"] = [f for f in board["food"] if (f["x"], f["y"]) != heads[n]]
                arena.spawn_food(board, 1)
            elif len(s["body"]) > 1:
                s["body"].pop()
            maxlen[n] = max(maxlen[n], len(s["body"]))
            if s["health"] <= 0:
                s["health"] = 0
                deaths.setdefault(n, "starve")
                death_turn.setdefault(n, turns)

        if record:
            frames.append(_snap(turns, board, deaths))

    final_alive = [s for s in board["snakes"] if s["health"] > 0]
    if len(final_alive) == 1:
        winner = final_alive[0]["name"]
    elif not final_alive:
        winner = None
    else:
        winner = max(final_alive, key=lambda s: (len(s["body"]), -names.index(s["name"])))["name"]

    return {
        "winner": winner,
        "turns": turns,
        "names": names,
        "size": w,
        "walls": walls,
        "lengths": {s["name"]: len(s["body"]) for s in board["snakes"]},
        "maxlen": maxlen,
        "deaths": {n: deaths.get(n) for n in names},
        "death_turn": {n: death_turn.get(n) for n in names},
        "alive": [s["name"] for s in board["snakes"] if s["health"] > 0],
        "anomalies": anomalies,
        "frames": frames if record else None,
    }
