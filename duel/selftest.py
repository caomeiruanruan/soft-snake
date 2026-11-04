"""口径自测：duel.engine 和 arena.run_game 用同一套确定性策略逐局对拍。

arena.run_game 把出生点、11x11、soft/rival 写死了，所以这里：
  - 把 arena.choose_move 换成测试策略；
  - 用 engine.new_board(2, 11)（出生点与 arena 完全一致）喂给 engine；
  - 比较 胜者 / 双方终局长度 / 回合数（arena 的回合数在分出生死那局会多记 1）。

跑法：python -m duel.selftest [局数]
"""
import random
import sys

from . import arena, engine


def policy(api, name):
    me = [s for s in api["snakes"] if s["name"] == name]
    if not me:
        return "up"
    head = (me[0]["body"][0]["x"], me[0]["body"][0]["y"])
    food = [(f["x"], f["y"]) for f in api["food"]]
    blocked = set()
    for s in api["snakes"]:
        b = [(p["x"], p["y"]) for p in s["body"]]
        blocked |= set(b[:-1] if len(b) > 1 else b)
    best = None
    for d, (dx, dy) in (("up", (0, 1)), ("down", (0, -1)),
                        ("left", (-1, 0)), ("right", (1, 0))):
        p = (head[0] + dx, head[1] + dy)
        if not (0 <= p[0] < api["width"] and 0 <= p[1] < api["height"]):
            continue
        if p in blocked:
            continue
        if food:
            score = -abs(p[0] - food[0][0]) - abs(p[1] - food[0][1])
        else:
            score = 0
        if best is None or score > best[0]:
            best = (score, d)
    return best[1] if best else "up"


def reckless(api, name):
    """故意容易撞墙/撞身体，用来覆盖死亡判定分支。"""
    me = [s for s in api["snakes"] if s["name"] == name]
    if not me:
        return "up"
    body = me[0]["body"]
    x, y, ln = body[0]["x"], body[0]["y"], len(body)
    return ("up", "down", "left", "right")[(x * 7 + y * 13 + ln * 5) % 4]


class _Fixed:
    def __init__(self, name, fn=policy):
        self.name = name
        self.fn = fn

    def move(self, api, name, turn=0):
        return {"move": self.fn(api, name), "ms": 0.0, "error": None, "status": None}


def _one(seed, fn=policy):
    orig = arena.choose_move
    arena.choose_move = fn
    try:
        a_win, a_turns, a_res = arena.run_game(seed=seed)
    finally:
        arena.choose_move = orig

    players = {"A": _Fixed("A", fn), "B": _Fixed("B", fn)}
    board = engine.new_board(2, 11)
    board["snakes"][0]["name"] = "A"
    board["snakes"][1]["name"] = "B"
    r = engine.run_game(players, seed=seed, size=11, n_snakes=2, walls=1,
                        max_turns=400)
    e_win = {"soft": "A", "rival": "B", None: None}[a_win]
    len_a, len_b = a_res["soft"][1], a_res["rival"][1]
    any_dead = len(r["alive"]) < 2
    exp_turns = r["turns"] + 1 if any_dead else r["turns"]
    ok = (e_win == r["winner"]
          and r["lengths"]["A"] == len_a and r["lengths"]["B"] == len_b
          and exp_turns == a_turns)
    return ok, (seed, a_win, e_win, a_turns, r["turns"], len_a, len_b,
                r["lengths"]["A"], r["lengths"]["B"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    n = int(argv[0]) if argv else 40
    bad = 0
    for fn, tag in ((policy, "稳健策略"), (reckless, "乱撞策略")):
        for seed in range(n):
            ok, info = _one(seed, fn)
            if not ok:
                bad += 1
                print("[%s] MISMATCH seed=%d arena_win=%r engine_win=%r "
                      "turns %d/%d len %d/%d vs %d/%d" % ((tag,) + info))
    # 同 seed 两遍必须逐字节一致
    p1 = engine.run_game({"A": _Fixed("A"), "B": _Fixed("B")}, seed=123,
                         size=11, n_snakes=2, walls=1)
    p2 = engine.run_game({"A": _Fixed("A"), "B": _Fixed("B")}, seed=123,
                         size=11, n_snakes=2, walls=1)
    det = p1 == p2
    print("对拍 %d 局 x 2 套策略：%s"
          % (n, "全部一致" if not bad else "%d 局不一致" % bad))
    print("确定性：%s" % ("一致" if det else "不一致！"))
    return 0 if (not bad and det) else 1


if __name__ == "__main__":
    sys.exit(main())
