"""Battlesnake 决策核心：不依赖任何第三方库，arena.py 和 server.py 共用。"""
import random

DIRS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}


def _pts(body):
    if not body:
        return []
    if isinstance(body[0], dict):
        return [(p["x"], p["y"]) for p in body]
    return [tuple(p) for p in body]


def neighbors(p, w, h):
    out = []
    for d, (dx, dy) in DIRS.items():
        n = (p[0] + dx, p[1] + dy)
        if 0 <= n[0] < w and 0 <= n[1] < h:
            out.append((d, n))
    return out


def flood_size(start, blocked, w, h, cap=200):
    """从 start 能走到的空格数量，用来判断会不会把自己闷死。"""
    seen = {start}
    stack = [start]
    while stack and len(seen) < cap:
        c = stack.pop()
        for _, n in neighbors(c, w, h):
            if n in seen or n in blocked:
                continue
            seen.add(n)
            stack.append(n)
    return len(seen)


def choose_move(board, me_name):
    w, h = board["width"], board["height"]
    snakes = board["snakes"]
    me = None
    for s in snakes:
        if s["name"] == me_name:
            me = s
            break
    if me is None:
        return "up"

    mybody = _pts(me["body"])
    head = mybody[0]
    mylen = len(mybody)
    health = me.get("health", 100)

    food = {(f["x"], f["y"]) for f in board.get("food", [])}

    # 所有蛇身占的格子（含尾巴）
    all_cells = set()
    my_tail = None
    enemy_heads = []
    for s in snakes:
        b = _pts(s["body"])
        if not b:
            continue
        all_cells.update(b)
        if s["name"] == me_name:
            my_tail = b[-1] if len(b) > 2 else None
        else:
            enemy_heads.append((b[0], len(b)))

    # blocked      = 尾巴也算墙（这一回合吃了东西，尾巴不会让开）
    # blocked_free = 尾巴不算墙（这一回合没吃，尾巴会让开）
    # 实测证据（2026-11-03 两局，黑匣子记录）：把尾巴那一格当空格钻进去，
    # 引擎判 self-collision —— 即使下一回合尾巴会腾开也一样。
    # 所以两套一律把整条身体当墙，绝不钻自己，尾巴也不例外。
    blocked = set(all_cells)
    blocked_free = set(all_cells)

    # 对面下一回合能到的格子 → 那一格里，能过来的最长的是谁
    enemy_reach = {}
    for eh, elen in enemy_heads:
        for _, p in neighbors(eh, w, h):
            if elen > enemy_reach.get(p, -1):
                enemy_reach[p] = elen

    best = None
    for d, n in neighbors(head, w, h):
        blk = blocked if n in food else blocked_free
        if n in blk:
            continue

        sc = 0.0

        # 1) 撞头风险：贴脸（相距 1）或者对面一步能冲进这一格，都算
        for eh, elen in enemy_heads:
            if elen >= mylen and (abs(eh[0] - n[0]) + abs(eh[1] - n[1]) <= 1 or n in enemy_reach):
                sc -= 100000

        # 2) 空间：走进去还剩多少格可活
        room = flood_size(n, blk | {n}, w, h, cap=w * h)
        if room < mylen + 2:
            # 进去就是死口袋：要早躲，别等到被围住才发现
            sc -= 8000
        sc += min(room, mylen * 6) * 12

        # 3) 食物：越饿越想吃
        if n in food:
            sc += 60 + (100 - health) * 1.2
        elif food:
            best_fd = min(abs(n[0] - f[0]) + abs(n[1] - f[1]) for f in food)
            sc -= best_fd * 1.5

        # 4) 别原地打转（钻自己脖子）
        if len(mybody) > 1 and n == mybody[1]:
            sc -= 300

        # 5) 轻微靠中，减少贴墙
        sc -= (abs(n[0] - w // 2) + abs(n[1] - h // 2)) * 0.6

        sc += random.random() * 0.01

        if best is None or sc > best[0]:
            best = (sc, d)

    if best is not None and best[0] > -5000:
        return best[1]

    # 真被围死了：先挑没被身体占住的、活得最久的那格；一格都没有才随便走
    free_moves = [(d, n) for d, n in neighbors(head, w, h) if n not in blocked_free]
    if free_moves:
        return max(free_moves, key=lambda t: flood_size(t[1], blocked_free | {t[1]}, w, h, cap=w * h))[0]
    any_moves = [d for d, _ in neighbors(head, w, h)]
    if any_moves:
        return random.choice(any_moves)
    return "up"
