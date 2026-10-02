"""Three-round Memory Bank test: baseline, then three rounds of ~100 customer turns, each followed
by a profile snapshot and retrieval questions answered from the retrieved memories only.

    python scripts/memory_bank_extraction_poc/run_rounds.py MEMORY_BANK ROUNDS_DIR

MEMORY_BANK is the POC bank's resource name (docs/memory-bank-extraction-poc/memory_bank.txt);
its configuration is replaced with the topics below before the run. Each round's extraction time
window is saved so make_rounds_report.py can read the extraction model's token usage from Cloud
Monitoring afterwards (the metrics arrive a few minutes late).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import agentplatform
from google import genai

sys.path.insert(0, str(Path(__file__).parent))
from plan_rounds import QUERIES, SESSIONS  # noqa: E402

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODELS = f"projects/{PROJECT}/locations/{LOCATION}/publishers/google/models"
EXTRACTION_MODEL = "gemini-3.5-flash"  # Memory Bank rejects 2.5; 3.5 is served from "global"
ANSWER_MODEL = os.environ.get("POC_ANSWER_MODEL", "gemini-2.5-flash")
TOP_K = int(os.environ.get("POC_TOP_K", "8"))
ATTEMPTS = 5
TRANSIENT = ("DEADLINE_EXCEEDED", "throttled", "RESOURCE_EXHAUSTED", "UNAVAILABLE")

# Memory Bank has no free-text summary prompt; the "compact personalization profile for a
# shopping assistant" instruction is expressed as these topics.
TOPICS = {
    "brand_preferences": "Brands the user prefers or refuses per product category, whether "
    "stated or shown by repeatedly choosing the same brand. When the user switches brand, record "
    "the new brand as current and note the change.",
    "diet_and_meal_patterns": "Stable eating patterns and meal-planning preferences (e.g. "
    "high-protein weekdays, Mediterranean meals, low-sodium or low-sugar choices), including "
    "patterns shown by repeated choices. Record changes, keeping only the current pattern as "
    "current.",
    "product_restrictions_and_dislikes": "Foods or ingredients the household must avoid (such as "
    "a food allergy, recorded as the food to avoid) and products, flavors or ingredients the user "
    "dislikes.",
    "budget_and_value": "The user's grocery budget and where they choose store brands or cheaper "
    "options.",
    "recurring_purchases": "Items the user buys repeatedly and preferred package sizes.",
    "organic_and_quality": "Where the user wants organic or specific quality, and where not.",
    "household": "Household size and who the user shops for.",
}
EXCLUSIONS = (
    " Keep durable preferences and recurring patterns; ignore one-time orders for events or "
    "other people, store complaints, prices asked once, order status and pickup times, and "
    "medical conditions or symptoms."
)


def configure(client, name: str) -> None:
    """Replace the bank's configuration (a Memory Bank is a reasoning engine; its config is the
    context spec's memory_bank_config)."""
    client.runtimes.update(
        name=name,
        config={
            "context_spec": {
                "memory_bank_config": {
                    "generation_config": {
                        "model": f"projects/{PROJECT}/locations/global/publishers/google/models/"
                        f"{EXTRACTION_MODEL}"
                    },
                    "similarity_search_config": {
                        "embedding_model": f"{MODELS}/text-embedding-005"
                    },
                    "customization_configs": [
                        {
                            "scope_keys": ["user_id"],
                            "enable_third_person_memories": True,
                            "memory_topics": [
                                {"custom_memory_topic": {"label": label,
                                                         "description": text + EXCLUSIONS}}
                                for label, text in TOPICS.items()
                            ],
                        }
                    ],
                }
            }
        },
    )


def snapshot(client, name: str, scope: dict[str, str]) -> list[dict]:
    retrieved = client.memory_banks.memories.retrieve(
        name=name, scope=scope, simple_retrieval_params={"page_size": 100}
    )
    return [
        {
            "fact": item.memory.fact,
            "topics": [
                t.custom_memory_topic_label or str(t.managed_memory_topic)
                for t in (item.memory.topics or [])
            ],
        }
        for item in retrieved
    ]


def answer(gemini, question: str, facts: list[str]) -> dict:
    prompt = (
        "You are helping a grocery shopping assistant. Answer the question about the customer "
        "using only these remembered facts; if they don't say, say so. Be brief.\n\nFacts:\n"
        + "\n".join(f"- {fact}" for fact in facts)
        + f"\n\nQuestion: {question}"
    )
    response = gemini.models.generate_content(model=ANSWER_MODEL, contents=prompt)
    usage = response.usage_metadata
    return {
        "text": response.text,
        "input_tokens": usage.prompt_token_count or 0,
        "output_tokens": (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0),
    }


