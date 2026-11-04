"""多进程里的单局执行体（放在独立模块里，Windows spawn 才能正常 import）。"""
import copy
import random

from . import engine, players as P

ROLES = ("A", "B", "C", "D")

_S = {}


def build(specs, step_ms, replays, info):
    """info = {"idx", "src", "name", "opp"}（replay 对手时才有）。"""
    players, labels, role_of = {}, {}, {}
    board = None
    if info:
        rname, idx, opp = info["name"], info["idx"], info["opp"]
        if rname == opp:
            raise SystemExit("回放里那条蛇也叫 %r，和对面重名了，换一条蛇名再试" % rname)
        board = P.replay_initial_board(replays[info["src"]], rname, opp)
        players[rname] = P.ReplayPlayer(replays[info["src"]], rname)
        players[opp] = P.make_player(specs[1 - idx], step_ms)
        role_of[rname] = ROLES[idx]
        role_of[opp] = opp
        labels[opp] = players[opp].label
        labels[ROLES[idx]] = "replay:%s" % rname
        order = list(ROLES[:2])
    else:
        for role, spec in zip(ROLES, specs):
            players[role] = P.make_player(spec, step_ms)
            labels[role] = players[role].label
            role_of[role] = role
        order = list(ROLES[:len(specs)])
    return {"players": players, "labels": labels, "role_of": role_of,
            "role_order": order, "board": board}


def _cfg(i):
    s = _S
    if s["board"] is not None:
        return s["board"]["width"], 1
    if s["size_mode"] == "mix":
        size = random.Random("size:%s:%d" % (s["seed"], i)).choice([11, 19])
    else:
        size = int(s["size_mode"])
    if s["walls_mode"] == "mix":
        walls = random.Random("walls:%s:%d" % (s["seed"], i)).choice([0, 1])
    else:
        walls = int(s["walls_mode"])
    return size, walls


def _remap_frames(frames, role_of):
    out = []
    for f in frames:
        out.append({
            "turn": f["turn"], "width": f["width"], "height": f["height"],
            "food": f["food"],
            "snakes": [dict(s, name=role_of.get(s["name"], s["name"])) for s in f["snakes"]],
        })
    return out


def _record(i, res, size, walls):
    s = _S
    ro = lambda n: s["role_of"].get(n, n) if n else n
    order = s["role_order"]
    lengths = {ro(n): v for n, v in res["lengths"].items()}
    maxlen = {ro(n): v for n, v in res["maxlen"].items()}
    deaths = {ro(n): v for n, v in res["deaths"].items()}
    dturn = {ro(n): v for n, v in res["death_turn"].items()}
    alive = [ro(n) for n in res["alive"]]
    anom = []
    for a in res["anomalies"]:
        head, _, rest = a.partition(" ")
        if head in s["role_of"]:
            a = s["role_of"][head] + (" " + rest if rest else "")
        anom.append(a)
    return {
        "game": i + 1,
        "size": size,
        "walls": walls,
        "snakes": list(order),
        "winner": ro(res["winner"]),
        "turns": res["turns"],
        "lengths": {r: lengths.get(r, 0) for r in order},
        "maxlen": {r: maxlen.get(r, 0) for r in order},
        "deaths": {r: deaths.get(r) for r in order},
        "death_turn": {r: dturn.get(r) for r in order},
        "lifetime": {r: (dturn.get(r) if dturn.get(r) is not None else res["turns"])
                     for r in order},
        "alive": [r for r in order if r in alive],
        "anomalies": anom,
    }


def _init(payload):
    _S.clear()
    _S.update(build(payload["specs"], payload["step_ms"],
                    payload["replays"], payload["info"]))
    _S.update({"seed": payload["seed"], "max_turns": payload["max_turns"],
               "size_mode": payload["size"], "walls_mode": payload["walls"],
               "step_ms": payload["step_ms"],
               "record": set(payload["record"])})


def _play(i):
    s = _S
    size, walls = _cfg(i)
    board = copy.deepcopy(s["board"]) if s["board"] is not None else None
    rec_wanted = i in s["record"]
    res = engine.run_game(s["players"], seed=s["seed"] + i * 1000003,
                          size=size, n_snakes=len(s["players"]),
                          walls=walls, max_turns=s["max_turns"],
                          step_ms=s["step_ms"], board=board, record=rec_wanted)
    frames = _remap_frames(res["frames"], s["role_of"]) if rec_wanted else None
    return {"rec": _record(i, res, size, walls), "frames": frames}
