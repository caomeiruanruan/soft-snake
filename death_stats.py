"""统计「我最近这些局都是怎么死的」。

不改蛇、不调额度，只读接口：
  1. 从 Duels 榜上找到 soft 的 entry，抓最近对局 id
  2. 每局取全帧，只算最后 10 回合的 room / 尾巴可达
  3. 按死法分类汇总

用法：
    python death_stats.py                 # 默认最近 20 局
    python death_stats.py --games 30
    python death_stats.py --me soft --league duels
"""
import argparse
import json
import re
import ssl
import sys
import urllib.request
from collections import Counter

LEAGUES = {
    "duels": "77212f22-20f5-4e0c-8db6-78844318a9bc",
    "standard": "d692fd01-5376-4060-8c4c-91dc2ecfe3ba",
    "royale": "77ce41bf-12ad-4eac-bac2-b11939fb9b18",
    "constrictor": "2997e28a-83a0-41e0-a203-d42108cfe450",
}
BASE = "https://arena.battlesnake.com"
DIRS = ((0, 1), (0, -1), (-1, 0), (1, 0))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=40, context=CTX).read().decode("utf-8", "replace")


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


def find_entry(league, name):
    html = get("%s/leaderboards/%s" % (BASE, league))
    pat = r'href="/leaderboards/%s/entries/([0-9a-f\-]{36})"[^>]*>\s*([^<]{1,40})' % league
    for m in re.finditer(pat, html):
        if m.group(2).strip().lower() == name.lower():
            return m.group(1)
    return None


def recent_games(league, entry, want):
    ids, page = [], 0
    while len(ids) < want and page < 5:
        url = "%s/leaderboards/%s/entries/%s" % (BASE, league, entry)
        if page:
            url += "?page=%d" % page
        html = get(url)
        got = re.findall(r"/games/([0-9a-f\-]{36})", html)
        new = [g for g in dict.fromkeys(got) if g not in ids]
        if not new:
            break
        ids.extend(new)
        page += 1
    return ids[:want]


def fetch_frames(gid):
    frames, offset = [], 0
    while True:
        data = json.loads(get("%s/api/games/%s/frames?offset=%d" % (BASE, gid, offset)))
        chunk = data.get("Frames") or []
        frames.extend(chunk)
        if len(chunk) < 100:
            break
        offset += 100
    return frames


def analyse(gid, me_name, w=11, h=11):
    frames = fetch_frames(gid)
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
        rows.append(dict(turn=f.get("Turn"), length=len(body), health=me.get("Health"),
                         room=flood(head, cells, w, h),
                         tail=can_reach(head, tail, cells, w, h),
                         cause=me.get("EliminatedCause") or "",
                         status=str(me.get("StatusCode"))))
    return rows


def classify(rows):
    alive = [r for r in rows if not r["cause"]] or rows
    last = alive[-10:]
    if len(last) < 3:
        return "数据太少", None
    for a, b in zip(last, last[1:]):
        if a["room"] >= 5 and b["room"] <= a["room"] * 0.5:
            return "突然关门", (a["turn"], a["room"], b["turn"], b["room"])
    rooms = [r["room"] for r in last]
    if all(x >= y for x, y in zip(rooms, rooms[1:])):
        return "慢慢耗干", (rooms[0], rooms[-1])
    return "其他", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--me", default="soft")
    ap.add_argument("--league", default="duels", choices=list(LEAGUES))
    ap.add_argument("--games", type=int, default=20)
    a = ap.parse_args()

    league = LEAGUES[a.league]
    entry = find_entry(league, a.me)
    if not entry:
        print("榜上没找到 %s" % a.me)
        return 1
    print("entry %s  联赛 %s" % (entry, a.league))
    ids = recent_games(league, entry, a.games)
    print("取到 %d 局，开始逐局分析\n" % len(ids))

    tally = Counter()
    detail = []
    for i, gid in enumerate(ids, 1):
        try:
            rows = analyse(gid, a.me)
        except Exception as e:
            print("  %2d %s  读取失败 %s" % (i, gid[:8], e))
            continue
        if not rows:
            print("  %2d %s  本局没有这条蛇" % (i, gid[:8]))
            continue
        dead = [r for r in rows if r["cause"]]
        cause = dead[0]["cause"] if dead else "存活"
        turns = rows[-1]["turn"]
        if not dead:
            kind, info = "存活（不参与分类）", None
        else:
            kind, info = classify(rows)
        tally[kind] += 1
        tally["死因:" + cause] += 1
        detail.append((gid, kind, cause, turns, info))
        print("  %2d %s  %-5s 死因%-16s %3s 回合  %s" % (
            i, gid[:8], kind, cause, turns, info))

    total = sum(v for k, v in tally.items() if not k.startswith("死因:"))
    deaths = sum(v for k, v in tally.items()
                 if not k.startswith("死因:") and not k.startswith("存活"))
    print("\n=== 汇总（%d 局，其中死亡 %d 局）===" % (total, deaths))
    for k, v in tally.most_common():
        print("  %-22s %d" % (k, v))
    out = "E:\\workspaceformylove\\snake\\duel\\out\\death_stats.json"
    with open(out, "w", encoding="utf-8") as fp:
        json.dump([{"gid": g, "kind": k, "cause": c, "turns": t, "info": i} for g, k, c, t, i in detail],
                  fp, ensure_ascii=False, indent=1)
    print("\n明细写到 %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
