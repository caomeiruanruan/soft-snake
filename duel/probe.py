# -*- coding: utf-8 -*-
"""局面库探针：把官方回放里的某一回合请出来，问「同一局面，我会怎么走」。

和 replay 对手的区别：replay 是把对手的动作重放，棋盘三步就岔开、动作立刻非法；
这里只取「那一回合的棋盘」，不做任何续弈，所以不会骗人。

用法：
    python -m duel.probe --games 6375786e-7052-4efa-a22c-d5aaccc3edaa \
        --snake py:..\\hui\\snake\\snake.py --turns 50,100,150,200
    python -m duel.probe --games <id> --snake py:..\\core.py --every 25 --json out/probe.json

输出：每个抽样回合一张对照表——
    我选什么 / 它当时选什么 / 我的选择是否合法 /
    落点后的可走空间（我 vs 它）/ 到最近食物的步数（我 vs 它）/ 判定
只读官方接口，不改任何人的代码。
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import deque

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "duel"

from duel.players import PyPlayer, parse_spec  # noqa: E402

API = "https://arena.battlesnake.com/api"
DIRS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}

# 指标阈值：落点后空间掉到对方选择的 60% 以下，或空间已经很紧却还要多走两步去吃饭
SPACE_RATIO = 0.6
TIGHT = 20
FOOD_GAP = 2


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dsh-duel-probe"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # 官方偶尔限流，退避重试
            last = e
            time.sleep(1.0 + i)
    raise RuntimeError("请求失败：%s（%s）" % (url, last))


def fetch_frames(gid):
    """翻页取全部帧：offset 每次 +100，直到某页不满 100 帧。"""
    frames, off = [], 0
    while True:
        d = get("%s/games/%s/frames?offset=%d" % (API, gid, off))
        page = d.get("Frames") or []
        frames.extend(page)
        if len(page) < 100:
            return frames
        off += len(page)


def snake_ids(gid):
    d = get("%s/games/%s" % (API, gid))
    return {s["Name"]: s["ID"] for s in (d.get("LastFrame") or {}).get("Snakes", [])}


def move_request(gid, sid, turn):
    return get("%s/games/%s/move-request?you=%s&turn=%d" % (API, gid, sid, turn))


def key(x, y):
    return x * 100 + y


def inb(x, y, w, h):
    return 0 <= x < w and 0 <= y < h


def flood(px, py, blocked, w, h):
    if not inb(px, py, w, h) or key(px, py) in blocked:
        return 0
    seen = {key(px, py)}
    q = deque([(px, py)])
    while q:
        cx, cy = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            k = key(nx, ny)
            if inb(nx, ny, w, h) and k not in blocked and k not in seen:
                seen.add(k)
                q.append((nx, ny))
    return len(seen)


def food_steps(px, py, blocked, food, w, h):
    goals = {key(x, y) for x, y in food}
    if not goals or key(px, py) in goals:
        return 0 if goals else 99
    seen = {key(px, py)}
    q = deque([(px, py, 0)])
    while q:
        cx, cy, d = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            k = key(nx, ny)
            if not inb(nx, ny, w, h) or k in seen:
                continue
            if k in goals:
                return d + 1
            if k in blocked:
                continue
            seen.add(k)
            q.append((nx, ny, d + 1))
    return 99


def probe_board(payload, me_name):
    """把 move-request 的 payload 整理成探针要用的几样东西。"""
    board = payload["board"]
    w, h = board["width"], board["height"]
    food = [(f["x"], f["y"]) for f in (board.get("food") or [])]
    snakes = []
    for s in board["snakes"]:
        body = [(p["x"], p["y"]) for p in s["body"]]
        snakes.append({"name": s["name"], "body": body, "health": s.get("health", 100)})
    me = next(s for s in snakes if s["name"] == me_name)
    others = [s for s in snakes if s["name"] != me_name]
    return w, h, food, snakes, me, others


def eval_move(move, me, others, food, w, h):
    """对「这一步」给出合法性 + 两个指标。整条身体都算墙（官方实测：尾巴也撞死）。"""
    hx, hy = me["body"][0]
    dx, dy = DIRS[move]
    nx, ny = hx + dx, hy + dy
    blocked = set()
    for s in [me] + others:
        for p in s["body"]:
            blocked.add(key(*p))
    # 只把尾巴让开于「可走空间」的估计，合法性一律按全身体判
    blocked_tail = set(blocked)
    for s in [me] + others:
        blocked_tail.discard(key(*s["body"][-1]))
    # 官方规则：每回合结束时所有蛇的尾巴都会让开（吃到食物的那条除外），
    # 所以「走进尾巴」是合法的。只有「也吃到食物」时尾巴不动，才真撞上。
    legal = inb(nx, ny, w, h) and key(nx, ny) not in blocked_tail
    if not legal:
        return {"move": move, "legal": False, "space": 0, "fdist": 99, "head_gap": 99}
    tail_risk = any(key(nx, ny) == key(*s["body"][-1]) and key(nx, ny) in food for s in others)
    oh = [s["body"][0] for s in others]
    head_gap = min((abs(nx - o[0]) + abs(ny - o[1]) for o in oh), default=99)
    return {
        "move": move,
        "legal": True,
        "space": flood(nx, ny, blocked_tail, w, h),
        "fdist": food_steps(nx, ny, blocked_tail, food, w, h),
        "head_gap": head_gap,
        "tail_risk": tail_risk,
    }


def recorded_move(frames_by_turn, name, turn):
    """从相邻两帧反推它在那一回合走了哪一步。"""
    a = frames_by_turn.get(turn)
    b = frames_by_turn.get(turn + 1)
    if not a or not b:
        return None
    def head(f):
        for s in f.get("Snakes") or []:
            if s.get("Name") == name:
                return (s["Body"][0]["X"], s["Body"][0]["Y"])
        return None
    ha, hb = head(a), head(b)
    if not ha or not hb:
        return None
    for m, (dx, dy) in DIRS.items():
        if (ha[0] + dx, ha[1] + dy) == hb:
            return m
    return None


def pick_turns(frames, turns, every, limit):
    total = frames[-1]["Turn"] if frames else 0
    if turns:
        return [t for t in turns if 0 < t <= total]
    step = every or max(1, total // (limit or 10))
    out = list(range(step, total + 1, step))
    return out


def run_one(gid, player, me_name, turns_opt, every, limit):
    frames = fetch_frames(gid)
    by_turn = {f["Turn"]: f for f in frames}
    ids = snake_ids(gid)
    if me_name not in ids:
        raise SystemExit("这局里没有叫 %s 的蛇，可选：%s" % (me_name, ", ".join(ids)))
    sid = ids[me_name]
    picks = pick_turns(frames, turns_opt, every, limit)

    rows = []
    for t in picks:
        payload = move_request(gid, sid, t)
        w, h, food, snakes, me, others = probe_board(payload, me_name)
        # PyPlayer.move 收的是 board 本体（它自己从 snakes 里找 you），不是整个 payload
        mine = player.move(payload["board"], me_name, t)
        mine = mine.get("move") if isinstance(mine, dict) else mine
        theirs = recorded_move(by_turn, me_name, t)
        m_ev = eval_move(mine, me, others, food, w, h) if mine in DIRS else None
        t_ev = eval_move(theirs, me, others, food, w, h) if theirs in DIRS else None

        verdict = ""
        if m_ev and t_ev:
            if not m_ev["legal"]:
                verdict = "我这一步非法"
            elif m_ev["space"] < t_ev["space"] * SPACE_RATIO:
                verdict = "空间更差"
            elif m_ev["space"] < TIGHT and m_ev["fdist"] > t_ev["fdist"] + FOOD_GAP:
                verdict = "更饿"
        else:
            verdict = "无法比较"

        rows.append({
            "game": gid, "turn": t, "me": mine, "theirs": theirs,
            "mine_legal": bool(m_ev and m_ev["legal"]),
            "space_mine": m_ev["space"] if m_ev else 0,
            "space_theirs": t_ev["space"] if t_ev else 0,
            "fdist_mine": m_ev["fdist"] if m_ev else 99,
            "fdist_theirs": t_ev["fdist"] if t_ev else 99,
            "verdict": verdict,
        })
        time.sleep(0.15)  # 官方限流留余量
    return rows


def render(rows, out_md=None):
    lines = []
    lines.append("| 回合 | 我选 | 它选 | 我的合法性 | 空间 我/它 | 食步 我/它 | 判定 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append("| %d | %s | %s | %s | %d / %d | %d / %d | %s |" % (
            r["turn"], r["me"], r["theirs"] or "-",
            "合法" if r["mine_legal"] else "非法",
            r["space_mine"], r["space_theirs"],
            r["fdist_mine"], r["fdist_theirs"],
            r["verdict"] or ""))
    text = "\n".join(lines)

    n = len(rows)
    same = sum(1 for r in rows if r["me"] == r["theirs"])
    legal = sum(1 for r in rows if r["mine_legal"])
    worse = sum(1 for r in rows if r["verdict"] in ("空间更差", "更饿"))
    illegal = n - legal
    head = []
    head.append("局面数 %d｜与记录同向 %d（%.1f%%）｜合法 %d（%.1f%%）｜明显更差 %d" % (
        n, same, 100.0 * same / n if n else 0,
        legal, 100.0 * legal / n if n else 0, worse))
    if illegal:
        head.append("注意：%d 个局面我的选择非法——重新看那几步" % illegal)
    summary = "\n".join(head)
    if out_md:
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(summary + "\n\n" + text + "\n")
    return summary, text


def main():
    ap = argparse.ArgumentParser(description="局面库探针：同一局面下我和回放的蛇各走什么")
    ap.add_argument("--games", required=True, help="回放 id，逗号分隔")
    ap.add_argument("--snake", default="py:..\\hui\\snake\\snake.py", help="我的蛇：py:<文件>")
    ap.add_argument("--name", default="xiaohui", help="回放里代表我的那条蛇的名字")
    ap.add_argument("--turns", default="", help="指定回合，逗号分隔")
    ap.add_argument("--every", type=int, default=0, help="每隔多少回合抽一个")
    ap.add_argument("--limit", type=int, default=10, help="不指定回合时默认抽几个")
    ap.add_argument("--json", default="", help="把结果写成 json")
    ap.add_argument("--md", default="", help="把对照表写成 markdown")
    a = ap.parse_args()

    kind, target = parse_spec(a.snake)
    if kind != "py":
        raise SystemExit("探针只支持 py:（本地文件），因为没有「第 N 回合的局面」这种东西可给 http: 用")
    player = PyPlayer(target)

    turns = [int(x) for x in a.turns.split(",") if x.strip()] if a.turns else []
    all_rows = []
    for gid in [g.strip() for g in a.games.split(",") if g.strip()]:
        rows = run_one(gid, player, a.name, turns, a.every, a.limit)
        summary, table = render(rows)
        print("\n=== %s" % gid)
        print(summary)
        print(table)
        all_rows.extend(rows)

    summary, table = render(all_rows)
    print("\n=== 合计")
    print(summary)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, ensure_ascii=False, indent=1)
        print("json -> %s" % a.json)
    if a.md:
        render(all_rows, a.md)
        print("md -> %s" % a.md)


if __name__ == "__main__":
    main()
