"""Write the POC's grocery-assistant conversations from the seeded plan, using Gemini.

Run once; the output file is reused by run_poc.py so every run scores the same conversations.

    python scripts/memory_bank_extraction_poc/generate_conversations.py OUT.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from plan import PERSONA, SESSIONS  # noqa: E402

PROMPT = """Write one realistic chat session between a customer and a Kroger grocery shopping
assistant. Customer: {persona}
In this session the customer: {plan}

Rules:
- Exactly {turns} customer messages, each followed by one assistant reply.
- Mention only what this session's plan says about the customer's preferences; don't add new
  brands, diets or facts about her.
- Natural, short messages, like a real shopper typing on a phone.
Return JSON: a list of {{"role": "user" | "model", "text": "..."}} in order."""


def main() -> None:
    out = Path(sys.argv[1])
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    sessions = []
    for index, plan in enumerate(SESSIONS, 1):
        turns = 6 if index % 3 == 0 else 5  # 18 sessions -> 96 customer turns
        response = client.models.generate_content(
            model=os.environ.get("POC_WRITER_MODEL", "gemini-2.5-flash"),
            contents=PROMPT.format(persona=PERSONA, plan=plan, turns=turns),
            config=types.GenerateContentConfig(
                temperature=0.4, response_mime_type="application/json"
            ),
        )
        messages = json.loads(response.text)
        sessions.append({"session": index, "plan": plan, "messages": messages})
        print(index, sum(m["role"] == "user" for m in messages), "customer turns", flush=True)
    out.write_text(json.dumps(sessions, indent=2))
    total = sum(m["role"] == "user" for s in sessions for m in s["messages"])
    print("wrote", out, "-", len(sessions), "sessions,", total, "customer turns")


if __name__ == "__main__":
    main()
