"""四人混战：我 vs 三条不同性格的蛇。不联网，纯本地。

三只陪练：
  greedy  抢食型：只盯最近的食物，不太看路
  turtler 龟缩型：靠边绕圈，尽量不碰人
  killer  莽撞型：追着别人的头撞
"""
import random
import sys
from core import choose_move, neighbors, DIRS, flood_size


def _api(board, alive):
    return {
        "width": board["width"],
        "height": board["height"],
        "food": board["food"],
        "snakes": [
            {"name": s["name"], "body": [{"x": p[0], "y": p[1]} for p in s["body"]],
             "health": s["health"], "length": len(s["body"])}
            for s in alive
        ],
    }


def _blocked(api, me_name):
    occ = set()
    for s in api["snakes"]:
        b = [(p["x"], p["y"]) for p in s["body"]]
        for p in b[:-1]:
            occ.add(p)
    return occ


def pol_greedy(api, me):
    w, h = api["width"], api["height"]
    me_s = [s for s in api["snakes"] if s["name"] == me][0]
    head = (me_s["body"][0]["x"], me_s["body"][0]["y"])
    occ = _blocked(api, me)
    food = [(f["x"], f["y"]) for f in api["food"]]
    best = None
    for d, n in neighbors(head, w, h):
        if n in occ:
            continue
        sc = 0
        if food:
            sc -= min(abs(n[0] - f[0]) + abs(n[1] - f[1]) for f in food) * 10
        sc += len(neighbors(n, w, h))
        if best is None or sc > best[0]:
            best = (sc, d)
    return best[1] if best else "up"


def pol_turtler(api, me):
    w, h = api["width"], api["height"]
    me_s = [s for s in api["snakes"] if s["name"] == me][0]
    head = (me_s["body"][0]["x"], me_s["body"][0]["y"])
    occ = _blocked(api, me)
    best = None
    for d, n in neighbors(head, w, h):
        if n in occ:
            continue
        edge = min(n[0], n[1], w - 1 - n[0], h - 1 - n[1])
        sc = flood_size(n, occ | {n}, w, h, cap=w * h) * 2 - edge * 4
        if best is None or sc > best[0]:
            best = (sc, d)
    return best[1] if best else "up"


def pol_killer(api, me):
    w, h = api["width"], api["height"]
    me_s = [s for s in api["snakes"] if s["name"] == me][0]
    head = (me_s["body"][0]["x"], me_s["body"][0]["y"])
    occ = _blocked(api, me)
    targets = [(s["body"][0]["x"], s["body"][0]["y"]) for s in api["snakes"] if s["name"] != me]
    best = None
    for d, n in neighbors(head, w, h):
        if n in occ:
            continue
        sc = 0
        if targets:
            sc -= min(abs(n[0] - t[0]) + abs(n[1] - t[1]) for t in targets) * 8
        sc += flood_size(n, occ | {n}, w, h, cap=w * h)
        if best is None or sc > best[0]:
            best = (sc, d)
    return best[1] if best else "up"


POLICIES = {"soft": None, "greedy": pol_greedy, "turtler": pol_turtler, "killer": pol_killer}


def new_snake(name, x, y, d):
    dx, dy = DIRS[d]
    return {"name": name, "body": [(x, y), (x - dx, y - dy), (x - 2 * dx, y - 2 * dy)], "health": 100}


def spawn_food(board, n=3):
    w, h = board["width"], board["height"]
    used = {(f["x"], f["y"]) for f in board["food"]}
    for s in board["snakes"]:
        used |= set(s["body"])
    free = [(x, y) for x in range(w) for y in range(h) if (x, y) not in used]
    random.shuffle(free)
    for p in free[:n]:
        board["food"].append({"x": p[0], "y": p[1]})


