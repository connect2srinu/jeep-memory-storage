"""Write the three rounds of conversations (about 100 customer turns each) from plan_rounds.py.

    python scripts/memory_bank_extraction_poc/generate_rounds.py OUT_DIR

Writes OUT_DIR/conversations_round{1,2,3}.json; later runs reuse them.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from plan_rounds import PERSONA, SESSIONS  # noqa: E402

PROMPT = """Write one realistic chat session between a customer and a Kroger grocery shopping
assistant. Customer: {persona}

Exactly {turns} customer messages, each followed by one assistant reply. Short, natural messages,
like a real shopper typing on a phone. Cover these beats in order:
{beats}

How to write each kind of beat:
- EXPLICIT: the customer states it in her own words, as her preference or need.
- IMPLICIT: the assistant offers options and the customer just chooses ("yes", "that one",
  "the Organic Valley"). She must NOT say she prefers, likes, always or usually buys it, and must
  not explain why.
- NOISE: a one-off request or remark; treat it as ordinary.
- TRANSACTION: an ordinary task with nothing personal in it.
Fill the remaining turns with ordinary shopping chat (quantities, confirming the cart, thanks).
Do not add any other brands, diets, people or facts about her.
Return JSON: a list of {{"role": "user" | "model", "text": "..."}} in order."""


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    for round_number, sessions in SESSIONS.items():
        path = out / f"conversations_round{round_number}.json"
        if path.exists():
            print("keeping", path)
            continue
        written = []
        for index, beats in enumerate(sessions, 1):
            turns = 6 if index <= 10 else 5  # 18 sessions -> 100 customer turns
            response = client.models.generate_content(
                model=os.environ.get("POC_WRITER_MODEL", "gemini-2.5-flash"),
                contents=PROMPT.format(
                    persona=PERSONA,
                    turns=turns,
                    beats="\n".join(f"- {kind}: {beat}" for kind, beat in beats),
                ),
                config=types.GenerateContentConfig(
                    temperature=0.4, response_mime_type="application/json"
                ),
            )
            messages = json.loads(response.text)
            written.append({"session": index, "beats": beats, "messages": messages})
        path.write_text(json.dumps(written, indent=2))
        total = sum(m["role"] == "user" for s in written for m in s["messages"])
        print(f"round {round_number}: {len(written)} sessions, {total} customer turns -> {path}",
              flush=True)


if __name__ == "__main__":
    main()