def tokens(gemini, text: str) -> int:
    return gemini.models.count_tokens(model=ANSWER_MODEL, contents=text).total_tokens if text else 0


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    name, rounds_dir = sys.argv[1], Path(sys.argv[2])
    client = agentplatform.Client(project=PROJECT, location=LOCATION)
    gemini = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    if "--resume" in sys.argv:
        # Continue a stopped run: same customer, from the first round not yet saved.
        result = json.loads((rounds_dir / "results_rounds.json").read_text())
        scope = result["scope"]
        print("resuming", scope, "after round", len(result["rounds"]), flush=True)
    else:
        configure(client, name)
        scope = {"user_id": f"poc-rounds-maya-{int(time.time())}"}
        print("bank", name, "scope", scope, flush=True)
        result = {"memory_bank": name, "scope": scope, "extraction_model": EXTRACTION_MODEL,
                  "answer_model": ANSWER_MODEL, "top_k": TOP_K, "started_at": now(),
                  "baseline": snapshot(client, name, scope), "rounds": []}
        print("round 0 baseline:", len(result["baseline"]), "facts", flush=True)

    done = {item["round"] for item in result["rounds"]}
    for round_number in (number for number in SESSIONS if number not in done):
        sessions = json.loads((rounds_dir / f"conversations_round{round_number}.json").read_text())
        conversation_text = "\n".join(
            f"{m['role']}: {m['text']}" for s in sessions for m in s["messages"]
        )
        window_start, seconds, retries = now(), [], []
        for session in sessions:
            started = time.perf_counter()
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    client.memory_banks.memories.generate(
                        name=name,
                        scope=scope,
                        direct_contents_source={"events": [
                            {"content": {"role": m["role"], "parts": [{"text": m["text"]}]}}
                            for m in session["messages"]
                        ]},
                        config={"wait_for_completion": True},
                    )
                    break
                except RuntimeError as error:
                    # The extraction model sometimes times out or is throttled; retry those.
                    if attempt == ATTEMPTS or not any(m in str(error) for m in TRANSIENT):
                        raise
                    retries.append(session["session"])
                    reason = next(m for m in TRANSIENT if m in str(error))
                    print(f"round {round_number} session {session['session']}: {reason}, "
                          f"retry {attempt}", flush=True)
                    time.sleep(30 * attempt)
            seconds.append(time.perf_counter() - started)
        window_end = now()
        facts = snapshot(client, name, scope)
        print(f"round {round_number}: extracted {len(sessions)} sessions -> {len(facts)} facts",
              flush=True)

        queries = []
        for query in QUERIES:
            started = time.perf_counter()
            found = [
                {"fact": item.memory.fact, "distance": item.distance}
                for item in client.memory_banks.memories.retrieve(
                    name=name, scope=scope,
                    similarity_search_params={"search_query": query["query"], "top_k": TOP_K},
                )
            ]
            latency_ms = (time.perf_counter() - started) * 1000
            reply = answer(gemini, query["query"], [item["fact"] for item in found])
            text = reply["text"].lower()
            queries.append({
                "id": query["id"], "query": query["query"], "retrieved": found,
                "latency_ms": latency_ms, "answer": reply["text"],
                "answer_input_tokens": reply["input_tokens"],
                "answer_output_tokens": reply["output_tokens"],
                "expected": query["expect"][round_number],
                "expected_found": [w for w in query["expect"][round_number] if w in text],
                "unwanted_found": [w for w in query.get("must_not", []) if w in text],
            })
        result["rounds"].append({
            "round": round_number,
            "sessions": len(sessions),
            "customer_turns": sum(m["role"] == "user" for s in sessions for m in s["messages"]),
            "conversation_tokens": tokens(gemini, conversation_text),
            "extraction_window": [window_start, window_end],
            "extraction_seconds": seconds,
            "extraction_retries": retries,
            "generate_calls": len(sessions),
            "facts": facts,
            "memory_tokens": tokens(gemini, "\n".join(f["fact"] for f in facts)),
            "queries": queries,
        })
        (rounds_dir / "results_rounds.json").write_text(json.dumps(result, indent=2, default=str))
    result["finished_at"] = now()
    (rounds_dir / "results_rounds.json").write_text(json.dumps(result, indent=2, default=str))
    print("wrote", rounds_dir / "results_rounds.json", flush=True)


if __name__ == "__main__":
    main()
