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


# ---------------------------------------------------------------- 5. scalability
def scalability():
    img, d = canvas()
    title(d, "Scalability — a Known Ceiling, With Headroom",
          "The Vertex quota is the ceiling; it is raisable (Google-agreed) and mitigations keep us under it")
    # quota panel (left)
    rrect(d, [60, 170, 740, 470], radius=18, fill=TEAL[0], outline=TEAL[1], width=3)
    d.text((84, 188), "Vertex Memory Bank quota (per project · region)", font=font(22, True), fill=TEAL[2])
    bullets(d, 90, 238, [
        "Reads: 300 / min   ·   Writes: 100 / min  (current default)",
        "Google-approved 10x increase → ~3,000 reads / min",
        "Writes also consume read quota (each write retrieves first)",
        "DSQ / Provisioned Throughput available for guaranteed capacity",
    ], font(19), TEAL[2], dot=TEAL[1], gap=14, max_w=620)
    # headroom bars
    d.text((90, 388), "Steady-state load sits well under the raised ceiling:", font=font(18), fill=INK)
    for i, (lab, frac, col) in enumerate([
        ("typical load", 0.08, GREEN[1]), ("300/min (today)", 0.10, AMBER[1]),
        ("~3,000/min (approved)", 1.0, TEAL[1])]):
        y = 418 + i * 16
        d.text((92, y - 4), lab, font=font(13), fill=MUTED)
    # simple headroom bar
    rrect(d, [300, 414, 720, 430], radius=8, fill="#E5E7EB")
    rrect(d, [300, 414, 300 + 420 * 0.10, 430], radius=8, fill=AMBER[1])
    rrect(d, [300, 414, 300 + 420 * 0.02, 430], radius=8, fill=GREEN[1])
    d.text((300, 436), "typical ▮  300/min ▮  headroom to ~3,000/min ────────", font=font(13), fill=MUTED)
    # mitigations (right)
    d.text((780, 178), "Mitigations that keep reads bounded", font=font(22, True), fill=PURPLE[2])
    mits = [
        ("1. Lazy per-member resolve", "Only the referenced member, not the whole household every turn"),
        ("2. Session-cached snapshot", "Resolve once per session; reuse across turns"),
        ("3. Per-LOB dedicated Memory Bank", "Heavy / regulated lines get their own quota bucket"),
    ]
    for i, (h, sub) in enumerate(mits):
        y = 224 + i * 92
        rrect(d, [780, y, 1540, y + 78], radius=14, fill=PURPLE[0], outline=PURPLE[1], width=3)
        d.text((800, y + 14), h, font=font(20, True), fill=PURPLE[2])
        for j, ln in enumerate(wrap(d, sub, font(17), 720)):
            d.text((800, y + 44 + j * 22), ln, font=font(17), fill=INK)
    rrect(d, [60, 720, 1540, 812], radius=16, fill=INK)
    centered(d, [60, 720, 1540, 812],
             "The ceiling is raisable and already agreed (10x); lazy resolve + caching keep steady-state load far below it.",
             font(22, True), "#FFFFFF")
    save(img, "05_scalability.png")


# ---------------------------------------------------------------- 6. roadmap
def roadmap():
    img, d = canvas()
    title(d, "Delivery Timeline", "Foundation is done; hardening and scale-out are scoped next")
    phases = [
        ("PHASE 0 — Foundation", "DONE", GREEN, [
            "Dual memory (short-term + governed long-term)",
            "Governance: sensitivity, never-store, RBAC",
            "Deletion: forget (per-member / household cascade) + purge",
            "Observability & audit events",
            "Household + per-member memory",
            "Thin-agent onboarding",
        ]),
        ("PHASE 1 — Hardening", "NEXT", BLUE, [
            "Quota increase to 10x (Google-agreed)",
            "429 → 503 + Retry-After handling",
            "Per-LOB Memory Bank strategy",
            "Admin UI for the household roster",
            "SLA / DR posture confirmation",
        ]),
        ("PHASE 2 — Quality", "PLANNED", PURPLE, [
            "Memory-quality / evaluation harness",
            "Schema registry + change notification",
            "Conflict-resolution hardening",
            "Cost & usage dashboards",
        ]),
    ]
    # timeline arrow
    arrow(d, (70, 200), (1540, 200), color=MUTED, width=5, head=18)
    cw, gap, x0 = 480, 30, 60
    for i, (name, tag, col, items) in enumerate(phases):
        x = x0 + i * (cw + gap)
        d.ellipse([x + 20, 190, x + 40, 210], fill=col[1])
        rrect(d, [x, 232, x + cw, 300], radius=14, fill=col[0], outline=col[1], width=3)
        d.text((x + 20, 246), name, font=font(21, True), fill=col[2])
        rrect(d, [x + cw - 118, 244, x + cw - 16, 288], radius=10, fill=col[1])
        centered(d, [x + cw - 118, 244, x + cw - 16, 288], tag, font(16, True), "#FFFFFF")
        y = 330
        for it in items:
            d.ellipse([x + 8, y + 7, x + 18, y + 17], fill=col[1])
            for j, ln in enumerate(wrap(d, it, font(18), cw - 40)):
                d.text((x + 30, y + j * 22), ln, font=font(18), fill=INK)
            y += max(1, len(wrap(d, it, font(18), cw - 40))) * 22 + 14
    save(img, "06_roadmap.png")


