"""只看死前那十几回合 —— 快速判断一局是怎么输的。

用法：
    python last_turns.py <对局id 或 回放链接>            # 默认看最后 15 回合
    python last_turns.py <id> --tail 25 --me soft
    python last_turns.py <id> --all                     # 打印全程

输出每一行：
    回合 / 长度 / 血量 / room（头部能走到的空格数）/ tail（能不能走回自己尾巴）
死因分类：
    突然关门 —— 最后 10 回合里 room 从高位一步掉到很低（>=50% 且绝对值掉 >=5）
    慢慢耗干 —— room 单调下降，没有断崖
    其他     —— 都没中
"""
import argparse
import json
import ssl
import sys
import urllib.request

API = "https://arena.battlesnake.com/api/games/%s"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
DIRS = ((0, 1), (0, -1), (-1, 0), (1, 0))


def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30, context=CTX).read().decode("utf-8", "replace")


def game_id(raw):
    """从链接或裸 id 里抠出 uuid。"""
    raw = raw.strip().split("?")[0].rstrip("/")
    return raw.rsplit("/", 1)[-1]


def neighbors(c, w, h):
    for dx, dy in DIRS:
        x, y = c[0] + dx, c[1] + dy
        if 0 <= x < w and 0 <= y < h:
            yield (x, y)


def flood(start, blocked, w, h):
    seen = {start}
    stack = [start]
    while stack:
        c = stack.pop()
        for n in neighbors(c, w, h):
            if n in seen or n in blocked:
                continue
            seen.add(n)
            stack.append(n)
    return len(seen)


def can_reach(start, target, blocked, w, h):
    if start == target:
        return True
    seen = {start}
    stack = [start]
    while stack:
        c = stack.pop()
        for n in neighbors(c, w, h):
            if n == target:
                return True
            if n in seen or n in blocked:
                continue
            seen.add(n)
            stack.append(n)
    return False


def fetch_frames(gid):
    frames = []
    offset = 0
    while True:
        data = json.loads(get_text((API % gid) + "/frames?offset=%d" % offset))
        chunk = data.get("Frames") or []
        frames.extend(chunk)
        if len(chunk) < 100:
            break
        offset += 100
    return frames


def board_size(gid):
    try:
        info = json.loads(get_text(API % gid))
        w = info.get("Width") or (info.get("Ruleset") or {}).get("Width")
        return int(w or 11), int(info.get("Height") or w or 11)
    except Exception:
        return 11, 11


def trace(frames, me_name, w, h):
    rows = []
    for f in frames:
        me = None
        for s in f.get("Snakes", []):
            if s.get("Name") == me_name:
                me = s
                break
        if me is None:
            continue
        body = [(p["X"], p["Y"]) for p in me.get("Body") or []]
        if not body:
            continue
        cells = {(p["X"], p["Y"]) for s in f["Snakes"] for p in s.get("Body") or []}
        head, tail = body[0], body[-1]
        room = flood(head, cells, w, h)
        tail_ok = can_reach(head, tail, cells, w, h)
        rows.append(dict(turn=f.get("Turn"), length=len(body),
                         health=me.get("Health"), room=room, tail=tail_ok,
                         cause=me.get("EliminatedCause") or ""))
    return rows


def classify(rows):
    # 最后那一帧是"已经死了"的局面（身体断开、room 会突然变大），不参与判定
    rows = [r for r in rows if not r["cause"]] or rows
    last = rows[-10:] if len(rows) >= 10 else rows
    if len(last) < 3:
        return "数据太少"
    drops = []
    for a, b in zip(last, last[1:]):
        if a["room"] >= 5 and b["room"] <= a["room"] * 0.5:
            drops.append((a["turn"], a["room"], b["turn"], b["room"]))
    if drops:
        t0, r0, t1, r1 = drops[0]
        return "突然关门（turn %s 的 %d 格 → turn %s 的 %d 格）" % (t0, r0, t1, r1)
    rooms = [r["room"] for r in last]
    if all(x >= y for x, y in zip(rooms, rooms[1:])):
        return "慢慢耗干（%d → %d，逐格下降）" % (rooms[0], rooms[-1])
    return "其他（没有明显断崖，也不是单调下降）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--tail", type=int, default=15)
    ap.add_argument("--me", default="soft")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    gid = game_id(a.game)
    frames = fetch_frames(gid)
    if not frames:
        print("没取到帧，检查 id 是否正确")
        return 1
    w, h = board_size(gid)
    rows = trace(frames, a.me, w, h)
    if not rows:
        print("这局里没有叫 %s 的蛇" % a.me)
        return 1

    show = rows if a.all else rows[-a.tail:]
    print("对局 %s   棋盘 %dx%d   共 %d 帧   本蛇 %s" % (gid, w, h, len(frames), a.me))
    print("回合   长度   血量   room  可回尾")
    for r in show:
        print("%4s %6s %6s %6s   %s%s" % (
            r["turn"], r["length"], r["health"], r["room"],
            "Y" if r["tail"] else "N",
            ("  ← " + r["cause"]) if r["cause"] else ""))
    print("\n判定：" + classify(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