def run(seed=0, max_turns=400):
    random.seed(seed)
    w = h = 11
    board = {"width": w, "height": h, "food": [], "snakes": [
        new_snake("soft", 1, 1, "right"),
        new_snake("greedy", 9, 9, "left"),
        new_snake("turtler", 1, 9, "right"),
        new_snake("killer", 9, 1, "left"),
    ]}
    spawn_food(board, 3)
    deaths = []
    t = 0
    while t < max_turns:
        t += 1
        alive = [s for s in board["snakes"] if s["health"] > 0]
        if len(alive) <= 1:
            break
        api = _api(board, alive)
        moves = {}
        for s in alive:
            if s["name"] == "soft":
                moves[s["name"]] = choose_move(api, "soft")
            else:
                moves[s["name"]] = POLICIES[s["name"]](api, s["name"])

        heads = {}
        for s in alive:
            hx, hy = s["body"][0]
            dx, dy = DIRS[moves[s["name"]]]
            heads[s["name"]] = (hx + dx, hy + dy)
        food = {(f["x"], f["y"]) for f in board["food"]}
        eats = {n: heads[n] in food for n in heads}
        occ = {}
        for s in alive:
            b = list(s["body"])
            if not eats[s["name"]] and len(b) > 1:
                b = b[:-1]
            occ[s["name"]] = set(b)

        dead = set()
        for n, p in heads.items():
            if not (0 <= p[0] < w and 0 <= p[1] < h):
                dead.add(n)
        for n, p in heads.items():
            if n in dead:
                continue
            for m, cells in occ.items():
                if p in cells:
                    dead.add(n)
                    break
        ns = list(heads)
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                a, b = ns[i], ns[j]
                if heads[a] == heads[b]:
                    la = len([s for s in alive if s["name"] == a][0]["body"])
                    lb = len([s for s in alive if s["name"] == b][0]["body"])
                    if la > lb:
                        dead.add(b)
                    elif lb > la:
                        dead.add(a)
                    else:
                        dead.add(a); dead.add(b)

        for s in alive:
            n = s["name"]
            s["health"] -= 1
            if n in dead:
                s["health"] = 0
                deaths.append((n, t, len(s["body"])))
                continue
            s["body"].insert(0, heads[n])
            if eats[n]:
                s["health"] = 100
                board["food"] = [f for f in board["food"] if (f["x"], f["y"]) != heads[n]]
                spawn_food(board, 1)
            else:
                if len(s["body"]) > 1:
                    s["body"].pop()
            if s["health"] <= 0:
                s["health"] = 0
                deaths.append((n, t, len(s["body"])))

    final = [s for s in board["snakes"] if s["health"] > 0]
    if final:
        winner = max(final, key=lambda s: len(s["body"]))["name"]
    else:
        winner = deaths[-1][0] if deaths else None
    # 我的名次：按 存活>长度 排
    order = sorted(board["snakes"], key=lambda s: (s["health"] > 0, len(s["body"])), reverse=True)
    place = [s["name"] for s in order].index("soft") + 1
    soft_len = len([s for s in board["snakes"] if s["name"] == "soft"][0]["body"])
    soft_died = any(d[0] == "soft" for d in deaths)
    soft_turn = [d[1] for d in deaths if d[0] == "soft"]
    return {"winner": winner, "place": place, "my_len": soft_len,
            "my_death_turn": soft_turn[0] if soft_turn else None, "turns": t}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    stats = {1: 0, 2: 0, 3: 0, 4: 0}
    wins = 0
    lens, dts = [], []
    for i in range(n):
        r = run(seed=i * 4621 + 11)
        stats[r["place"]] += 1
        if r["winner"] == "soft":
            wins += 1
        lens.append(r["my_len"])
        if r["my_death_turn"]:
            dts.append(r["my_death_turn"])
    print("games      ", n)
    print("最后存活第一", wins, "/", n)
    print("名次分布   1st", stats[1], " 2nd", stats[2], " 3rd", stats[3], " 4th", stats[4])
    print("平均长度   ", round(sum(lens) / n, 2), " 最长", max(lens))
    if dts:
        print("我阵亡回合  平均", round(sum(dts) / len(dts), 1), " 最早", min(dts), " 最晚", max(dts), " 局数", len(dts))
    else:
        print("我一次都没死")