# ---------------------------------------------------------------- 7. adoption
def adoption():
    img, d = canvas()
    title(d, "Adoption by Application — Thin Agent",
          "Apps build business logic; they inherit all memory plumbing from the platform")
    rrect(d, [60, 170, 770, 560], radius=18, fill=BLUE[0], outline=BLUE[1], width=3)
    d.text((88, 188), "The application OWNS", font=font(23, True), fill=BLUE[2])
    bullets(d, 96, 244, [
        "Prompts & instructions",
        "Domain tools & workflows",
        "Business logic",
        "Which domain it serves (config)",
    ], font(21), BLUE[2], dot=BLUE[1], gap=22, max_w=630)
    rrect(d, [830, 170, 1540, 560], radius=18, fill=PURPLE[0], outline=PURPLE[1], width=4)
    d.text((858, 188), "The application INHERITS (platform)", font=font(23, True), fill=PURPLE[2])
    bullets(d, 866, 244, [
        "Resolve + inject snapshot (2 callbacks)",
        "Memory tools (read / save / dynamic)",
        "Governance, never-store, RBAC, sensitivity",
        "Deletion, retention, audit",
        "Scaling: quota, caching, per-LOB isolation",
    ], font(21), PURPLE[2], dot=PURPLE[1], gap=18, max_w=630)
    # onboarding steps
    steps = ["Register agent\n+ grants", "Set 6 env vars", "Reuse client +\n2 callbacks + 3 tools", "Ship"]
    sw, gap, x0, y = 340, 30, 60, 610
    for i, s in enumerate(steps):
        x = x0 + i * (sw + gap)
        rrect(d, [x, y, x + sw, y + 90], radius=14, fill=GREEN[0], outline=GREEN[1], width=3)
        centered(d, [x, y, x + sw, y + 90], s, font(20, True), GREEN[2], gap=2)
        if i < len(steps) - 1:
            arrow(d, (x + sw + 2, y + 45), (x + sw + gap - 2, y + 45), color=INK, width=5, head=13)
    d.text((60, 730), "Onboarding is hours, not weeks — no per-app memory plumbing, no schema knowledge in the agent.",
           font=font(22, True), fill=INK)
    save(img, "07_adoption.png")


