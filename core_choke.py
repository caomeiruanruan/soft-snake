"""Battlesnake 决策核心：不依赖任何第三方库，arena.py 和 server.py 共用。"""
import os
import random

try:
    import search as _search
except Exception:  # 搜索模块缺失时整条退回启发式
    _search = None

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


def can_reach(start, target, blocked, w, h):
    """BFS：从 start 能不能走到 target。target 允许当终点进（即使它在 blocked 里）。"""
    if start == target:
        return True
    seen = {start}
    stack = [start]
    while stack:
        c = stack.pop()
        for _, n in neighbors(c, w, h):
            if n == target:
                return True
            if n in seen or n in blocked:
                continue
            seen.add(n)
            stack.append(n)
    return False


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
        #    用"很大但可比较"的罚分，而不是绝对禁止——否则一旦所有走法都危险，
        #    就会掉进兜底分支、连空间都不看地乱撞（实测 self 死从 5 涨到 10）。
        for eh, elen in enemy_heads:
            if elen >= mylen and (abs(eh[0] - n[0]) + abs(eh[1] - n[1]) <= 1 or n in enemy_reach):
                sc -= 6000 + 300 * (elen - mylen)

        # 2) 空间：走进去还剩多少格可活
        room = flood_size(n, blk | {n}, w, h, cap=w * h)
        # 先算"能不能回到尾巴"：能回 => 空间小不是死，是闭环，尾巴每回合腾一格
        tail_ok = True
        if my_tail and n != my_tail:
            tail_ok = can_reach(n, my_tail, blk | {n}, w, h)
        if room < mylen + 2 and not tail_ok:
            # 进去就是死口袋：要早躲，别等到被围住才发现
            sc -= 20000
        if room < mylen and not tail_ok:
            # 空间已经装不下自己且回不到尾巴
            sc -= (mylen - room) * 120
        sc += min(room, mylen * 6) * 28

        # 2.2) 能不能回到自己的尾巴：能回到尾巴 => 永远有退路；回不到 => 这步把自己关死了
        #      310 回合那局的教训：flood_size 说还剩 84 格，但那 84 格里没有一条路能通到尾巴。
        if not tail_ok:
            sc -= 8000

        # 2.5) 抢地盘：只压对面的活路，不主动贴脸（贴脸会把自己挤死）
        if enemy_heads:
            worst = None
            for eh, elen in enemy_heads:
                could = flood_size(eh, blk | {n}, w, h, cap=w * h)
                if worst is None or could < worst:
                    worst = could
            sc += 12 * (room - worst)

        # 2.4) 预读一层：我踩上 n 之后，对面最狠的那一步能把我的活路压到多少
        if enemy_heads:
            worst_my = room
            for eh, elen in enemy_heads:
                for _, m in neighbors(eh, w, h):
                    if m in blk or m == n:
                        continue
                    # 它走 m 之后，我最好的一步还能剩多少活路（真正的第 2 层）
                    best_after = 0
                    for _, k in neighbors(n, w, h):
                        if k in blk or k == m or k == n:
                            continue
                        r3 = flood_size(k, blk | {n, m, k}, w, h, cap=w * h)
                        if r3 > best_after:
                            best_after = r3
                    if best_after < worst_my:
                        worst_my = best_after
            if worst_my < room:
                sc -= (room - worst_my) * 18
            # 她一步就能把我的空间压到装不下我 —— 这就是"门在她手里"，和死口袋同级
            # 310 回合那局：turn 307 还有 85 格，她一手走完只剩 2 格，只罚 1494 分，太轻。
            if worst_my < mylen + 2:
                sc -= 20000

        # 2.6) 别钻死胡同：走进去只有一两个出口的格子，长身子进去就出不来
        open_nb = 0
        for _, q in neighbors(n, w, h):
            if q not in blk:
                open_nb += 1
        if open_nb <= 1:
            sc -= 1500
        elif open_nb == 2:
            sc -= 150

        # 3) 食物：活着优先，别为了变长把自己吃进死角
        starving = health < 40
        want_eat = starving or health < 80 or mylen < 12
        if n in food:
            if starving:
                sc += 200
            elif want_eat:
                sc += 60 + (100 - health) * 1.2
            else:
                sc += 20
            if room < mylen + 6:
                sc -= 300
        elif food and want_eat:
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

    def _head_collision(p):
        """这一格会不会撞上能赢我的头（同长也算死）。"""
        for eh, elen in enemy_heads:
            if elen >= mylen and (abs(eh[0] - p[0]) + abs(eh[1] - p[1]) <= 1 or p in enemy_reach):
                return True
        return False

    # 0) 真正的四层推演：有预算就用，超时/出错就退回下面的启发式
    if _search is not None and os.environ.get("SNAKE_SEARCH", "1") != "0":
        try:
            mv = _search.best_move(board, me_name)
        except Exception:
            mv = None
        if mv:
            return mv

    if best is not None and best[0] > -50000:
        return best[1]

    # 真被围死 / 所有走法都危险：先挑不撞头的，再挑不撞身的，最后才按空间挑
    cands = list(neighbors(head, w, h))
    no_head = [(d, n) for d, n in cands if not _head_collision(n)]
    free_moves = [(d, n) for d, n in no_head if n not in blocked_free]
    if free_moves:
        return max(free_moves, key=lambda t: flood_size(t[1], blocked_free | {t[1]}, w, h, cap=w * h))[0]
    if no_head:
        return max(no_head, key=lambda t: flood_size(t[1], blocked_free | {t[1]}, w, h, cap=w * h))[0]
    if cands:
        return random.choice([d for d, _ in cands])
    return "up"
