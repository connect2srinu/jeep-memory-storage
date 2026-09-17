#!/usr/bin/env python3
"""Generate diagrams (PNG) for the three-way memory comparison doc.

Custom vs Pure Memory Bank vs Hybrid (Control Plane over Memory Bank).
Pure Pillow — no external rasterizer. Outputs 1600x900 PNGs into ./img.
Run:  python3 generate_images.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "img")
os.makedirs(OUT, exist_ok=True)

FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

INK = "#1F2937"
MUTED = "#6B7280"
BG = "#FFFFFF"
BAND = "#F3F4F6"
BLUE = ("#DBEAFE", "#2563EB", "#1E40AF")      # agent / business / postgres
PURPLE = ("#EDE9FE", "#7C3AED", "#5B21B6")    # control plane (hero)
TEAL = ("#CCFBF1", "#0D9488", "#0F766E")      # gcp managed / memory bank
RED = ("#FEE2E2", "#DC2626", "#991B1B")       # problem / gap
GREEN = ("#D1FAE5", "#059669", "#065F46")     # good / pass
AMBER = ("#FEF3C7", "#D97706", "#92400E")     # partial / accent


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def canvas(w=1600, h=900):
    img = Image.new("RGB", (w, h), BG)
    return img, ImageDraw.Draw(img)


def rrect(d, box, radius=18, fill=None, outline=None, width=3):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap(d, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def centered(d, box, text, fnt, fill, gap=6, pad=16):
    x0, y0, x1, y1 = box
    lines = []
    for para in text.split("\n"):
        lines.extend(wrap(d, para, fnt, (x1 - x0) - 2 * pad))
    lh = fnt.size + gap
    total = lh * len(lines) - gap
    ty = y0 + ((y1 - y0) - total) / 2
    for ln in lines:
        lw = d.textlength(ln, font=fnt)
        d.text((x0 + ((x1 - x0) - lw) / 2, ty), ln, font=fnt, fill=fill)
        ty += lh


def title(d, text, sub=None):
    d.text((60, 40), text, font=font(44, True), fill=INK)
    if sub:
        d.text((62, 100), sub, font=font(23), fill=MUTED)


def bullets(d, x, y, items, fnt, fill, dot=GREEN[1], gap=14, max_w=520):
    for it in items:
        d.ellipse([x, y + 9, x + 10, y + 19], fill=dot)
        lines = wrap(d, it, fnt, max_w)
        for i, ln in enumerate(lines):
            d.text((x + 24, y + i * (fnt.size + 4)), ln, font=fnt, fill=fill)
        y += len(lines) * (fnt.size + 4) + gap
    return y


def arrow(d, p0, p1, color=MUTED, width=6, head=18):
    d.line([p0, p1], fill=color, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for a in (ang + math.radians(152), ang - math.radians(152)):
        d.line([p1, (p1[0] + head * math.cos(a), p1[1] + head * math.sin(a))], fill=color, width=width)


def mark(d, cx, cy, r, kind):
    """kind: 'pass' | 'fail' | 'part'."""
    col = {"pass": GREEN[1], "fail": RED[1], "part": AMBER[1]}[kind]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    w = max(4, int(r / 6))
    if kind == "pass":
        d.line([(cx - 0.45 * r, cy + 0.02 * r), (cx - 0.12 * r, cy + 0.38 * r),
                (cx + 0.5 * r, cy - 0.4 * r)], fill="#FFFFFF", width=w, joint="curve")
    elif kind == "fail":
        d.line([(cx - 0.38 * r, cy - 0.38 * r), (cx + 0.38 * r, cy + 0.38 * r)], fill="#FFFFFF", width=w)
        d.line([(cx + 0.38 * r, cy - 0.38 * r), (cx - 0.38 * r, cy + 0.38 * r)], fill="#FFFFFF", width=w)
    else:
        d.line([(cx - 0.42 * r, cy), (cx + 0.42 * r, cy)], fill="#FFFFFF", width=w)


def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path)
    print("wrote", path)


# ---------------------------------------------------------------- 1. three options
def three_options():
    img, d = canvas()
    title(d, "Three Options for the Unified Memory Layer",
          "Same agents on top — the difference is what sits underneath and who operates it")
    cols = [
        ("CUSTOM DESIGN", "Build & run our own engine", BLUE,
         [("Agent", BLUE), ("Custom memory service\nextraction · merge · compliance code\n(we build & operate)", RED),
          ("PostgreSQL\nsystem of record · SQL · exportable", BLUE)],
         "Highest build effort · full control"),
        ("PURE MEMORY BANK", "Adopt Google's managed service", TEAL,
         [("Agent", BLUE), ("ADK connector (ready-made)", TEAL),
          ("Vertex Memory Bank\nmanaged store · TTL · revisions · GA SLA", TEAL)],
         "Lowest build effort · least control"),
        ("HYBRID  (recommended)", "Control Plane over Memory Bank", PURPLE,
         [("Agent", BLUE),
          ("Control Plane\nnever-store · RBAC · resolve · audit", PURPLE),
          ("__SPLIT__", None)],
         "Moderate build · best of both"),
    ]
    cw, gap, x0 = 480, 30, 55
    for i, (name, tag, col, layers, cap) in enumerate(cols):
        x = x0 + i * (cw + gap)
        rrect(d, [x, 160, x + cw, 268], radius=16, fill=col[0], outline=col[1], width=4 if i == 2 else 3)
        centered(d, [x, 172, x + cw, 224], name, font(26, True), col[2], gap=2)
        centered(d, [x, 224, x + cw, 260], tag, font(19), MUTED, gap=2)
        ys = [300, 400, 540]
        hs = [70, 110, 110]
        for j, (lab, lc) in enumerate(layers):
            y = ys[j]
            h = hs[j]
            if lab == "__SPLIT__":
                half = (cw - 20) / 2
                rrect(d, [x, y, x + half, y + h], radius=12, fill=TEAL[0], outline=TEAL[1], width=3)
                centered(d, [x, y, x + half, y + h], "Memory Bank\nmanaged storage", font(17, True), TEAL[2], gap=2, pad=8)
                rrect(d, [x + half + 20, y, x + cw, y + h], radius=12, fill=BLUE[0], outline=BLUE[1], width=3)
                centered(d, [x + half + 20, y, x + cw, y + h], "Postgres\nsystem of record + audit", font(17, True), BLUE[2], gap=2, pad=8)
            else:
                bold = lc == PURPLE
                rrect(d, [x, y, x + cw, y + h], radius=12, fill=lc[0], outline=lc[1], width=4 if bold else 3)
                centered(d, [x, y, x + cw, y + h], lab, font(19 if bold else 18, bold), lc[2], gap=3, pad=10)
            if j < len(layers) - 1:
                arrow(d, (x + cw / 2, ys[j] + hs[j] + 2), (x + cw / 2, ys[j + 1] - 2), color=INK, width=5, head=13)
        rrect(d, [x, 670, x + cw, 726], radius=12, fill=BAND)
        centered(d, [x, 670, x + cw, 726], cap, font(19, True), col[2] if i == 2 else INK)
    d.text((60, 770), "The real choice is not Custom vs Memory Bank — it is raw Memory Bank vs Memory Bank governed by our Control Plane.",
           font=font(22, True), fill=INK)
    save(img, "01_three_options.png")


# ---------------------------------------------------------------- 2. gate matrix
def gate_matrix():
    img, d = canvas()
    title(d, "Decision Gates — Pass / Fail Before Any Scoring",
          "If a use case needs a gate and an option can't meet it, that option is out for that use case")
    gates = [
        ("G1  Provable never-store (code-enforced denylist)", "pass", "fail", "pass"),
        ("G2  Policy deletion & retention (TTL + delete + audit)", "pass", "pass", "pass"),
        ("G3  Deterministic recall of standing instructions", "pass", "part", "pass"),
        ("G4  Contractual SLA + documented DR (RTO/RPO)", "pass", "part", "part"),
        ("G5  Separation of duties (config-change ≠ deploy)", "pass", "part", "pass"),
        ("G6  Bulk / SQL analytics & clean exit", "pass", "fail", "pass"),
    ]
    lx0, lx1 = 55, 700
    colx = [700, 1000, 1300, 1560]  # custom, mb, hybrid boundaries
    centers = [(colx[0] + colx[1]) / 2, (colx[1] + colx[2]) / 2, (colx[2] + colx[3]) / 2]
    heads = [("Custom", BLUE), ("Pure Memory Bank", TEAL), ("Hybrid", PURPLE)]
    hy0, hy1 = 175, 235
    for c, (name, col) in zip(centers, heads):
        rrect(d, [c - 145, hy0, c + 145, hy1], radius=12, fill=col[0], outline=col[1], width=3)
        centered(d, [c - 145, hy0, c + 145, hy1], name, font(21, True), col[2])
    y = 250
    rh = 78
    for i, (name, *vals) in enumerate(gates):
        band = BG if i % 2 == 0 else BAND
        d.rectangle([lx0, y, colx[3], y + rh], fill=band)
        for j, ln in enumerate(wrap(d, name, font(20, True), lx1 - lx0 - 20)):
            d.text((lx0 + 8, y + 16 + j * 26), ln, font=font(20, True), fill=INK)
        for c, v in zip(centers, vals):
            mark(d, c, y + rh / 2, 24, v)
        y += rh
    # passes-all row
    d.rectangle([lx0, y, colx[3], y + rh], fill="#EEF2FF")
    d.text((lx0 + 8, y + 24), "Passes all critical gates?", font=font(22, True), fill=INK)
    for c, v in zip(centers, ("pass", "fail", "pass")):
        mark(d, c, y + rh / 2, 27, v)
    y += rh + 24
    # legend
    lx = 60
    for kind, lab in (("pass", "meets the gate"), ("part", "partial / conditional"), ("fail", "structural gap")):
        mark(d, lx + 12, y + 14, 13, kind)
        d.text((lx + 34, y + 2), lab, font=font(19), fill=INK)
        lx += 34 + d.textlength(lab, font=font(19)) + 60
    d.text((60, y + 46), "Hybrid passes every gate: it uses Memory Bank for managed storage and the Control Plane for never-store + clean exit.",
           font=font(21, True), fill=PURPLE[2])
    save(img, "02_gate_matrix.png")


# ---------------------------------------------------------------- 3. hybrid flow
def hybrid_flow():
    img, d = canvas()
    title(d, "How the Hybrid Works — Governance Before Storage",
          "The Control Plane adds the two things Memory Bank lacks, then delegates storage to the managed service")
    # WRITE PATH
    d.text((60, 150), "WRITE  —  save(fact)", font=font(24, True), fill=INK)
    rrect(d, [60, 200, 300, 320], radius=16, fill=BLUE[0], outline=BLUE[1], width=3)
    centered(d, [60, 200, 300, 320], "Agent\nsave(fact)", font(21, True), BLUE[2], gap=3)
    arrow(d, (305, 260), (400, 260), color=INK, width=6, head=16)
    rrect(d, [400, 180, 1050, 360], radius=18, fill=PURPLE[0], outline=PURPLE[1], width=4)
    d.text((424, 196), "Control Plane — enforced before anything is stored", font=font(21, True), fill=PURPLE[2])
    bullets(d, 430, 238, [
        "1. Never-store screen — block restricted content (denylist)",
        "2. Sensitivity classify + RBAC — may this agent write this?",
        "3. Governed write — canonical attribute or approved topic",
        "4. Audit event — who / what / when / correlation id",
    ], font(18), PURPLE[2], dot=PURPLE[1], gap=6, max_w=590)
    arrow(d, (1055, 240), (1150, 240), color=INK, width=6, head=16)
    rrect(d, [1150, 190, 1545, 285], radius=14, fill=TEAL[0], outline=TEAL[1], width=3)
    centered(d, [1150, 190, 1545, 285], "Vertex Memory Bank\nmanaged storage · TTL · revisions", font(18, True), TEAL[2], gap=2, pad=10)
    arrow(d, (1055, 300), (1150, 300), color=INK, width=6, head=16)
    rrect(d, [1150, 300, 1545, 395], radius=14, fill=BLUE[0], outline=BLUE[1], width=3)
    centered(d, [1150, 300, 1545, 395], "PostgreSQL\nsystem of record + audit", font(18, True), BLUE[2], gap=2, pad=10)
    # READ PATH
    d.text((60, 470), "READ  —  resolve()", font=font(24, True), fill=INK)
    rrect(d, [60, 520, 300, 640], radius=16, fill=BLUE[0], outline=BLUE[1], width=3)
    centered(d, [60, 520, 300, 640], "Agent\nresolve()", font(21, True), BLUE[2], gap=3)
    arrow(d, (305, 580), (400, 580), color=INK, width=6, head=16)
    rrect(d, [400, 500, 1050, 680], radius=18, fill=PURPLE[0], outline=PURPLE[1], width=4)
    d.text((424, 516), "Control Plane — deterministic resolution", font=font(21, True), fill=PURPLE[2])
    bullets(d, 430, 558, [
        "1. list-by-scope — authoritative, not similarity guesswork",
        "2. Merge canonical + dynamic + session state",
        "3. Apply prioritization & sensitivity policy",
        "4. Return a consistent snapshot the agent can trust",
    ], font(18), PURPLE[2], dot=PURPLE[1], gap=6, max_w=590)
    arrow(d, (1150, 560), (1055, 560), color=INK, width=6, head=16)
    rrect(d, [1150, 500, 1545, 660], radius=14, fill=BAND, outline=MUTED, width=2)
    centered(d, [1150, 500, 1545, 660], "Stores\nMemory Bank + Postgres\n(read back by scope)", font(18, True), INK, gap=3, pad=10)
    d.text((60, 730), "Best of both: managed storage, SLA and low cost from Memory Bank — never-store, deterministic recall,",
           font=font(22, True), fill=INK)
    d.text((60, 762), "RBAC, audit and clean SQL exit from the Control Plane.", font=font(22, True), fill=INK)
    save(img, "03_hybrid_flow.png")


# ---------------------------------------------------------------- 4. re-validation
def revalidation():
    img, d = canvas()
    title(d, "What Changed on Re-Validation",
          "Several Memory Bank limitations in the original assessment were wrong or outdated")
    rows = [
        ("MB has no SLA / uptime commitment",
         "GA since Dec 16, 2025 → SLA & SLOs now apply"),
        ("MB can't guarantee deletion / retention",
         "Granular TTL (30 / 90 / 365 d) + DeleteMemory + audit"),
        ("5 key-value pairs cap what can be recalled",
         "5-KV is the scope identifier (namespace), not a memory/recall cap"),
        ("Saves only in the background (racy)",
         "Direct synchronous CreateMemory is also supported"),
    ]
    y = 175
    rh, gap = 108, 22
    for claim, fact in rows:
        rrect(d, [60, y, 740, y + rh], radius=14, fill=RED[0], outline=RED[1], width=3)
        d.text((78, y + 12), "CLAIM", font=font(15, True), fill=RED[1])
        centered(d, [60, y + 24, 740, y + rh], claim, font(20, True), RED[2], gap=3, pad=18)
        arrow(d, (748, y + rh / 2), (832, y + rh / 2), color=INK, width=6, head=16)
        rrect(d, [840, y, 1540, y + rh], radius=14, fill=GREEN[0], outline=GREEN[1], width=3)
        d.text((858, y + 12), "VERIFIED", font=font(15, True), fill=GREEN[1])
        centered(d, [840, y + 24, 1540, y + rh], fact, font(20, True), GREEN[2], gap=3, pad=18)
        y += rh + gap
    rrect(d, [60, y + 6, 1540, y + 92], radius=14, fill=INK)
    centered(d, [60, y + 6, 1540, y + 92],
             "Confirmed MB gaps that remain: no hard never-store denylist · no bulk/SQL export — exactly what the Hybrid adds.",
             font(21, True), "#FFFFFF")
    save(img, "04_revalidation.png")


if __name__ == "__main__":
    three_options()
    gate_matrix()
    hybrid_flow()
    revalidation()
    print("done")
