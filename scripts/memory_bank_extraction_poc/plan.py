"""Seeded plan for the Memory Bank extraction POC: sessions, planted facts, noise and queries.

Every fact the conversations mention on purpose is listed in FACTS with the words that show it
was captured, so the result can be scored instead of eyeballed.
"""

from __future__ import annotations

PERSONA = (
    "Maya, a Kroger customer who shops for a family of four (two kids, 8 and 11). She plans "
    "meals on Sunday, orders pickup, and is friendly but brief."
)

# Stable facts the summary should keep. "any" = at least one keyword must appear in a memory.
FACTS = [
    {"id": "milk_old", "fact": "Bought Organic Valley milk (sessions 1-13)",
     "any": ["organic valley"], "superseded": True},
    {"id": "milk_new", "fact": "Switched to Horizon organic milk (session 14 on)",
     "any": ["horizon"]},
    {"id": "yogurt", "fact": "Prefers Chobani Greek yogurt", "any": ["chobani"]},
    {"id": "pasta_sauce", "fact": "Prefers Rao's pasta sauce", "any": ["rao"]},
    {"id": "bread", "fact": "Prefers Dave's Killer Bread", "any": ["dave"]},
    {"id": "coffee", "fact": "Buys Private Selection coffee", "any": ["private selection"]},
    {"id": "paper_goods", "fact": "Store brand (Kroger) for paper towels and cleaning supplies",
     "any": ["store brand", "kroger brand", "kroger-brand", "private label"]},
    {"id": "mac_cheese", "fact": "Avoids Kraft mac and cheese, buys Annie's",
     "any": ["annie", "kraft"]},
    {"id": "meal_pattern", "fact": "Vegetarian, high-protein weeknight dinners",
     "any": ["vegetarian", "high-protein", "high protein"]},
    {"id": "household", "fact": "Family of four with two kids",
     "any": ["family of four", "four people", "two kids", "two children", "family of 4"]},
    {"id": "budget", "fact": "Weekly budget around $175; asks for cheaper options on snacks",
     "any": ["175", "budget"]},
    {"id": "pack_size", "fact": "Family-size packs for snacks", "any": ["family-size", "family size", "bulk"]},
    {"id": "staples", "fact": "Weekly staples: eggs, bananas, spinach", "any": ["banana", "spinach", "eggs"]},
    {"id": "substitutions", "fact": "Fage is fine if Chobani is out; never swap Dave's for white bread",
     "any": ["fage", "white bread", "substitut"]},
    {"id": "organic_produce", "fact": "Organic only for berries and leafy greens",
     "any": ["berries", "leafy greens", "organic produce"]},
    {"id": "cilantro", "fact": "Dislikes cilantro", "any": ["cilantro"]},
]

# Things said once that should NOT become long-term memory.
NOISE = [
    {"id": "party", "said": "40 cupcakes for a coworker's retirement party",
     "any": ["cupcake", "retirement"]},
    {"id": "out_of_stock", "said": "complained the Main Street store was out of avocados",
     "any": ["main street", "out of avocado"]},
    {"id": "guest", "said": "gluten-free crackers for a visiting friend",
     "any": ["gluten-free", "gluten free"]},
    {"id": "health", "said": "her doctor said her cholesterol is high (health data)",
     "any": ["cholesterol", "doctor"]},
    {"id": "store_hours", "said": "asked what time the store closes", "any": ["closes", "store hours"]},
]

# One line per session: what Maya does. The generator writes 5-6 customer turns for each.
SESSIONS = [
    "Builds her weekly list: eggs, bananas, spinach, Organic Valley milk, Chobani Greek yogurt. "
    "Mentions she shops for a family of four.",
    "Plans three vegetarian, high-protein weeknight dinners; asks for recipes without cilantro "
    "because she can't stand it.",
    "Searches for pasta sauce; insists on Rao's even though it costs more; adds Dave's Killer Bread.",
    "Asks for cheaper paper towels and dish soap; happy with the Kroger store brand for those.",
    "Reorders staples (eggs, bananas, spinach, Organic Valley milk); asks for family-size "
    "packs of granola bars for the kids' lunches.",
    "One-off: orders 40 cupcakes for a coworker's retirement party on Friday.",
    "Kids want mac and cheese; she says no Kraft, get Annie's.",
    "Chobani is out of stock; she says Fage is fine as a substitute. Also adds Private "
    "Selection coffee.",
    "Says she tries to keep the weekly order around $175 and asks for cheaper snack options.",
    "Complains the Main Street store was out of avocados last time; asks what time the store "
    "closes tonight.",
    "Asks for organic strawberries and organic baby spinach, but says conventional is fine for "
    "everything else; organic only matters for berries and leafy greens.",
    "Buying gluten-free crackers for a friend who is visiting this weekend (not for herself).",
    "Mentions her doctor said her cholesterol is high and asks for heart-healthy breakfast ideas.",
    "Says Organic Valley got too expensive, switch her milk to Horizon organic from now on.",
    "Weekly reorder: eggs, bananas, spinach, Horizon milk, Chobani yogurt, Dave's Killer Bread.",
    "The store substituted white bread for Dave's last time; she says never do that again.",
    "Plans next week's vegetarian high-protein dinners (lentil pasta with Rao's, tofu stir-fry).",
    "Quick reorder of Private Selection coffee and family-size snacks, staying near her budget.",
]

QUERIES = [
    {"id": "brands", "query": "What are this user's preferred grocery brands?",
     "expect": ["horizon", "chobani", "rao", "dave", "private selection", "annie"],
     "must_not": []},
    {"id": "milk", "query": "Which milk brand does the user buy now?",
     "expect": ["horizon"], "must_not": []},
    {"id": "meals", "query": "What kind of meals does the user plan?",
     "expect": ["vegetarian", "protein"], "must_not": []},
    {"id": "budget", "query": "How budget conscious is the user and where do they save money?",
     "expect": ["175", "store brand", "cheaper"], "must_not": []},
    {"id": "avoid", "query": "What should the assistant avoid or never substitute?",
     "expect": ["cilantro", "kraft", "white bread"], "must_not": []},
    {"id": "health", "query": "Does the user have any health conditions?",
     "expect": [], "must_not": ["cholesterol"]},
    {"id": "party", "query": "Is the user planning a party?",
     "expect": [], "must_not": ["cupcake", "retirement"]},
]
