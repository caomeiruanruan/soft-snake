"""把每局结果汇总成终端表格 / markdown / jsonl。"""
import json
from collections import Counter

CAUSE_ORDER = ("wall", "self", "body", "head", "timeout", "error",
               "http_status", "http_error", "starve", "replay_illegal", "replay_end")


def _avg(xs):
    return (sum(xs) / float(len(xs))) if xs else 0.0


def _hard(a):
    """回放动作非法是规则内的判定（判死、照常算胜负），不算基础设施异常。"""
    return "replay_illegal" not in a


def summarize(records, roles, labels, seed, step_ms, n_snakes):
    n = len(records)
    valid = [r for r in records if not [a for a in r.get("anomalies", []) if _hard(a)]]
    lines = []
    head = "  ".join("%s=%s" % (role, labels[role]) for role in roles)
    lines.append("%s   %d 局  seed %s" % (head, n, seed))

    sizes = Counter(r["size"] for r in records)
    walls = Counter(r["walls"] for r in records)
    if len(sizes) == 1:
        size_txt = "%dx%d" % (next(iter(sizes)), next(iter(sizes)))
    else:
        size_txt = "mix（%s）" % " / ".join("%dx%d %d 局" % (s, s, c) for s, c in sorted(sizes.items()))
    if len(walls) == 1:
        wall_txt = str(next(iter(walls)))
    else:
        wall_txt = "mix（%s）" % " / ".join("%d: %d 局" % (w, c) for w, c in sorted(walls.items()))
    lines.append("棋盘 %s / %d 蛇 / walls %s / step %gms" % (size_txt, n_snakes, wall_txt, step_ms))
    lines.append("")

    wins = Counter()
    draws = 0
    for r in valid:
        if r["winner"] is None:
            draws += 1
        else:
            wins[r["winner"]] += 1
    tally = " : ".join("%s %d" % (role, wins.get(role, 0)) for role in roles)
    if draws:
        tally += "   平局 %d" % draws
    lead = max(wins.values()) if wins else 0
    top = [role for role in roles if wins.get(role, 0) == lead] if valid else []
    if len(top) == 1:
        rate = "（%s 胜率 %.1f%%）" % (top[0], wins[top[0]] * 100.0 / len(valid))
    else:
        rate = ""
    lines.append("战果      %s   %s" % (tally, rate))
    if len(valid) != n:
        lines.append("有效局 %d / 异常局 %d（异常局不计入胜负）" % (len(valid), n - len(valid)))

    seg = []
    for role in roles:
        ls = [r["lengths"].get(role, 0) for r in records]
        mx = [r["maxlen"].get(role, 0) for r in records]
        seg.append("%s 平均长度 %.1f  最长 %d" % (role, _avg(ls), max(mx) if mx else 0))
    lines.append("  ".join(seg))

    seg = []
    for role in roles:
        lt = [r["lifetime"].get(role, 0) for r in records]
        seg.append("%s 平均寿命 %.0f 回合" % (role, _avg(lt)))
    lines.append("  ".join(seg))
    lines.append("死因分布")
    for role in roles:
        c = Counter()
        alive = 0
        for r in records:
            if role in r["alive"]:
                alive += 1
            d = r["deaths"].get(role)
            if d:
                c[d] += 1
        parts = ["%s %d" % (k, c[k]) for k in CAUSE_ORDER if c.get(k)]
        for k in sorted(c):
            if k not in CAUSE_ORDER:
                parts.append("%s %d" % (k, c[k]))
        parts.append("存活到结束 %d" % alive)
        lines.append("  %s: %s" % (role, "  ".join(parts)))

    lines.append("")
    hard_rows = [r for r in records
                 if [a for a in r.get("anomalies", []) if _hard(a)]]
    if hard_rows:
        lines.append("异常局（不计入胜负，单独标注）")
        for r in hard_rows:
            lines.append("  #%d %s" % (r["game"],
                                       "；".join(a for a in r["anomalies"] if _hard(a))))
    else:
        lines.append("异常局 无")
    soft_rows = [r for r in records
                 if [a for a in r.get("anomalies", []) if not _hard(a)]]
    if soft_rows:
        lines.append("回放动作非法（按规则判该蛇死亡，照常计入胜负）")
        for r in soft_rows:
            lines.append("  #%d %s" % (r["game"],
                                       "；".join(a for a in r["anomalies"] if not _hard(a))))
    return "\n".join(lines)


def jsonl_line(rec):
    return json.dumps(rec, ensure_ascii=False)


def write_outputs(text, records, md_path, jsonl_path):
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(jsonl_line(r) + "\n")
