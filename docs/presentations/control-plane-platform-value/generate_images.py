#!/usr/bin/env python3
"""Generate the slide diagrams (PNG) for the Control Plane platform-value deck.

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

# palette
INK = "#1F2937"
MUTED = "#6B7280"
BG = "#FFFFFF"
BAND = "#F3F4F6"
BLUE = ("#DBEAFE", "#2563EB", "#1E40AF")      # agent / business
PURPLE = ("#EDE9FE", "#7C3AED", "#5B21B6")    # control plane (hero)
TEAL = ("#CCFBF1", "#0D9488", "#0F766E")      # gcp managed
RED = ("#FEE2E2", "#DC2626", "#991B1B")       # problem
GREEN = ("#D1FAE5", "#059669", "#065F46")     # good
AMBER = ("#FEF3C7", "#D97706", "#92400E")     # accent


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
    lines = wrap(d, text, fnt, (x1 - x0) - 2 * pad)
    lh = fnt.size + gap
    total = lh * len(lines) - gap
    ty = y0 + ((y1 - y0) - total) / 2
    for ln in lines:
        lw = d.textlength(ln, font=fnt)
        d.text((x0 + ((x1 - x0) - lw) / 2, ty), ln, font=fnt, fill=fill)
        ty += lh


def title(d, text, sub=None):
    d.text((60, 44), text, font=font(46, True), fill=INK)
    if sub:
        d.text((62, 104), sub, font=font(24), fill=MUTED)


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


def chips(d, box, labels, color, fnt, cols, ch=64, gap=14):
    x0, y0, x1, y1 = box
    cw = (x1 - x0 - gap * (cols - 1)) / cols
    for i, lab in enumerate(labels):
        r, c = divmod(i, cols)
        cx = x0 + c * (cw + gap)
        cy = y0 + r * (ch + gap)
        rrect(d, [cx, cy, cx + cw, cy + ch], radius=12, fill=color[0], outline=color[1], width=2)
        centered(d, [cx, cy, cx + cw, cy + ch], lab, fnt, color[2], gap=2, pad=8)


def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path)
    print("wrote", path)


# ---------------------------------------------------------------- 1. duplication tax
def duplication_tax():
    img, d = canvas()
    title(d, "The Duplication Tax: Every Agent Rebuilds the Platform")
    caps = ["Memory", "Security", "Observability", "Guardrails", "Lifecycle"]

    d.text((70, 150), "BEFORE — N agents × M capabilities", font=font(26, True), fill=RED[2])
    for a in range(3):
        ax = 70 + a * 210
        rrect(d, [ax, 200, ax + 180, 250], radius=10, fill=BLUE[0], outline=BLUE[1], width=2)
        centered(d, [ax, 200, ax + 180, 250], f"Agent {a + 1}", font(20, True), BLUE[2])
        for i, c in enumerate(caps):
            cy = 262 + i * 62
            rrect(d, [ax, cy, ax + 180, cy + 52], radius=8, fill=RED[0], outline=RED[1], width=2)
            centered(d, [ax, cy, ax + 180, cy + 52], c, font(18), RED[2])
    d.text((70, 600), "Same plumbing built and maintained many times → cost,",
           font=font(20), fill=MUTED)
    d.text((70, 628), "inconsistent governance, slow delivery.", font=font(20), fill=MUTED)

    arrow(d, (720, 430), (830, 430), color=INK, width=8, head=24)

    d.text((880, 150), "AFTER — one platform, reused by all", font=font(26, True), fill=GREEN[2])
    for a in range(3):
        ax = 880 + a * 210
        rrect(d, [ax, 210, ax + 180, 300], radius=10, fill=BLUE[0], outline=BLUE[1], width=2)
        centered(d, [ax, 210, ax + 180, 300], f"Agent {a + 1}\nbusiness logic", font(18, True), BLUE[2])
    arrow(d, (1130, 320), (1130, 360), color=MUTED, width=5, head=14)
    rrect(d, [880, 370, 1510, 470], radius=16, fill=GREEN[0], outline=GREEN[1], width=3)
    centered(d, [880, 370, 1510, 470], "Control Plane — shared enterprise platform", font(24, True), GREEN[2])
    chips(d, [880, 486, 1510, 486 + 64], caps, PURPLE, font(17), cols=5, ch=52)
    d.text((880, 600), "Build once, consume everywhere. New agents inherit", font=font(20), fill=MUTED)
    d.text((880, 628), "the platform on day one.", font=font(20), fill=MUTED)
    save(img, "01_duplication_tax.png")


# ---------------------------------------------------------------- 2. three layers
def three_layer():
    img, d = canvas()
    title(d, "Complement GCP, Don't Replace It")
    # business
    rrect(d, [180, 150, 1420, 268], radius=18, fill=BLUE[0], outline=BLUE[1], width=3)
    d.text((210, 168), "BUSINESS / AGENT LAYER   — what the business builds", font=font(24, True), fill=BLUE[2])
    chips(d, [210, 210, 1390, 210 + 46], ["Prompts", "Domain tools", "Workflows", "Agent logic"], BLUE, font(18), 4, ch=46)
    arrow(d, (800, 292), (800, 322), color=INK, width=6, head=16)
    d.text((820, 292), "simple, self-service interfaces", font=font(18), fill=MUTED)
    # control plane
    rrect(d, [180, 336, 1420, 556], radius=18, fill=PURPLE[0], outline=PURPLE[1], width=4)
    d.text((210, 352), "CONTROL PLANE — ENTERPRISE ABSTRACTION LAYER   (build once)", font=font(24, True), fill=PURPLE[2])
    chips(d, [210, 398, 1390, 398 + 132],
          ["Governance & Compliance", "Security & Identity", "Memory & Knowledge",
           "Observability & Eval", "Model & Runtime", "Lifecycle & Environment",
           "Discovery & Config", "Guardrails & Policy"], PURPLE, font(17), 4, ch=58)
    arrow(d, (800, 580), (800, 610), color=INK, width=6, head=16)
    d.text((820, 580), "abstracts, governs, orchestrates", font=font(18), fill=MUTED)
    # gcp
    rrect(d, [180, 624, 1420, 742], radius=18, fill=TEAL[0], outline=TEAL[1], width=3)
    d.text((210, 640), "GCP MANAGED PLATFORM SERVICES   — the managed engine", font=font(24, True), fill=TEAL[2])
    chips(d, [210, 682, 1390, 682 + 46],
          ["Gemini / Runtime", "Memory Bank", "Eval Service", "Cloud Run", "IAM / Secrets"], TEAL, font(17), 5, ch=46)
    d.text((180, 774), "GCP provides the managed AI services; the Control Plane turns them into an enterprise-ready agent platform.",
           font=font(22, True), fill=INK)
    save(img, "02_three_layer.png")


# ---------------------------------------------------------------- 3. capability domains
def capability_domains():
    img, d = canvas()
    title(d, "One Platform, Seven Capability Domains")
    domains = [
        ("Governance & Compliance", "Guardrails · sensitivity · consent/DSR · audit"),
        ("Security & Identity", "Enterprise IdP · authZ · secrets · tool access"),
        ("Memory & Knowledge", "Domains · schemas · resolution · topics · RAG"),
        ("Observability & Evaluation", "Tracing · eval orchestration · redact & route"),
        ("Model & Runtime", "Model gateway · quota/resilience · cost · cache"),
        ("Lifecycle & Environment", "Register · version · Dev→UAT→Prod · canary"),
        ("Discovery & Configuration", "Agent registry · tool catalog · dynamic config"),
    ]
    cols, cw, chh, gx, gy, x0, y0 = 4, 350, 180, 22, 26, 60, 170
    for i, (name, sub) in enumerate(domains):
        r, c = divmod(i, cols)
        x = x0 + c * (cw + gx)
        y = y0 + r * (chh + gy)
        rrect(d, [x, y, x + cw, y + chh], radius=16, fill=PURPLE[0], outline=PURPLE[1], width=3)
        d.text((x + 20, y + 20), f"{i + 1}", font=font(30, True), fill=PURPLE[1])
        centered(d, [x + 54, y + 14, x + cw - 12, y + 78], name, font(23, True), PURPLE[2], gap=2, pad=6)
        for j, ln in enumerate(wrap(d, sub, font(18), cw - 40)):
            d.text((x + 20, y + 96 + j * 26), ln, font=font(18), fill=MUTED)
    # 8th slot: message
    x = x0 + 3 * (cw + gx)
    y = y0 + 1 * (chh + gy)
    rrect(d, [x, y, x + cw, y + chh], radius=16, fill=GREEN[0], outline=GREEN[1], width=3)
    centered(d, [x, y, x + cw, y + chh],
             "Each is a reusable service — consumed by agents, not rebuilt.", font(21, True), GREEN[2])
    save(img, "03_capability_domains.png")


# ---------------------------------------------------------------- 4. memory abstraction
def memory_abstraction():
    img, d = canvas()
    title(d, "Example: Memory as a Governed Enterprise Capability")
    # gcp raw
    rrect(d, [80, 250, 430, 560], radius=18, fill=TEAL[0], outline=TEAL[1], width=3)
    centered(d, [80, 262, 430, 320], "GCP Memory Bank", font(26, True), TEAL[2])
    centered(d, [80, 330, 430, 540], "Managed store + retrieval.\nRaw capability — no enterprise model.", font(20), TEAL[2])
    arrow(d, (440, 405), (560, 405), color=INK, width=8, head=22)
    # control plane
    rrect(d, [560, 170, 1060, 660], radius=20, fill=PURPLE[0], outline=PURPLE[1], width=4)
    centered(d, [560, 186, 1060, 240], "Control Plane — memory abstraction", font(24, True), PURPLE[2])
    bullets(d, 590, 250, [
        "Domains · scopes · schemas · preference catalogs",
        "Sensitivity classification · memory topics",
        "Resolution & prioritization (session / explicit / long-term)",
        "Per-agent read/write governance",
        "Consent & right-to-be-forgotten",
        "Central configuration & administration",
    ], font(19), PURPLE[2], dot=PURPLE[1], gap=12, max_w=440)
    arrow(d, (1070, 405), (1190, 405), color=INK, width=8, head=22)
    # agent
    rrect(d, [1190, 250, 1520, 560], radius=18, fill=BLUE[0], outline=BLUE[1], width=3)
    centered(d, [1190, 262, 1520, 320], "Agent", font(26, True), BLUE[2])
    centered(d, [1190, 330, 1520, 540], "Simple interface:\nresolve()  ·  save()\nNo enterprise rules in agent code.", font(20), BLUE[2])
    d.text((80, 700), "A consistent enterprise memory model on top of the managed GCP service — built once.",
           font=font(22, True), fill=INK)
    save(img, "04_memory_abstraction.png")


# ---------------------------------------------------------------- 5. eval / observability
def eval_observability():
    img, d = canvas()
    title(d, "Example: Telemetry — Emit Once, Governed Routing")
    rrect(d, [80, 300, 400, 560], radius=18, fill=BLUE[0], outline=BLUE[1], width=3)
    centered(d, [80, 312, 400, 372], "Agent", font(26, True), BLUE[2])
    centered(d, [80, 380, 400, 540], "Emits once:\ntraces · prompts ·\nresponses · eval results", font(20), BLUE[2])
    arrow(d, (410, 430), (540, 430), color=INK, width=8, head=22)
    rrect(d, [540, 210, 1010, 650], radius=20, fill=PURPLE[0], outline=PURPLE[1], width=4)
    centered(d, [540, 226, 1010, 280], "Control Plane — telemetry pipeline", font(24, True), PURPLE[2])
    bullets(d, 570, 300, [
        "Redact PII / sensitive data before egress",
        "Apply enterprise data-handling policy",
        "Enrich with org / project / agent / version",
        "Standardize evaluation metadata",
        "Route to the right backend(s)",
    ], font(20), PURPLE[2], dot=PURPLE[1], gap=16, max_w=410)
    for i, (name, col) in enumerate([("Google Cloud\nObservability", TEAL), ("LangSmith", AMBER), ("Other backends", GREEN)]):
        y = 250 + i * 130
        arrow(d, (1020, 430), (1120, y + 45), color=MUTED, width=5, head=14)
        rrect(d, [1130, y, 1520, y + 90], radius=14, fill=col[0], outline=col[1], width=3)
        centered(d, [1130, y, 1520, y + 90], name, font(22, True), col[2])
    d.text((80, 720), "Emit once; the Control Plane decides how and where it is processed — swap backends without touching agents.",
           font=font(22, True), fill=INK)
    save(img, "05_eval_observability.png")


# ---------------------------------------------------------------- 6. value pillars
def value_pillars():
    img, d = canvas()
    title(d, "The Value: Platform Leverage")
    pillars = [
        ("Leverage", "Build a capability once; every agent reuses it."),
        ("Standardization", "One security, memory & compliance model."),
        ("Speed", "Teams ship business logic, not plumbing."),
        ("Governance by default", "Policy & PII enforced centrally, not per team."),
        ("Enterprise visibility", "Cost & audit by Org → Project → Agent → Version."),
    ]
    pw, gap, x0, y0, ph = 280, 22, 60, 190, 420
    cols = [BLUE, TEAL, GREEN, PURPLE, AMBER]
    for i, (name, sub) in enumerate(pillars):
        x = x0 + i * (pw + gap)
        col = cols[i]
        rrect(d, [x, y0, x + pw, y0 + ph], radius=18, fill=col[0], outline=col[1], width=3)
        d.ellipse([x + pw / 2 - 34, y0 + 34, x + pw / 2 + 34, y0 + 102], fill=col[1])
        centered(d, [x + pw / 2 - 34, y0 + 34, x + pw / 2 + 34, y0 + 102], str(i + 1), font(34, True), "#FFFFFF")
        centered(d, [x, y0 + 120, x + pw, y0 + 200], name, font(24, True), col[2], gap=2, pad=10)
        centered(d, [x, y0 + 210, x + pw, y0 + ph - 20], sub, font(19), INK, pad=16)
    rrect(d, [60, 700, 1540, 800], radius=16, fill=INK)
    centered(d, [60, 700, 1540, 800],
             "GCP provides the managed AI services; the Control Plane turns them into an enterprise-ready agent platform.",
             font(24, True), "#FFFFFF")
    save(img, "06_value_pillars.png")


if __name__ == "__main__":
    duplication_tax()
    three_layer()
    capability_domains()
    memory_abstraction()
    eval_observability()
    value_pillars()
    print("done")
