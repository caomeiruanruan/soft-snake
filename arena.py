"""本地裁判 + 自测：跑 N 局，看这条蛇会不会自己撞死。不联网、不花钱。"""
import random
import sys
from core import choose_move, _pts, DIRS


def new_snake(name, x, y, d):
    dx, dy = DIRS[d]
    body = [(x, y), (x - dx, y - dy), (x - 2 * dx, y - 2 * dy)]
    return {"name": name, "body": body, "health": 100, "length": 3}


def spawn_food(board, count=2):
    w, h = board["width"], board["height"]
    used = {(f["x"], f["y"]) for f in board["food"]}
    for s in board["snakes"]:
        used |= set(s["body"])
    free = [(x, y) for x in range(w) for y in range(h) if (x, y) not in used]
    random.shuffle(free)
    for p in free[:count]:
        board["food"].append({"x": p[0], "y": p[1]})


def to_api(board):
    return {
        "width": board["width"],
        "height": board["height"],
        "food": board["food"],
        "snakes": [
            {
                "name": s["name"],
                "body": [{"x": p[0], "y": p[1]} for p in s["body"]],
                "health": s["health"],
                "length": len(s["body"]),
            }
            for s in board["snakes"] if s["health"] > 0
        ],
    }


def run_game(seed=None, max_turns=400, verbose=False):
    if seed is not None:
        random.seed(seed)
    w = h = 11
    a = new_snake("soft", 1, 5, "right")
    b = new_snake("rival", 9, 5, "left")
    board = {"width": w, "height": h, "food": [], "snakes": [a, b]}
    spawn_food(board, 2)

    turns = 0
    while turns < max_turns:
        turns += 1
        alive = [s for s in board["snakes"] if s["health"] > 0]
        if len(alive) <= 1:
            break

        api = to_api(board)
        moves = {}
        for s in alive:
            moves[s["name"]] = choose_move(api, s["name"])

        # 先算新头
        new_heads = {}
        for s in alive:
            hx, hy = s["body"][0]
            dx, dy = DIRS[moves[s["name"]]]
            new_heads[s["name"]] = (hx + dx, hy + dy)

        food_set = {(f["x"], f["y"]) for f in board["food"]}
        eats = {n: (new_heads[n] in food_set) for n in new_heads}

        # 身体占位：尾巴这回合若没吃到就让出来
        blocked = {}
        for s in alive:
            body = list(s["body"])
            if not eats[s["name"]] and len(body) > 1:
                body = body[:-1]
            blocked[s["name"]] = set(body)

        dead = set()
        # 出界
        for n, p in new_heads.items():
            if not (0 <= p[0] < w and 0 <= p[1] < h):
                dead.add(n)
        # 撞身体（含自己）
        for n, p in new_heads.items():
            if n in dead:
                continue
            for m, cells in blocked.items():
                if p in cells:
                    dead.add(n)
                    break
        # 头对头
        names = list(new_heads)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                if new_heads[n1] == new_heads[n2]:
                    l1 = len([s for s in alive if s["name"] == n1][0]["body"])
                    l2 = len([s for s in alive if s["name"] == n2][0]["body"])
                    if l1 > l2:
                        dead.add(n2)
                    elif l2 > l1:
                        dead.add(n1)
                    else:
                        dead.add(n1)
                        dead.add(n2)

        # 结算
        for s in alive:
            n = s["name"]
            s["health"] -= 1
            if n in dead:
                s["health"] = 0
                continue
            np = new_heads[n]
            s["body"].insert(0, np)
            if eats[n]:
                s["health"] = 100
                board["food"] = [f for f in board["food"] if (f["x"], f["y"]) != np]
                spawn_food(board, 1)
            else:
                if len(s["body"]) > 1:
                    s["body"].pop()
            if s["health"] <= 0:
                s["health"] = 0

        if verbose and turns % 20 == 0:
            print("  t%-3d" % turns, [(s["name"], len(s["body"]), s["health"]) for s in board["snakes"]])

    res = {}
    for s in board["snakes"]:
        res[s["name"]] = (s["health"], len(s["body"]))
    winner = None
    if a["health"] > 0 and b["health"] <= 0:
        winner = "soft"
    elif b["health"] > 0 and a["health"] <= 0:
        winner = "rival"
    elif a["health"] > 0 and b["health"] > 0:
        winner = "soft" if len(a["body"]) >= len(b["body"]) else "rival"
    return winner, turns, res


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    wins = {"soft": 0, "rival": 0, None: 0}
    lens, turns_all = [], []
    for i in range(n):
        w, t, res = run_game(seed=i * 7919 + 13)
        wins[w] += 1
        lens.append(res["soft"][1])
        turns_all.append(t)
    print("games  ", n)
    print("win     ", wins["soft"], " lose ", wins["rival"], " draw ", wins[None])
    print("avg len ", round(sum(lens) / n, 2), " max", max(lens), " min", min(lens))
    print("avg turn", round(sum(turns_all) / n, 1), " max", max(turns_all))
