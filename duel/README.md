# duel · 本地对战台

A 蛇 vs B 蛇，一行命令打 N 局。只动 `duel/` 下的东西；规则判定复用 `arena.py` 的口径
（`duel/engine.py` 逐条复刻，`duel/selftest.py` 用同一套确定性策略和 `arena.run_game`
逐局对拍），决策逻辑从不复制：`py:` 对手就是 import 那个文件、调它的
`choosemove(board, me)`。

在 `E:\workspaceformylove\snake` 下跑：

```bash
python -m duel.run --a py:..\core.py --b py:..\core.py --games 20
python -m duel.run --a py:..\core.py --b http:https://xxx.onrender.com --games 100
python -m duel.run --a py:..\core.py --b replay:<game_id>:<蛇名> --games 50 --gif 1
```

## 三种对手

| 写法 | 说明 |
| --- | --- |
| `py:<文件路径>` | import 文件，调 `choosemove` / `choose_move(board, me_name)`；也兼容 Battlesnake 式单参数 `choose_move(payload)`（按签名自动判断，返回 `{"move": ...}` 或裸方向都行）。相对路径按 `snake/` 找，`..\core.py` 直接写也行。 |
| `http:<引擎地址>` | Battlesnake 协议 `POST /move`，500ms 超时。非 200 / 超时的那一局单独标成**异常局**，不算普通输。 |
| `replay:<回放>:<蛇名>` | `<回放>` 可以是 arena game_id / 本地 frames json / 完整 URL。把那条蛇每一回合的动作逐帧重放当对手；这一帧的动作在当前局面非法就判它死亡，记 `replay_illegal` 和原因。 |

## 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--games N` | 20 | 打多少局 |
| `--seed S` | 0 | 随机种子；同 seed 同参数结果逐字节一致 |
| `--size 11\|19\|mix` | 11 | 棋盘；mix 按局确定性抽 |
| `--snakes 2\|4` | 2 | 4 蛇时 C/D 默认镜像 A/B，可用 `--c` / `--d` 另给 |
| `--walls 0\|1\|mix` | 1 | 0 = 边界环绕，1 = 撞墙死 |
| `--step-ms MS` | 50 | 每步预算；http 对手按协议自带 500ms 预算 |
| `--real` | 关 | 等价于 `--step-ms 500` |
| `--workers N` | 4 | 并行进程；1 = 顺序跑 |
| `--gif N` | 0 | 把前 N 局存成 gif |
| `--save-replay` | 关 | 逐帧记录另存 `out/replays-<时间戳>/game-XXXX.json` |
| `--max-turns N` | 400 | 单局回合上限 |

## 输出

- `out/match-<时间戳>.md`：终端同款表格（战果 / 平均长度 / 平均寿命 / 死因分布 / 异常局）
- `out/match-<时间戳>.jsonl`：每局一行（胜者、回合数、终局长度、死因、异常）
- `out/match-<时间戳>-gN.gif`：`--gif` 时
- `out/` 在 `.gitignore` 里，不进版本库

## 口径

`duel/engine.py` 一个回合的顺序和 `arena.py` 完全一致：

1. 出界 → `wall`
2. 撞身体（尾巴这回合没吃就让开）→ `self` / `body`
3. 头对头（长的活、一样长双死）→ `head`
4. `health -= 1`，吃到食物回满 100
5. 只剩一条或到上限即停；都活着按长度判胜，打平 A 赢

自测：

```bash
python -m duel.selftest 40   # 两套策略 x 40 局和 arena.run_game 对拍 + 确定性
```

## 局面库探针（`duel.probe`）

`replay:` 是把对手的动作**逐帧重放**——棋盘三步就岔开，动作立刻非法，赢了也是假的。
要看清「别人在那个局面下怎么走」，用探针：只取**某一回合的棋盘**，不续弈。

```bash
# 同一局面，我和它各走什么
python -m duel.probe --games <game_id> --name xiaohui --snake py:..\hui\snake\snake.py \
    --turns 60,120,180,220,233,236
# 不指定回合时按 --every / --limit 抽样
python -m duel.probe --games <id> --name soft --snake py:..\core.py --every 25
```

输出一张对照表（回合 / 我选 / 它选 / 我的合法性 / 落点后空间 我·它 / 到食物步数 我·它 / 判定），
可 `--json out/probe.json`、`--md out/probe.md` 落盘。

几个说法：

- `--name` 是**回放里被我替换的那条蛇**，探针拿它在那一回合的棋盘，换成我的蛇来答。
- 「它选」是从相邻两帧反推的（头部位移），不需要额外请求。
- 合法性按**整条身体都是墙**判定（官方实测：尾巴也撞死），比 `duel/engine.py` 的尾巴让位口径更严。
- 「一致率」不是好指标：同一局面常有多步等价棋。真正该看的是判定列——空间掉到 60% 以下、
  或空间已经很紧却还要多走两步吃饭，才值得回看。
