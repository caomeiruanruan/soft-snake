# -*- coding: utf-8 -*-
"""Battlesnake 本地裁判（11x11，双蛇）。

规则（官方核心子集）：
  * 每回合两条蛇同时给出 up/down/left/right
  * 出界 / 撞到蛇身 / 对撞时较短的死（同长同死）⇒ 死亡
  * 血量每回合 -1；吃到食物血量回满、长度 +1；血量归 0 死亡
  * 只剩一条活蛇 = 它赢；到达回合上限则比长度
"""
import random

W = H = 11
MAX_TURNS = 300
START_LEN = 3
FOOD_COUNT = 3
START_HEALTH = 100

DIRS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


def cells_of(snake):
    return [(c["x"], c["y"]) for c in snake["body"]]


def occupied(snakes, ignore_tails=False):
    s = set()
    for sn in snakes:
        body = cells_of(sn)
        if ignore_tails and len(body) > 1:
            body = body[:-1]
        s.update(body)
    return s


def spawn(rng, taken, x_range):
    for _ in range(500):
        x = rng.choice(x_range)
        y = rng.randrange(H)
        body = [(x, y), (x, y), (x, y)]
        if x_range[0] == 0 and x_range[-1] < W - 1:
            body = [(x, y), (min(x + 1, W - 1), y), (min(x + 2, W - 1), y)]
        else:
            body = [(x, y), (max(x - 1, 0), y), (max(x - 2, 0), y)]
        if not any(c in taken for c in body) and len(set(body)) == len(body):
            return [{"x": c[0], "y": c[1]} for c in body]
    return [{"x": x_range[0], "y": 0}, {"x": x_range[0], "y": 1}, {"x": x_range[0], "y": 2}]


def new_state(rng):
    snakes = [
        {
            "id": "me",
            "name": "小洄",
            "health": START_HEALTH,
            "body": spawn(rng, set(), list(range(0, 3))),
            "alive": True,
            "death": None,
        },
        {
            "id": "foe",
            "name": "对手",
            "health": START_HEALTH,
            "body": spawn(rng, set(), list(range(W - 1, W - 4, -1))),
            "alive": True,
            "death": None,
        },
    ]
    food = []
    taken = occupied(snakes)
    while len(food) < FOOD_COUNT:
        c = (rng.randrange(W), rng.randrange(H))
        if c not in taken and c not in food:
            food.append(c)
    return {"turn": 0, "snakes": snakes, "food": food, "winner": None}


def next_head(head, move):
    dx, dy = DIRS.get(move or "up", (0, 0))
    return (head[0] + dx, head[1] + dy)


def apply_moves(state, moves):
    """moves: {"me": "up", "foe": "left"}  → 新 state（就地修改并返回）"""
    snakes = state["snakes"]
    alive = [s for s in snakes if s["alive"]]

    # 1. 计算新头
    new_heads = {}
    grow = {}
    for s in alive:
        body = cells_of(s)
        head = body[0]
        nh = next_head(head, moves.get(s["id"]))
        new_heads[s["id"]] = nh
        grow[s["id"]] = nh in state["food"]

    # 2. 判定死亡
    wall = {sid: (h[0] < 0 or h[0] >= W or h[1] < 0 or h[1] >= H)
            for sid, h in new_heads.items()}

    # 身体占格（不吃食时尾巴会移开）
    body_cells = {}
    for s in alive:
        body = cells_of(s)
        tail_moves = not grow.get(s["id"])
        body_cells[s["id"]] = set(body[:-1]) if tail_moves else set(body)

    deaths = {}
    for s in alive:
        sid = s["id"]
        h = new_heads[sid]
        if wall[sid]:
            deaths[sid] = "撞墙"
            continue
        hit = []
        for other in alive:
            if h in body_cells[other["id"]]:
                hit.append(other["id"])
        if hit:
            deaths[sid] = "撞到" + ("自己" if sid in hit else "对手")

    # 头对头
    ids = [s["id"] for s in alive]
    if len(ids) == 2:
        a, b = ids
        if new_heads[a] == new_heads[b]:
            la = len(cells_of(snakes[0] if a == "me" else snakes[1]))
            lb = len(cells_of(snakes[1] if b == "foe" else snakes[0]))
            if la == lb:
                deaths.setdefault(a, "对撞")
                deaths.setdefault(b, "对撞")
            else:
                shorter = a if la < lb else b
                deaths.setdefault(shorter, "对撞（较短）")

    # 3. 移动
    for s in alive:
        sid = s["id"]
        body = cells_of(s)
        if sid in deaths:
            s["alive"] = False
            s["death"] = deaths[sid]
            continue
        body.insert(0, new_heads[sid])
        if not grow.get(sid):
            body.pop()
        s["health"] -= 1
        if grow.get(sid):
            s["health"] = START_HEALTH
            state["food"] = [f for f in state["food"] if f != new_heads[sid]]
        if s["health"] <= 0:
            s["alive"] = False
            s["death"] = "饿死"
        s["body"] = [{"x": c[0], "y": c[1]} for c in body]

    # 4. 补食物
    taken = occupied(snakes)
    while len(state["food"]) < FOOD_COUNT:
        rng = state.get("_rng") or random
        cand = None
        for _ in range(300):
            c = (rng.randrange(W), rng.randrange(H))
            if c not in taken and c not in state["food"]:
                cand = c
                break
        if cand is None:
            break
        state["food"].append(cand)

    state["turn"] += 1

    living = [s for s in snakes if s["alive"]]
    if len(living) == 0:
        state["winner"] = "draw"
    elif len(living) == 1:
        state["winner"] = living[0]["id"]
    elif state["turn"] >= MAX_TURNS:
        lengths = {s["id"]: len(s["body"]) for s in living}
        best = max(lengths.values())
        winners = [k for k, v in lengths.items() if v == best]
        state["winner"] = winners[0] if len(winners) == 1 else "draw"
    return state
