"""真正的推演：minimax + 迭代加深 + 时间预算。

跟 core.py 里的启发式打分不是一套东西：
  core.py 问「这一步之后我还剩多少格」（一步）
  这里问「我走 A、她回 B、我再走 C …… 四层之后谁的空间大」（四层，带时间上限）

用法（core.py 内部调用）：
    from search import best_move
    mv = best_move(board, me_name, budget_ms=300)
预算用完就退回上一层深度已经算到的结果，从不超时。
"""
import os
import time

DIRS = (("up", (0, 1)), ("down", (0, -1)), ("left", (-1, 0)), ("right", (1, 0)))
MY_WIN = 1e9
MY_LOSE = -1e9


class OutOfTime(Exception):
    pass


def _flood(start, blocked, w, h):
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for _, (dx, dy) in DIRS:
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen and n not in blocked:
                seen.add(n)
                stack.append(n)
    return len(seen)


def _reach(start, target, blocked, w, h):
    if start == target:
        return True
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for _, (dx, dy) in DIRS:
            n = (x + dx, y + dy)
            if n == target:
                return True
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen and n not in blocked:
                seen.add(n)
                stack.append(n)
    return False


def _blocked(bodies):
    s = set()
    for b in bodies:
        s.update(b)
    return s


def _legal(head, blocked, w, h):
    out = []
    for name, (dx, dy) in DIRS:
        n = (head[0] + dx, head[1] + dy)
        if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked:
            out.append((name, n))
    return out


def _advance(body, n, eating):
    """位置推进。注意：判合法性时尾巴永远算墙（引擎这么判），这里只用于估值。"""
    return ([n] + body) if eating else ([n] + body[:-1])


def _eval(mybody, enbody, health, ehealth, w, h):
    blk = _blocked([mybody] + ([enbody] if enbody else []))
    myroom = _flood(mybody[0], blk, w, h)
    v = myroom * 1.0
    if enbody:
        v -= 0.55 * _flood(enbody[0], blk, w, h)
    if len(mybody) > 2 and not _reach(mybody[0], mybody[-1], blk, w, h):
        v -= 45
    v += (health - 50) * 0.35
    if enbody:
        v += (50 - ehealth) * 0.10
    return v


def _negamax(mybody, enbody, food, health, ehealth, w, h, depth, alpha, beta, deadline):
    if time.perf_counter() > deadline:
        raise OutOfTime

    if not enbody:
        return MY_WIN - depth
    if not mybody:
        return MY_LOSE + depth

    blk = _blocked([mybody, enbody])
    my_moves = [t for t in _legal(mybody[0], blk, w, h) if t[1] != enbody[0]]  # 撞头：头对头必死，先排除
    if health <= 1 and not any(n in food for _, n in my_moves):
        return MY_LOSE + depth                                            # 这一步走完就饿死
    if not my_moves:
        return MY_LOSE + depth
    if depth <= 0:
        return _eval(mybody, enbody, health, ehealth, w, h)

    # 走子排序：先吃得到的、再离对手远的，砍枝更快
    def order(t):
        name, n = t
        return -int(n in food)

    best = MY_LOSE
    for _, n in sorted(my_moves, key=order):
        eating = n in food
        nb = _advance(mybody, n, eating)
        nf = food - {n} if eating else food
        nh = 100 if eating else max(0, health - 1)
        val = _their_move(nb, enbody, nf, nh, ehealth, w, h, depth - 1, alpha, beta, deadline)
        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def _their_move(mybody, enbody, food, health, ehealth, w, h, depth, alpha, beta, deadline):
    """对手也在骗人：它挑对我最坏的一步。"""
    if time.perf_counter() > deadline:
        raise OutOfTime
    blk = _blocked([mybody, enbody])
    e_moves = [t for t in _legal(enbody[0], blk, w, h) if t[1] != mybody[0]]
    if ehealth <= 1 and not any(m in food for _, m in e_moves):
        return MY_WIN - depth
    if not e_moves:
        return MY_WIN - depth
    worst = MY_WIN
    for _, m in e_moves:
        eating = m in food
        eb = _advance(enbody, m, eating)
        ef = food - {m} if eating else food
        eh = 100 if eating else max(0, ehealth - 1)
        val = _negamax(mybody, eb, ef, health, eh, w, h, depth - 1, alpha, beta, deadline)
        if val < worst:
            worst = val
        if worst < beta:
            beta = worst
        if alpha >= beta:
            break
    return worst


def best_move(board, me_name, budget_ms=None):
    """算一步。返回方向名，算不出来返回 None。"""
    if budget_ms is None:
        budget_ms = float(os.environ.get("SNAKE_BUDGET_MS", "300"))
    w, h = board["width"], board["height"]
    me = en = None
    for s in board["snakes"]:
        if s["name"] == me_name:
            me = s
        else:
            en = s
    if me is None:
        return None
    mybody = [(p["x"], p["y"]) for p in me["body"]]
    enbody = [(p["x"], p["y"]) for p in en["body"]] if en else []
    if not mybody:
        return None
    food = {(f["x"], f["y"]) for f in board.get("food") or []}
    health = me.get("health", 100)
    ehealth = en.get("health", 100) if en else 100

    deadline = time.perf_counter() + budget_ms / 1000.0
    blk = _blocked([mybody] + ([enbody] if enbody else []))
    roots = _legal(mybody[0], blk, w, h)
    if enbody:
        roots = [t for t in roots if t[1] != enbody[0]]
    if not roots:
        return None

    best_move_name = roots[0][0]
    last_depth_result = None
    try:
        for depth in range(2, 9, 1):
            local_best = None
            for name, n in roots:
                eating = n in food
                nb = _advance(mybody, n, eating)
                nf = food - {n} if eating else food
                nh = 100 if eating else max(0, health - 1)
                val = _their_move(nb, enbody, nf, nh, ehealth, w, h, depth - 1,
                                  MY_LOSE, MY_WIN, deadline)
                if local_best is None or val > local_best[0]:
                    local_best = (val, name)
            last_depth_result = local_best
            best_move_name = local_best[1]
    except OutOfTime:
        if last_depth_result is None:
            return None
    return best_move_name
