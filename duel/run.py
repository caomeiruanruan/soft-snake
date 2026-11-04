"""对战台命令行。

  python -m duel.run --a py:..\\core.py --b http:https://xxx.onrender.com --games 100
  python -m duel.run --a py:..\\core.py --b replay:<game_id>:<蛇名> --games 50 --gif 1
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

from . import players as P, stats, gif as gifmod, worker

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
ROLES = ("A", "B", "C", "D")


def _argparser():
    ap = argparse.ArgumentParser(
        prog="python -m duel.run",
        description="本地对战台：A 蛇 vs B 蛇，一行命令打 N 局")
    ap.add_argument("--a", required=True, help="py:<文件> / http:<地址> / replay:<回放>:<蛇名>")
    ap.add_argument("--b", required=True, help="同上")
    ap.add_argument("--c", help="4 蛇模式第 3 条（默认镜像 --a）")
    ap.add_argument("--d", help="4 蛇模式第 4 条（默认镜像 --b）")
    ap.add_argument("--games", type=int, default=20, help="打多少局（默认 20）")
    ap.add_argument("--seed", type=int, default=0, help="随机种子（默认 0）")
    ap.add_argument("--size", default="11", help="11 / 19 / mix（默认 11）")
    ap.add_argument("--snakes", type=int, default=2, choices=(2, 4), help="2 或 4 条蛇")
    ap.add_argument("--walls", default="1", help="0 边界环绕 / 1 撞墙死 / mix")
    ap.add_argument("--step-ms", type=float, default=50.0, help="每步预算毫秒（默认 50）")
    ap.add_argument("--real", action="store_true", help="等价于 --step-ms 500")
    ap.add_argument("--workers", type=int, default=4, help="并行进程数（默认 4）")
    ap.add_argument("--gif", type=int, default=0, metavar="N", help="把前 N 局存成 gif")
    ap.add_argument("--save-replay", action="store_true", help="每局的逐帧记录另存 json")
    ap.add_argument("--max-turns", type=int, default=400, help="单局回合上限（默认 400）")
    ap.add_argument("--out-dir", default=OUT_DIR, help="输出目录")
    return ap


def _check(ap, args):
    if args.size not in ("11", "19", "mix"):
        ap.error("--size 只能是 11 / 19 / mix")
    if args.walls not in ("0", "1", "mix"):
        ap.error("--walls 只能是 0 / 1 / mix")
    if args.games < 1:
        ap.error("--games 至少 1")
    if not 1 <= args.workers <= 64:
        ap.error("--workers 要在 1..64")
    if args.gif < 0 or args.gif > args.games:
        ap.error("--gif 要在 0..--games 之间")


def _load_replays(specs):
    replays, info = {}, None
    for i, spec in enumerate(specs):
        if not P.is_replay_spec(spec):
            continue
        src, name = P.parse_spec(spec)[1]
        if info is not None:
            raise SystemExit("一次只能有一条 replay 蛇（它已经替掉一边了）")
        if len(specs) != 2:
            raise SystemExit("replay 对手只支持 2 蛇模式（--snakes 2）")
        if src not in replays:
            replays[src] = P.load_replay(src)
        info = {"idx": i, "src": src, "name": name, "opp": ROLES[1 - i]}
    return replays, info


def _stamp(out_dir):
    base = time.strftime("%Y%m%d-%H%M%S")
    stamp, n = base, 1
    while os.path.exists(os.path.join(out_dir, "match-%s.md" % stamp)):
        n += 1
        stamp = "%s-%d" % (base, n)
    return stamp


def main(argv=None):
    ap = _argparser()
    args = ap.parse_args(argv)
    _check(ap, args)

    step_ms = 500.0 if args.real else float(args.step_ms)
    if step_ms < 200 and not args.real:
        # 实测教训（2026-11-04）：预算给 50ms 时，本机跑 3-4 个 worker 会让 py 玩家
        # 偶发超预算 → 引擎判「直行」→ 本来会赢的局直接输。样本会整体下偏 20-30 个百分点。
        print("提示：--step-ms %.0f 偏小，py 玩家偶发超过预算会被判直行，"
              "胜率样本会失真；对比实验建议 300+ 或 --real" % step_ms)
    specs = [args.a, args.b]
    if args.snakes == 4:
        specs += [args.c or args.a, args.d or args.b]

    replays, info = _load_replays(specs)
    meta = worker.build(specs, step_ms, replays, info)

    need = set()
    if args.gif:
        need.update(range(min(args.gif, args.games)))
    if args.save_replay:
        need.update(range(args.games))

    payload = {
        "specs": specs, "step_ms": step_ms, "seed": args.seed,
        "max_turns": args.max_turns, "size": args.size, "walls": args.walls,
        "replays": replays, "info": info, "record": sorted(need),
    }

    t0 = time.time()
    sys.stderr.write("开打：%d 局（seed %d，%d workers）...\n"
                     % (args.games, args.seed, args.workers))
    if args.workers > 1 and args.games > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.workers, initializer=worker._init, initargs=(payload,)) as pool:
            outs = pool.map(worker._play, range(args.games))
    else:
        worker._init(payload)
        outs = [worker._play(i) for i in range(args.games)]
    elapsed = time.time() - t0

    records = [o["rec"] for o in outs]
    frames = {i: o["frames"] for i, o in enumerate(outs) if o["frames"]}

    text = stats.summarize(records, meta["role_order"], meta["labels"],
                           args.seed, step_ms, args.snakes)
    os.makedirs(args.out_dir, exist_ok=True)
    stamp = _stamp(args.out_dir)
    md_path = os.path.join(args.out_dir, "match-%s.md" % stamp)
    jsonl_path = os.path.join(args.out_dir, "match-%s.jsonl" % stamp)
    stats.write_outputs(text, records, md_path, jsonl_path)

    print(text)
    print("")
    sys.stderr.write("用时 %.1fs\n" % elapsed)
    sys.stderr.write("报告 %s\n明细 %s\n" % (md_path, jsonl_path))

    if frames:
        for i in sorted(frames):
            if i >= args.gif:
                continue
            path = os.path.join(args.out_dir, "match-%s-g%d.gif" % (stamp, i + 1))
            if gifmod.render(frames[i], path):
                sys.stderr.write("gif  %s\n" % path)

    if args.save_replay and frames:
        rdir = os.path.join(args.out_dir, "replays-%s" % stamp)
        os.makedirs(rdir, exist_ok=True)
        for i in sorted(frames):
            path = os.path.join(rdir, "game-%04d.json" % (i + 1))
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"config": records[i], "frames": frames[i]}, fh,
                          ensure_ascii=False)
        sys.stderr.write("replay 目录 %s\n" % rdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
