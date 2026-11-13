"""记一行排名，攒成曲线。

用法：python rank_log.py            # 追加一行到 duel/out/rank.log
      python rank_log.py --show     # 只看最近 20 行

输出格式（一行一记）：
  2026-11-04 15:20  Duels  #42  soft  6.2分  64.3%  70局   |  #48 xiaohui 3.4分  59.4%  69局
"""
import argparse
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime

LB = "77212f22-20f5-4e0c-8db6-78844318a9bc"  # Duels 11x11
URL = "https://arena.battlesnake.com/leaderboards/%s" % LB
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duel", "out", "rank.log")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch_rows():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40, context=CTX).read().decode("utf-8", "replace")
    out = {}
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        txt = re.sub(r"<[^>]+>", "|", tr)
        txt = re.sub(r"\|+", "|", txt)
        cells = [c.strip() for c in txt.split("|") if c.strip()]
        # ['42','soft','by','caomeiruanruan','Python','Cloudflare','6.2','64.3','624.0','70']
        if len(cells) >= 10 and cells[0].isdigit():
            name = cells[1]
            out[name.lower()] = dict(rank=cells[0], rating=cells[-4],
                                     win=cells[-3], food=cells[-2], games=cells[-1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--tail", type=int, default=20)
    a = ap.parse_args()

    if a.show:
        if not os.path.exists(LOG):
            print("还没有记录")
            return 0
        with open(LOG, encoding="utf-8") as fp:
            lines = [l.rstrip("\n") for l in fp if l.strip()]
        for l in lines[-a.tail:]:
            print(l)
        return 0

    rows = fetch_rows()
    me = rows.get("soft")
    her = rows.get("xiaohui")
    if not me:
        print("榜上没找到 soft")
        return 1
    line = "%s  Duels  #%s  soft  %s分  %s%%  %s局" % (
        datetime.now().strftime("%Y-%m-%d %H:%M"), me["rank"], me["rating"], me["win"], me["games"])
    if her:
        line += "   |  #%s xiaohui %s分  %s%%  %s局" % (her["rank"], her["rating"], her["win"], her["games"])
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fp:
        fp.write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
