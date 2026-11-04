"""本地对战台 duel：A 蛇 vs B 蛇，复用 snake/arena.py 的判定口径。

目录边界：本包只允许写 duel/ 下的东西；arena.py / core.py / server.py /
melee.py 只读、不修改。
"""
import os
import sys

SNAKE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SNAKE_DIR not in sys.path:
    sys.path.insert(0, SNAKE_DIR)

import arena  # noqa: E402,F401  （sys.path 就位后复用软软的裁判实现）

__all__ = ["SNAKE_DIR", "arena"]
