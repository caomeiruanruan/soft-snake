
import json
import urllib.request

payload = {
    "game": {"id": "test-1", "ruleset": {"name": "standard"}, "timeout": 500},
    "turn": 3,
    "board": {
        "width": 11,
        "height": 11,
        "food": [{"x": 5, "y": 8}, {"x": 2, "y": 3}, {"x": 8, "y": 6}],
        "hazards": [],
        "snakes": [
            {
                "id": "me",
                "name": "xiaohui",
                "health": 80,
                "body": [{"x": 5, "y": 5}, {"x": 5, "y": 4}, {"x": 5, "y": 3}],
                "head": {"x": 5, "y": 5},
                "length": 3,
                "shout": "",
            },
            {
                "id": "foe",
                "name": "foe",
                "health": 90,
                "body": [{"x": 2, "y": 2}, {"x": 2, "y": 1}, {"x": 1, "y": 1}],
                "head": {"x": 2, "y": 2},
                "length": 3,
            },
        ],
    },
    "you": {
        "id": "me",
        "name": "xiaohui",
        "health": 80,
        "body": [{"x": 5, "y": 5}, {"x": 5, "y": 4}, {"x": 5, "y": 3}],
        "head": {"x": 5, "y": 5},
        "length": 3,
    },
}

req = urllib.request.Request(
    "http://127.0.0.1:8095/move",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=10) as r:
    print("/move ->", r.status, r.read().decode())

with urllib.request.urlopen("http://127.0.0.1:8095/", timeout=10) as r:
    print("/ ->", r.status, r.read().decode())
