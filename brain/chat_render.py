"""Render the showdown as a group-chat UI. (PRD B: clip visuals)

Draws 1080x1920 frames of a group chat where ARIA (our bot) and the reacting AIs
appear as message bubbles, one per beat. clipfarm stitches a frame per card into
the video, so the chat grows message-by-message in time with the voices, and the
winner's bubble lights up on the drop.
"""

import glob
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (10, 10, 15)
HEADER_H = 128
MARGIN = 44
AVATAR = 84
GAP = 26                      # avatar-to-bubble gap
BUBBLE_PAD = 26
LINE_GAP = 10
MSG_GAP = 40
BUBBLE_MAX = W - MARGIN * 2 - AVATAR - GAP

_FONT_DIR = "/usr/share/fonts/liberation"


def _font(size: int, bold: bool = False, italic: bool = False):
    name = "LiberationSans-"
    name += "BoldItalic" if (bold and italic) else "Bold" if bold else "Italic" if italic else "Regular"
    path = os.path.join(_FONT_DIR, name + ".ttf")
    if not os.path.exists(path):
        path = glob.glob(os.path.join(_FONT_DIR, "*.ttf"))[0]
    return ImageFont.truetype(path, size)


F_HEADER = _font(44, bold=True)
F_NAME = _font(34, bold=True)
F_TEXT = _font(40)
F_BADGE = _font(30, bold=True)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)) if len(c) == 6 else (255, 255, 255)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _draw_message(img, draw, msg, y, highlight=False, dim=False):
    color = _hex(msg["color"])
    if dim:
        color = _mix(color, BG, 0.55)
    x = MARGIN
    # avatar: colored circle with the initial
    draw.ellipse([x, y, x + AVATAR, y + AVATAR], fill=color)
    initial = (msg["name"] or "?")[0].upper()
    iw = draw.textlength(initial, font=F_NAME)
    draw.text((x + AVATAR / 2 - iw / 2, y + AVATAR / 2), initial,
              font=F_NAME, fill=(10, 10, 15), anchor="lm")

    bx = x + AVATAR + GAP
    # name
    draw.text((bx, y + 2), msg["name"], font=F_NAME, fill=color, anchor="lm")
    ty = y + 26
    # bubble text
    lines = _wrap(draw, msg["text"], F_TEXT, BUBBLE_MAX - BUBBLE_PAD * 2)
    line_h = F_TEXT.size + LINE_GAP
    text_h = line_h * len(lines)
    widest = max((draw.textlength(ln, font=F_TEXT) for ln in lines), default=0)
    bw = min(BUBBLE_MAX, widest + BUBBLE_PAD * 2)
    bh = text_h + BUBBLE_PAD * 2
    bubble_bg = _mix(BG, color, 0.16 if not dim else 0.06)
    draw.rounded_rectangle([bx, ty, bx + bw, ty + bh], radius=26, fill=bubble_bg)
    if highlight:
        draw.rounded_rectangle([bx - 4, ty - 4, bx + bw + 4, ty + bh + 4],
                               radius=30, outline=color, width=5)
    tcol = (240, 240, 245) if not dim else _mix((240, 240, 245), BG, 0.5)
    for i, ln in enumerate(lines):
        draw.text((bx + BUBBLE_PAD, ty + BUBBLE_PAD + i * line_h + line_h / 2 - LINE_GAP / 2),
                  ln, font=F_TEXT, fill=tcol, anchor="lm")

    bottom = ty + bh
    if highlight:
        badge = "MOST SELFLESS"
        star_w = 40
        pill_w = star_w + draw.textlength(badge, font=F_BADGE) + 40
        py = bottom + 12
        draw.rounded_rectangle([bx, py, bx + pill_w, py + 46], radius=23, fill=color)
        _star(draw, bx + 26, py + 23, 15, fill=(10, 10, 15))
        draw.text((bx + star_w + 8, py + 23), badge, font=F_BADGE, fill=(10, 10, 15), anchor="lm")
        bottom = py + 46
    return bottom + MSG_GAP


def _star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def render_chat(messages, out_path, highlight_key=None):
    """messages: [{name, color, text, key}] shown top-to-bottom. If highlight_key
    is set, that bubble lights up and the others dim (the winner reveal)."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    # header
    draw.rectangle([0, 0, W, HEADER_H], fill=(21, 18, 31))
    draw.line([0, HEADER_H, W, HEADER_H], fill=(42, 36, 64), width=2)
    draw.ellipse([MARGIN, 34, MARGIN + 60, 94], fill=(122, 58, 255))
    draw.text((MARGIN + 80, HEADER_H / 2), "the group chat", font=F_HEADER,
              fill=(230, 224, 245), anchor="lm")

    y = HEADER_H + 40
    for m in messages:
        dim = highlight_key is not None and m["key"] != highlight_key
        y = _draw_message(img, draw, m, y,
                          highlight=(m["key"] == highlight_key), dim=dim)
    img.save(out_path)
    return out_path
