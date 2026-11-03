import io

p = r"E:\workspaceformylove\snake\server.py"
s = io.open(p, encoding="utf-8").read()

old = '''        elif self.path.startswith("/move"):
            mv = choose_move(data)'''
new = '''        elif self.path.startswith("/move"):
            try:
                io.open(r"E:\\workspaceformylove\\snake\\last_move.json", "w",
                        encoding="utf-8").write(json.dumps(data))
            except Exception:
                pass
            mv = choose_move(data)'''

assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched")
