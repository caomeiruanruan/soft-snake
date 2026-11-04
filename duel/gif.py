"""把一局的逐帧快照画成 gif（Pillow，纯本地）。"""
from PIL import Image, ImageDraw, ImageFont

COLOR = {
    "A": (124, 156, 245),
    "B": (248, 113, 113),
    "C": (52, 211, 153),
    "D": (251, 191, 36),
}
BG = (15, 18, 26)
GRID = (32, 38, 52)
FOOD = (239, 68, 68)
DEAD = (70, 74, 86)
TEXT = (200, 206, 220)


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def render(frames, path, duration=80):
    if not frames:
        return False
    w = frames[0]["width"]
    h = frames[0]["height"]
    cell = 24 if w <= 11 else 16
    pad = 26
    font = _font(13)
    imgs = []
    for f in frames:
        img = Image.new("RGB", (w * cell + pad * 2, h * cell + pad * 2), BG)
        d = ImageDraw.Draw(img)
        d.text((pad, 4), "turn %d" % f["turn"], font=font, fill=TEXT)
        for x in range(w + 1):
            d.line([(pad + x * cell, pad), (pad + x * cell, pad + h * cell)], fill=GRID)
        for y in range(h + 1):
            d.line([(pad, pad + y * cell), (pad + w * cell, pad + y * cell)], fill=GRID)
        for fx, fy in f["food"]:
            d.ellipse([pad + fx * cell + 3, pad + fy * cell + 3,
                       pad + (fx + 1) * cell - 3, pad + (fy + 1) * cell - 3], fill=FOOD)
        for s in f["snakes"]:
            base = COLOR.get(s["name"], (150, 150, 160))
            dead = bool(s.get("dead")) or s["health"] <= 0
            col = DEAD if dead else base
            for i, (x, y) in enumerate(s["body"]):
                if not (0 <= x < w and 0 <= y < h):
                    continue
                box = [pad + x * cell + 1, pad + y * cell + 1,
                       pad + (x + 1) * cell - 1, pad + (y + 1) * cell - 1]
                if i == 0:
                    d.rectangle(box, fill=tuple(min(255, c + 45) for c in col))
                else:
                    d.rectangle(box, fill=col)
        imgs.append(img)
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0, optimize=True)
    return True
