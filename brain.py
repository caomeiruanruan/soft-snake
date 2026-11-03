# -*- coding: utf-8 -*-
"""两条蛇的大脑：都是同一套启发式（保命 > 吃食 > 抢空间），加一点随机扰动。"""
import random
from collections import deque

from engine import DIRS, H, W, cells_of

ORDER = ["up", "down", "left", "right"]


def safe(snakes, sid, move, food):
    me = next(s for s in snakes if s["id"] == sid)
    body = cells_of(me)
    head = body[0]
    dx, dy = DIRS[move]
    nh = (head[0] + dx, head[1] + dy)
    if not (0 <= nh[0] < W and 0 <= nh[1] < H):
        return False
    blocked = set()
    for s in snakes:
        if not s["alive"]:
            continue
        b = cells_of(s)
        grow = nh in food
        if s["id"] == sid:
            blocked |= set(b[:-1]) if not grow else set(b)
        else:
            # 对手的尾巴这回合可能让开，保守起见也算障碍
            blocked |= set(b)
    return nh not in blocked


def space(snakes, sid, move, food):
    """走完一步后能到达的格子数（洪水填充）。"""
    me = next(s for s in snakes if s["id"] == sid)
    body = cells_of(me)
    head = body[0]
    dx, dy = DIRS[move]
    nh = (head[0] + dx, head[1] + dy)
    blocked = set()
    for s in snakes:
        if not s["alive"]:
            continue
        b = cells_of(s)
        blocked |= set(b[:-1]) if s["id"] == sid else set(b)
    if nh in blocked:
        return 0
    seen = {nh}
    q = deque([nh])
    while q and len(seen) < 200:
        x, y = q.popleft()
        for d in DIRS.values():
            nx, ny = x + d[0], y + d[1]
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in blocked and (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
    return len(seen)


def decide(state, sid, rng, noise=0.0):
    snakes = state["snakes"]
    food = [tuple(f) for f in state["food"]]
    me = next(s for s in snakes if s["id"] == sid and s["alive"])
    head = cells_of(me)[0]
    foe_head = None
    for s in snakes:
        if s["id"] != sid and s["alive"]:
            foe_head = cells_of(s)[0]

    best, best_score = None, -1e9
    for mv in ORDER:
        if not safe(snakes, sid, mv, food):
            continue
        sp = space(snakes, sid, mv, food)
        dx, dy = DIRS[mv]
        nh = (head[0] + dx, head[1] + dy)
        score = sp * 1.0
        if nh in food:
            score += 30
        # 朝最近的食走
        if food:
            dist = min(abs(nh[0] - f[0]) + abs(nh[1] - f[1]) for f in food)
            score += max(0, 10 - dist) * 0.8
        # 躲开对手的头附近（短蛇更要躲）
        if foe_head:
            d = abs(nh[0] - foe_head[0]) + abs(nh[1] - foe_head[1])
            if d <= 1:
                score -= 12
            elif d == 2:
                score -= 3
        if me["health"] < 30 and food:
            dist = min(abs(nh[0] - f[0]) + abs(nh[1] - f[1]) for f in food)
            score += max(0, 12 - dist) * 1.5
        score += rng.random() * noise
        if score > best_score:
            best, best_score = mv, score
    return best or rng.choice(ORDER)
