"""Memory Bank extraction POC: conversations -> managed extraction -> semantic retrieval.

Uses a dedicated Memory Bank (created on the first run, reused after) and calls it directly; the
governed control plane is not involved. Results are scored against the seeded plan in plan.py.

    python scripts/memory_bank_extraction_poc/run_poc.py CONVERSATIONS.json OUT_DIR

Environment: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION; optional POC_MEMORY_BANK (resource
name to reuse), POC_REPEATS (search repetitions per query, default 5).
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import agentplatform

sys.path.insert(0, str(Path(__file__).parent))
from plan import FACTS, NOISE, QUERIES  # noqa: E402

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODELS = f"projects/{PROJECT}/locations/{LOCATION}/publishers/google/models"
# Memory Bank rejects Gemini 2.5 models for extraction; gemini-3.5-flash is served from the
# global location, not us-central1.
EXTRACTION_MODEL = os.environ.get("POC_EXTRACTION_MODEL", "gemini-3.5-flash")
EXTRACTION_LOCATION = os.environ.get("POC_EXTRACTION_LOCATION", "global")

# The "shopping assistant" instruction lives in the topic descriptions: Memory Bank extracts only
# what these topics describe.
TOPICS = {
    "grocery_brand_preferences": "Brands the user prefers, is loyal to or refuses, per product "
    "category (milk, yogurt, bread, pasta sauce, coffee...). When the user switches brand, keep "
    "only the new brand as current.",
    "diet_and_meal_patterns": "Stable eating patterns and recurring meal-planning preferences, "
    "and foods or ingredients the user dislikes. Not one-off meals or food for other people.",
    "budget_and_value": "The user's grocery budget and where they choose store brands or cheaper "
    "options.",
    "recurring_purchases": "Items the user buys regularly and preferred package sizes.",
    "substitution_rules": "Substitutions the user accepts or refuses when an item is unavailable.",
    "household": "Household size and who the user shops for.",
}
EXCLUSIONS = (
    " Ignore one-time orders for events or other people, store complaints, store hours and "
    "medical conditions."
)


def memory_config() -> dict:
    return {
        "generation_config": {
            "model": f"projects/{PROJECT}/locations/{EXTRACTION_LOCATION}"
            f"/publishers/google/models/{EXTRACTION_MODEL}"
        },
        "similarity_search_config": {"embedding_model": f"{MODELS}/text-embedding-005"},
        "unstructured_memory_configs": [
            {
                "scope_keys": ["user_id"],
                "enable_third_person_memories": True,
                "memory_topics": [
                    {"custom_memory_topic": {"label": label, "description": text + EXCLUSIONS}}
                    for label, text in TOPICS.items()
                ],
            }
        ],
    }


def bank_name(client) -> str:
    if os.environ.get("POC_MEMORY_BANK"):
        # Re-apply the config so an existing bank always runs with the settings above. A Memory
        # Bank is a reasoning engine; its config is the context spec's memory_bank_config.
        name = os.environ["POC_MEMORY_BANK"]
        config = memory_config()
        config["customization_configs"] = config.pop("unstructured_memory_configs")
        client.runtimes.update(
            name=name, config={"context_spec": {"memory_bank_config": config}}
        )
        return name
    bank = client.memory_banks.create(
        managed_semantic_memory_config=memory_config(),
        config={
            "display_name": "grocery-extraction-poc",
            "description": "Memory Bank extraction POC; not used by the governed platform.",
        },
    )
    return bank.name


def all_facts(client, name: str, scope: dict[str, str]) -> list[str]:
    retrieved = client.memory_banks.memories.retrieve(
        name=name, scope=scope, simple_retrieval_params={"page_size": 100}
    )
    return [item.memory.fact for item in retrieved]


def found(texts: list[str], keywords: list[str]) -> list[str]:
    return [text for text in texts if any(word in text.lower() for word in keywords)]


def main() -> None:
    sessions = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    repeats = int(os.environ.get("POC_REPEATS", "5"))
    client = agentplatform.Client(project=PROJECT, location=LOCATION)
    name = bank_name(client)
    (out / "memory_bank.txt").write_text(name + "\n")
    scope = {"user_id": f"poc-maya-{int(time.time())}"}
    print("bank", name, "scope", scope, flush=True)

    generation_seconds, before_switch = [], []
    for session in sessions:
        events = [
            {"content": {"role": m["role"], "parts": [{"text": m["text"]}]}}
            for m in session["messages"]
        ]
        started = time.perf_counter()
        client.memory_banks.memories.generate(
            name=name,
            scope=scope,
            direct_contents_source={"events": events},
            config={"wait_for_completion": True},
        )
        generation_seconds.append(time.perf_counter() - started)
        print(f"session {session['session']:2d} extracted in {generation_seconds[-1]:.1f}s", flush=True)
        if session["session"] == 13:
            before_switch = all_facts(client, name, scope)

    facts = all_facts(client, name, scope)
    queries = []
    for query in QUERIES:
        timings, results = [], []
        for _ in range(repeats):
            started = time.perf_counter()
            results = [
                {"fact": item.memory.fact, "distance": item.distance}
                for item in client.memory_banks.memories.retrieve(
                    name=name,
                    scope=scope,
                    similarity_search_params={"search_query": query["query"], "top_k": 5},
                )
            ]
            timings.append((time.perf_counter() - started) * 1000)
        texts = [item["fact"] for item in results]
        queries.append(
            {
                **query,
                "results": results,
                "expected_found": [w for w in query["expect"] if found(texts, [w])],
                "unwanted_found": [w for w in query["must_not"] if found(texts, [w])],
                "latency_ms": timings,
            }
        )
        print(f"query {query['id']}: {len(results)} results, "
              f"median {statistics.median(timings):.0f} ms", flush=True)

    result = {
        "run_at": datetime.now(UTC).isoformat(),
        "memory_bank": name,
        "extraction_model": EXTRACTION_MODEL,
        "scope": scope,
        "sessions": len(sessions),
        "customer_turns": sum(m["role"] == "user" for s in sessions for m in s["messages"]),
        "generation_seconds": generation_seconds,
        "facts_before_switch": before_switch,
        "facts": facts,
        "fact_scores": [{**f, "matched": found(facts, f["any"])} for f in FACTS],
        "noise_scores": [{**n, "matched": found(facts, n["any"])} for n in NOISE],
        "queries": queries,
    }
    (out / "results.json").write_text(json.dumps(result, indent=2, default=str))
    print("wrote", out / "results.json", "-", len(facts), "facts")


if __name__ == "__main__":
    main()
