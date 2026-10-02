"""Write rounds_report.md from run_rounds.py results, adding the extraction model's real token
usage from Cloud Monitoring. Run it at least five minutes after run_rounds.py finishes.

    python scripts/memory_bank_extraction_poc/make_rounds_report.py ROUNDS_DIR
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_usage import token_usage  # noqa: E402
from plan_rounds import NOISE, PREFERENCES, QUERIES  # noqa: E402

# USD per 1M tokens, Vertex AI generative AI pricing (checked 2026-10-02): Gemini 3.5 Flash at the
# global endpoint; Gemini 2.5 Flash. Memory Bank operations: $0.085 per 1M writes, per 3M reads.
PRICES = {"gemini-3.5-flash": (1.50, 9.00), "gemini-2.5-flash": (0.30, 2.50)}
WRITE_PER_OP, READ_PER_OP = 0.085 / 1_000_000, 0.085 / 3_000_000
CHANGE_WORDS = ("switch", "previously", "instead", "no longer", "used to", "replac", "rather than",
                "changed", "now prefer", "moved")


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES[model]
    return tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out


def current(preference: dict, round_number: int):
    """(value, status, keywords) in force after this round, or None if not yet introduced."""
    rounds = [r for r in preference["by_round"] if r <= round_number]
    if not rounds:
        return None
    value, status, keywords = preference["by_round"][max(rounds)]
    return value, (status if max(rounds) == round_number else "persists"), keywords


def score(preference: dict, round_number: int, facts: list[str]) -> dict | None:
    state = current(preference, round_number)
    if state is None:
        return None
    value, status, keywords = state
    lowered = [fact.lower() for fact in facts]
    matched = [facts[i] for i, text in enumerate(lowered) if any(k in text for k in keywords)]
    # After a change, a fact naming the old value (and not the new one or the change) is stale.
    changed = any(s == "changed" for r, (_, s, _) in preference["by_round"].items()
                  if r <= round_number)
    stale = [
        facts[i] for i, text in enumerate(lowered)
        if changed
        and any(k in text for k in preference.get("stale", []))
        and not any(k in text for k in keywords)
        and not any(word in text for word in CHANGE_WORDS)
    ]
    return {"value": value, "status": status, "captured": bool(matched), "matched": matched,
            "stale": stale}


def cell(result: dict | None) -> str:
    if result is None:
        return "—"
    mark = "✓" if result["captured"] and not result["stale"] else ("⚠" if result["stale"] else "✗")
    note = {"changed": " *(changed)*", "new": " *(new)*"}.get(result["status"], "")
    return f"{mark} {result['value']}{note}" + (" — old value still current" if result["stale"] else "")


def main() -> None:
    folder = Path(sys.argv[1])
    data = json.loads((folder / "results_rounds.json").read_text())
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    rounds = data["rounds"]
    for item in rounds:
        start, end = item["extraction_window"]
        end = (datetime.fromisoformat(end.replace("Z", "+00:00")) + timedelta(minutes=2)
               ).strftime("%Y-%m-%dT%H:%M:%SZ")
        item["extraction_tokens"] = token_usage(project, data["extraction_model"], start, end)
    (folder / "results_rounds.json").write_text(json.dumps(data, indent=2, default=str))

    fact_text = {r["round"]: [f["fact"] for f in r["facts"]] for r in rounds}
    after = [f"After round {r['round']}" for r in rounds]
    scores = {p["id"]: {r: score(p, r, fact_text[r]) for r in fact_text} for p in PREFERENCES}
    L = [
        "# Memory Bank Longitudinal POC — "
        + ("Three Rounds" if len(rounds) == 3 else f"Interim ({len(rounds)} of 3 rounds)"),
        "",
        f"Run {data['started_at'][:16].replace('T', ' ')} UTC. One customer, a dedicated Memory "
        f"Bank, {len(rounds)} round(s) of about 100 customer turns each "
        f"({sum(r['customer_turns'] for r in rounds)} in total). Extraction: Memory Bank with "
        f"{data['extraction_model']} and seven shopping-focused memory topics. Retrieval: semantic "
        f"search (top {data['top_k']}) and an answer written by {data['answer_model']} from the "
        "retrieved memories only; the conversations are never sent again. The governed control "
        "plane was not involved.",
        "",
        "## Final comparison chart",
        "",
        "✓ in the profile · ✗ missing · ⚠ old value still stated as current · — not yet mentioned. "
        "**Explicit** = the customer said it; **implicit** = only shown by what she chose.",
        "",
        "| Preference | Type | Before | " + " | ".join(after) + " |",
        "|---|---|---|" + "---|" * len(rounds),
    ]
    for p in PREFERENCES:
        L.append(f"| {p['category']}: {p['id'].replace('_', ' ')} | {p['type']} | — | "
                 + " | ".join(cell(scores[p["id"]][r["round"]]) for r in rounds) + " |")

    L += ["", "## Explicit vs implicit", "",
          "| Type | " + " | ".join(after) + " |", "|---|" + "---|" * len(rounds)]
    for kind in ("explicit", "implicit"):
        row = []
        for r in rounds:
            active = [scores[p["id"]][r["round"]] for p in PREFERENCES if p["type"] == kind]
            active = [s for s in active if s]
            good = sum(s["captured"] and not s["stale"] for s in active)
            row.append(f"{good} of {len(active)}")
        L.append(f"| {kind.title()} | " + " | ".join(row) + " |")
    L += ["", "Changed preferences:", ""]
    for p in PREFERENCES:
        for r in rounds:
            s = scores[p["id"]][r["round"]]
            if s and s["status"] == "changed":
                verdict = ("captured, old value replaced" if s["captured"] and not s["stale"]
                           else "old value still current" if s["stale"] else "not captured")
                L.append(f"- Round {r['round']}, {p['id'].replace('_', ' ')} ({p['type']}): "
                         f"→ {s['value']} — {verdict}")

    L += ["", "## Snapshot progression", "",
          "| | Before | " + " | ".join(after) + " |", "|---|---|" + "---|" * len(rounds),
          f"| Facts stored | {len(data['baseline'])} | "
          + " | ".join(str(len(r["facts"])) for r in rounds) + " |",
          "| Customer turns processed (cumulative) | 0 | "
          + " | ".join(str(sum(x["customer_turns"] for x in rounds[: i + 1]))
                       for i in range(len(rounds))) + " |"]
    topics = sorted({t for r in rounds for f in r["facts"] for t in f["topics"]})
    for topic in topics:
        L.append(f"| {topic.replace('_', ' ')} | 0 | "
                 + " | ".join(str(sum(topic in f["topics"] for f in r["facts"])) for r in rounds)
                 + " |")
    noise_rows = []
    for r in rounds:
        lowered = [f.lower() for f in fact_text[r["round"]]]
        kept = [n["id"] for rn, items in NOISE.items() if rn <= r["round"] for n in items
                if any(any(k in t for k in n["any"]) for t in lowered)]
        noise_rows.append(", ".join(kept) or "none")
    L.append("| One-off details kept (should be none) | — | " + " | ".join(noise_rows) + " |")

    L += ["", "## Retrieval tests (asked after every round, without the conversations)", ""]
    plan = {q["id"]: q for q in QUERIES}
    for r in rounds:
        L += [f"### After round {r['round']}", ""]
        for q in r["queries"]:
            # Score against the current plan, so a corrected expected term re-scores old answers.
            text = q["answer"].lower()
            q["expected"] = plan[q["id"]]["expect"][r["round"]]
            q["expected_found"] = [w for w in q["expected"] if w in text]
            q["unwanted_found"] = [w for w in plan[q["id"]].get("must_not", []) if w in text]
            expected = (f"{len(q['expected_found'])}/{len(q['expected'])} expected terms"
                        + (f", missing {', '.join(sorted(set(q['expected']) - set(q['expected_found'])))}"
                           if len(q["expected_found"]) < len(q["expected"]) else "")
                        if q["expected"] else "no expected terms")
            unwanted = f" · **unwanted: {', '.join(q['unwanted_found'])}**" if q["unwanted_found"] else ""
            L += [f"**{q['query']}** — {expected}{unwanted} · search {q['latency_ms']:.0f} ms", "",
                  "> " + q["answer"].strip().replace("\n", "\n> "), ""]

    L += ["## Tokens and cost", "",
          "Extraction tokens are Memory Bank's real usage of the extraction model, read from Cloud "
          "Monitoring for each round's extraction window (that model is used by nothing else). "
          "Output includes the model's reasoning tokens.", "",
          "| Round | Conversation tokens | Extraction input | Extraction output | Answer input | "
          "Answer output | Memory tokens | Compression (cumulative) | Cost |",
          "|---|---|---|---|---|---|---|---|---|"]
    totals = {"conv": 0, "ein": 0, "eout": 0, "ain": 0, "aout": 0, "cost": 0.0, "writes": 0,
              "reads": 0}
    for r in rounds:
        ein = r["extraction_tokens"].get("input", 0)
        eout = r["extraction_tokens"].get("output", 0)
        ain = sum(q["answer_input_tokens"] for q in r["queries"])
        aout = sum(q["answer_output_tokens"] for q in r["queries"])
        reads = len(r["queries"]) + 1
        round_cost = (cost(data["extraction_model"], ein, eout) + cost(data["answer_model"], ain, aout)
                      + r["generate_calls"] * WRITE_PER_OP + reads * READ_PER_OP)
        for key, value in (("conv", r["conversation_tokens"]), ("ein", ein), ("eout", eout),
                           ("ain", ain), ("aout", aout), ("cost", round_cost),
                           ("writes", r["generate_calls"]), ("reads", reads)):
            totals[key] += value
        ratio = totals["conv"] / r["memory_tokens"] if r["memory_tokens"] else 0
        L.append(f"| {r['round']} | {r['conversation_tokens']:,} | {ein:,} | {eout:,} | {ain:,} | "
                 f"{aout:,} | {r['memory_tokens']:,} | {ratio:.0f} : 1 | ${round_cost:.4f} |")
    L.append(f"| **Total** | **{totals['conv']:,}** | **{totals['ein']:,}** | **{totals['eout']:,}** "
             f"| **{totals['ain']:,}** | **{totals['aout']:,}** | | | **${totals['cost']:.4f}** |")

    extraction_cost = cost(data["extraction_model"], totals["ein"], totals["eout"])
    if totals["ein"] and totals["conv"]:
        out_ratio = totals["eout"] / totals["ein"]
        per_m_conversation = extraction_cost * 1e6 / totals["conv"]
        per_m_input = PRICES[data["extraction_model"]][0] + out_ratio * PRICES[data["extraction_model"]][1]
        L += ["", "### Projection to 1 million tokens", "",
              f"- Extraction read {totals['ein'] / totals['conv']:.1f} input tokens per token of "
              f"conversation (the model also reads its instructions and the existing memories), "
              f"and wrote {out_ratio:.1%} as many output tokens as it read.",
              f"- **Per 1M extraction input tokens:** 1M × ${PRICES[data['extraction_model']][0]:.2f} "
              f"+ {out_ratio * 1e6:,.0f} output × ${PRICES[data['extraction_model']][1]:.2f} per 1M "
              f"= **${per_m_input:.2f}**.",
              f"- **Per 1M tokens of raw conversation:** ${extraction_cost:.4f} × "
              f"(1,000,000 / {totals['conv']:,}) = **${per_m_conversation:.2f}** of extraction.",
              f"- Answers: {totals['ain'] / max(1, sum(len(r['queries']) for r in rounds)):.0f} "
              "input tokens per question on average — only the retrieved memories, not the "
              "conversation history.",
              f"- Memory Bank operations ({totals['writes']} generate calls, {totals['reads']} "
              f"reads) cost ${totals['writes'] * WRITE_PER_OP + totals['reads'] * READ_PER_OP:.6f};"
              " storage of a few dozen short facts is negligible."]
    L += ["", "## Profile snapshots (as returned by Memory Bank)", "",
          f"### Before round 1\n\n{len(data['baseline'])} facts.", ""]
    for r in rounds:
        L += [f"### After round {r['round']} — {len(r['facts'])} facts", ""]
        for topic in topics + ["(no topic)"]:
            items = [f["fact"] for f in r["facts"]
                     if (topic in f["topics"]) or (topic == "(no topic)" and not f["topics"])]
            if items:
                L += [f"**{topic.replace('_', ' ')}**", ""] + [f"- {i}" for i in items] + [""]
    L += ["## Extraction time per session", "",
          "| Round | Median | Max | Timeouts / throttling retried |", "|---|---|---|---|"]
    for r in rounds:
        L.append(f"| {r['round']} | {statistics.median(r['extraction_seconds']):.1f} s | "
                 f"{max(r['extraction_seconds']):.1f} s | {len(r.get('extraction_retries', []))} |")
    L += ["", "Scoring is keyword based against the planted ground truth in `plan_rounds.py`; "
          "read the snapshots to confirm. Prices: Vertex AI generative AI pricing and Gemini "
          "Enterprise Agent Platform pricing, checked 2026-10-02."]
    (folder / "rounds_report.md").write_text("\n".join(L) + "\n")
    print("wrote", folder / "rounds_report.md")


if __name__ == "__main__":
    main()