# ---------------------------------------------------------------- 8. extraction flow
def extraction_flow():
    img, d = canvas()
    title(d, "Where Memory Extraction Happens — Today",
          "The agent's own LLM detects & extracts · the Control Plane validates & governs · Memory Bank stores")
    cols = [(60, 270), (330, 760), (840, 1240), (1300, 1545)]
    heads = [("1  CUSTOMER", INK), ("2  AGENT LAYER (ADK)", BLUE[2]),
             ("3  CONTROL PLANE API", PURPLE[2]), ("4  MEMORY BANK", TEAL[2])]
    for (x0, _), (lab, col) in zip(cols, heads):
        d.text((x0, 158), lab, font=font(17, True), fill=col)

    # 1. customer
    rrect(d, [60, 200, 270, 420], radius=16, fill=BAND, outline=MUTED, width=2)
    centered(d, [60, 200, 270, 420],
             "“We only buy organic. Timmy is allergic to peanuts.”", font(19, True), INK, gap=5)
    arrow(d, (275, 300), (325, 300), color=INK, width=6, head=15)

    # 2. agent — extraction happens here
    rrect(d, [330, 200, 760, 560], radius=18, fill=BLUE[0], outline=BLUE[1], width=4)
    d.text((352, 216), "Detects & extracts", font=font(22, True), fill=BLUE[2])
    rrect(d, [352, 254, 640, 288], radius=10, fill=AMBER[1])
    centered(d, [352, 254, 640, 288], "EXTRACTION HAPPENS HERE", font(15, True), "#FFFFFF", pad=6)
    bullets(d, 356, 306, [
        "Session snapshot injected each turn: writable preferences, topics, household roster",
        "The same LLM call that picks shopping tools decides: is this a preference?",
        "Extracts attribute + value + person → save_preference(…)",
    ], font(18), BLUE[2], dot=BLUE[1], gap=12, max_w=370)

    # agent branch: normal shopping never touches memory
    arrow(d, (545, 562), (545, 604), color=MUTED, width=5, head=13)
    rrect(d, [330, 608, 760, 690], radius=14, fill=BAND, outline=MUTED, width=2)
    centered(d, [330, 608, 760, 690],
             "~90% of turns: normal shopping\nNo Control Plane / Memory Bank call", font(18, True), MUTED, gap=4)

    # agent -> control plane, and the confirmation turn back
    arrow(d, (765, 300), (835, 300), color=INK, width=6, head=15)
    d.text((770, 312), "save", font=font(14, True), fill=INK)
    arrow(d, (835, 470), (765, 470), color=AMBER[1], width=5, head=14)
    d.text((770, 480), "confirm", font=font(14, True), fill=AMBER[2])

    # 3. control plane — validation & governance
    rrect(d, [840, 200, 1240, 560], radius=18, fill=PURPLE[0], outline=PURPLE[1], width=4)
    d.text((862, 216), "Validates & governs", font=font(22, True), fill=PURPLE[2])
    y = bullets(d, 866, 262, [
        "Attribute in the preference catalog and the agent's grant",
        "Scope: household / member resolution",
        "Never-store + sensitivity screen",
        "Purpose check · audit event",
    ], font(17), PURPLE[2], dot=PURPLE[1], gap=10, max_w=345)
    bullets(d, 866, y, [
        "New member or health data → needs_confirmation; agent asks the customer",
    ], font(17), AMBER[2], dot=AMBER[1], gap=10, max_w=345)
    arrow(d, (1245, 300), (1295, 300), color=INK, width=6, head=15)

    # 4. memory bank — storage only
    rrect(d, [1300, 200, 1545, 420], radius=16, fill=TEAL[0], outline=TEAL[1], width=3)
    d.text((1320, 216), "Stores only", font=font(22, True), fill=TEAL[2])
    bullets(d, 1318, 262, [
        "CreateMemory: typed fact, exact scope",
        "Read back by scope on resolve",
    ], font(16), TEAL[2], dot=TEAL[1], gap=10, max_w=195)
    rrect(d, [1300, 440, 1545, 560], radius=14, fill=BAND, outline=MUTED, width=2)
    centered(d, [1300, 440, 1545, 560],
             "Managed extraction (GenerateMemories) is OFF — no ungoverned memories",
             font(16, True), MUTED, gap=4, pad=12)

    # read path
    rrect(d, [840, 608, 1545, 690], radius=14, fill=BAND, outline=PURPLE[1], width=2)
    centered(d, [840, 608, 1545, 690],
             "Read path: resolve once per session → snapshot cached in the agent → injected every turn (no per-turn API call)",
             font(17, True), PURPLE[2], gap=4, pad=18)

    rrect(d, [60, 730, 1545, 830], radius=16, fill=INK)
    centered(d, [60, 730, 1545, 830],
             "Extraction rides on the agent's existing LLM call — 0 extra model calls. Control Plane + Memory Bank "
             "are called only on memory turns, and every write is validated centrally.",
             font(21, True), "#FFFFFF", gap=6, pad=30)
    save(img, "08_extraction_flow.png")


if __name__ == "__main__":
    three_options()
    gate_matrix()
    hybrid_flow()
    revalidation()
    scalability()
    roadmap()
    adoption()
    extraction_flow()
    print("done")
