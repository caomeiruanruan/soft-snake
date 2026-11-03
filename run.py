# -*- coding: utf-8 -*-
"""跑一局，录成回放。用法： python run.py [seed]"""
import io
import json
import random
import sys
import time

import brain
import engine

BASE = r"E:\workspaceformylove\snake"


def snapshot(state, moves):
    return {
        "turn": state["turn"],
        "moves": dict(moves),
        "food": [list(f) for f in state["food"]],
        "snakes": [
            {
                "id": s["id"],
                "name": s["name"],
                "health": s["health"],
                "alive": s["alive"],
                "death": s["death"],
                "body": [[c["x"], c["y"]] for c in s["body"]],
            }
            for s in state["snakes"]
        ],
        "winner": state["winner"],
    }


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else int(time.time()) % 100000
    rng = random.Random(seed)
    state = engine.new_state(rng)
    state["_rng"] = rng
    frames = [snapshot(state, {})]
    t0 = time.time()

    while state["winner"] is None and state["turn"] < engine.MAX_TURNS:
        moves = {}
        for s in state["snakes"]:
            if not s["alive"]:
                continue
            noise = 2.0 if s["id"] == "foe" else 0.0
            moves[s["id"]] = brain.decide(state, s["id"], rng, noise=noise)
        state = engine.apply_moves(state, moves)
        frames.append(snapshot(state, moves))

    winner = state["winner"]
    lens = {s["id"]: len(s["body"]) for s in state["snakes"]}
    print("seed", seed, "| 回合", state["turn"], "| 胜者", winner, "| 长度", lens)
    for s in state["snakes"]:
        print("   ", s["name"], "存活" if s["alive"] else "死亡：" + str(s["death"]), "len", len(s["body"]))

    data = {"seed": seed, "w": engine.W, "h": engine.H, "frames": frames}
    with io.open(BASE + r"\replay.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    with io.open(BASE + r"\replay.js", "w", encoding="utf-8") as f:
        f.write("window.REPLAY = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    print("回放 ->", BASE + r"\replay.js", "（%.1fs）" % (time.time() - t0))


main()
