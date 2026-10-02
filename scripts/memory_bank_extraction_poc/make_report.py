"""Write report.md from a run_poc.py results.json.

    python scripts/memory_bank_extraction_poc/make_report.py OUT_DIR
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def main() -> None:
    out = Path(sys.argv[1])
    r = json.loads((out / "results.json").read_text())
    facts = r["facts"]
    stable = [f for f in r["fact_scores"] if not f.get("superseded")]
    kept = [f for f in stable if f["matched"]]
    noise_kept = [n for n in r["noise_scores"] if n["matched"]]
    old_milk = next(f for f in r["fact_scores"] if f["id"] == "milk_old")
    # Organic Valley is "still current" only in a fact that doesn't also record the switch.
    old_milk = {**old_milk, "matched": [t for t in old_milk["matched"] if "horizon" not in t.lower()]}
    latencies = [ms for q in r["queries"] for ms in q["latency_ms"]]
    gen = r["generation_seconds"]

    lines = [
        "# Memory Bank Extraction POC — Results",
        "",
        f"Run {r['run_at'][:16].replace('T', ' ')} UTC against a dedicated Memory Bank "
        f"(`{r['memory_bank'].rsplit('/', 1)[-1]}`), one customer, {r['sessions']} sessions, "
        f"{r['customer_turns']} customer turns. Extraction model {r['extraction_model']}, embeddings "
        "text-embedding-005, six shopping-focused memory topics. The governed control plane was "
        "not involved.",
        "",
        "## Scorecard",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Planted stable preferences captured | {len(kept)} of {len(stable)} |",
        f"| Noise kept (should be 0) | {len(noise_kept)} of {len(r['noise_scores'])}"
        + (f" — {', '.join(n['id'] for n in noise_kept)}" if noise_kept else "") + " |",
        f"| Milk switch: Horizon is current | {'yes' if next(f for f in r['fact_scores'] if f['id'] == 'milk_new')['matched'] else 'no'} |",
        f"| Milk switch: Organic Valley still stored as current | {'yes — ' + '; '.join(old_milk['matched']) if old_milk['matched'] else 'no — the old fact was replaced'} |",
        f"| Facts stored at the end | {len(facts)} (from {r['customer_turns']} customer turns) |",
        f"| Extraction time per session | median {statistics.median(gen):.1f} s, max {max(gen):.1f} s |",
        f"| Semantic search latency ({len(latencies)} calls) | p50 {pct(latencies, .5):.0f} ms, "
        f"p95 {pct(latencies, .95):.0f} ms, max {max(latencies):.0f} ms |",
        "",
        "## Targeted queries (top 5, closest first)",
        "",
    ]
    for q in r["queries"]:
        verdict = []
        if q["expect"]:
            verdict.append(f"expected {len(q['expected_found'])}/{len(q['expect'])}"
                           + (f" (missing: {', '.join(set(q['expect']) - set(q['expected_found']))})"
                              if len(q["expected_found"]) < len(q["expect"]) else ""))
        if q["must_not"]:
            verdict.append("unwanted: " + (", ".join(q["unwanted_found"]) or "none"))
        lines += [f"**{q['query']}** — {'; '.join(verdict)} · median "
                  f"{statistics.median(q['latency_ms']):.0f} ms", ""]
        lines += [f"{i}. {item['fact']} *(distance {item['distance']:.3f})*"
                  for i, item in enumerate(q["results"], 1)] or ["(no results)"]
        lines.append("")
    lines += ["## Planted facts", "", "| Planted | Captured as |", "|---|---|"]
    for f in r["fact_scores"]:
        label = f["fact"] + (" *(superseded)*" if f.get("superseded") else "")
        lines.append(f"| {label} | {'<br>'.join(f['matched']) or '**not found**'} |")
    lines += ["", "## Noise (should not be kept)", "", "| Said once | Kept as |", "|---|---|"]
    for n in r["noise_scores"]:
        lines.append(f"| {n['said']} | {'<br>'.join(n['matched']) or 'not kept'} |")
    lines += ["", "## All stored facts", ""] + [f"- {fact}" for fact in facts]
    lines += ["", "## Facts after session 13 (before the milk switch)", ""]
    lines += [f"- {fact}" for fact in r["facts_before_switch"]]
    lines += [
        "",
        "Scoring is keyword based (see `plan.py`); read the stored facts above to confirm. "
        "Latency is measured from this workstation, so it includes network time.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("wrote", out / "report.md")


if __name__ == "__main__":
    main()
