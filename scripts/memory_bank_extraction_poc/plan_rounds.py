"""Seeded plan for the three-round (longitudinal) Memory Bank test.

PREFERENCES is the hidden ground truth: what the profile should say after each round. "explicit"
preferences are stated by the customer; "implicit" ones only show in what she repeatedly chooses
(she never says she prefers them), so they test whether Memory Bank infers patterns.
"""

from __future__ import annotations

PERSONA = (
    "Maya, a Kroger customer who shops for her family (husband and two kids, 8 and 11). She "
    "orders pickup and types short, casual messages."
)

# by_round: round -> (value, status, keywords that show it). Status: new / reinforced / changed.
# A round missing from by_round means the preference is not mentioned in that round (it should
# persist). "stale" keywords identify the previous value after a change.
PREFERENCES = [
    {"id": "milk", "category": "Brands", "type": "implicit", "by_round": {
        1: ("Organic Valley milk", "new", ["organic valley"]),
        2: ("Organic Valley milk", "reinforced", ["organic valley"]),
        3: ("Organic Valley milk", "reinforced", ["organic valley"])}},
    {"id": "pasta_sauce", "category": "Brands", "type": "explicit", "by_round": {
        1: ("Rao's pasta sauce", "new", ["rao"]),
        2: ("Rao's pasta sauce", "reinforced", ["rao"])}},
    {"id": "yogurt", "category": "Brands", "type": "explicit", "by_round": {
        1: ("Chobani Greek yogurt", "new", ["chobani"]),
        2: ("Oikos Greek yogurt", "changed", ["oikos"]),
        3: ("Oikos Greek yogurt", "reinforced", ["oikos"])}, "stale": ["chobani"]},
    {"id": "bread", "category": "Brands", "type": "implicit", "by_round": {
        1: ("Dave's Killer Bread", "new", ["dave"]),
        2: ("Dave's Killer Bread", "reinforced", ["dave"]),
        3: ("Simple Truth whole wheat bread", "changed", ["simple truth"])}, "stale": ["dave"]},
    {"id": "coffee", "category": "Brands", "type": "implicit", "by_round": {
        2: ("Private Selection coffee", "new", ["private selection"]),
        3: ("Private Selection coffee", "reinforced", ["private selection"])}},
    {"id": "sparkling_water", "category": "Products", "type": "implicit", "by_round": {
        3: ("LaCroix sparkling water", "new", ["lacroix", "la croix"])}},
    {"id": "high_protein", "category": "Diet", "type": "explicit", "by_round": {
        1: ("High-protein weekday meals", "new", ["protein"]),
        2: ("High-protein weekday meals", "reinforced", ["protein"]),
        3: ("High-protein weekday meals", "reinforced", ["protein"])}},
    {"id": "friday_meals", "category": "Diet", "type": "explicit", "by_round": {
        1: ("Vegetarian Fridays", "new", ["vegetarian"]),
        2: ("Mediterranean meals (instead of vegetarian Fridays)", "changed", ["mediterranean"]),
        3: ("Mediterranean meals", "reinforced", ["mediterranean"])}, "stale": ["vegetarian"]},
    {"id": "low_sodium", "category": "Diet", "type": "implicit", "by_round": {
        2: ("Low-sodium products", "new", ["sodium"]),
        3: ("Low-sodium products", "reinforced", ["sodium"])}},
    {"id": "low_sugar", "category": "Diet", "type": "explicit", "by_round": {
        3: ("Low added sugar (e.g. cereal)", "new", ["sugar"])}},
    {"id": "tree_nuts", "category": "Restrictions", "type": "explicit", "by_round": {
        1: ("No tree nuts (son's allergy)", "new", ["tree nut", "almond", "cashew"]),
        3: ("No tree nuts (son's allergy)", "reinforced", ["tree nut", "almond", "cashew"])}},
    {"id": "cilantro", "category": "Dislikes", "type": "explicit", "by_round": {
        1: ("Dislikes cilantro", "new", ["cilantro"])}},
    {"id": "yogurt_flavor", "category": "Dislikes", "type": "explicit", "by_round": {
        1: ("No strawberry yogurt", "new", ["strawberry"])}},
    {"id": "store_brand", "category": "Budget", "type": "implicit", "by_round": {
        1: ("Kroger brand for paper and cleaning goods", "new", ["kroger brand", "store brand", "kroger-brand", "private label"]),
        2: ("Kroger brand for paper and cleaning goods", "reinforced", ["kroger brand", "store brand", "kroger-brand", "private label"]),
        3: ("Kroger brand for paper and cleaning goods", "reinforced", ["kroger brand", "store brand", "kroger-brand", "private label"])}},
    {"id": "weekly_budget", "category": "Budget", "type": "explicit", "by_round": {
        1: ("Weekly budget about $175", "new", ["175"]),
        3: ("Weekly budget about $200", "changed", ["200"])}, "stale": ["175"]},
    {"id": "organic_produce", "category": "Products", "type": "explicit", "by_round": {
        1: ("Organic only for berries and leafy greens", "new", ["berries", "leafy green"])}},
    {"id": "staples", "category": "Recurring", "type": "implicit", "by_round": {
        1: ("Weekly eggs, bananas, spinach", "new", ["banana", "spinach"]),
        2: ("Weekly eggs, bananas, spinach", "reinforced", ["banana", "spinach"]),
        3: ("Weekly eggs, bananas, spinach", "reinforced", ["banana", "spinach"])}},
    {"id": "snack_size", "category": "Recurring", "type": "implicit", "by_round": {
        1: ("Family-size snack packs", "new", ["family-size", "family size", "large bag", "bulk"]),
        3: ("Family-size snack packs", "reinforced", ["family-size", "family size", "large bag", "bulk"])}},
    {"id": "household", "category": "Household", "type": "implicit", "by_round": {
        1: ("Family of four with two kids", "new", ["four", "two kids", "two children", "children", "kids"])}},
]

# Said once; should NOT become long-term memory.
NOISE = {
    1: [{"id": "party", "said": "40 cupcakes for a coworker's retirement", "any": ["cupcake", "retirement"]},
        {"id": "complaint", "said": "Main Street store out of avocados; store closing time", "any": ["main street", "closes", "closing time"]}],
    2: [{"id": "bbq", "said": "burger buns and hot dogs for a neighbor's BBQ", "any": ["bbq", "barbecue", "neighbor", "hot dog"]},
        {"id": "guest", "said": "gluten-free pasta for a visiting friend", "any": ["gluten"]}],
    3: [{"id": "health", "said": "has been getting migraines (health data)", "any": ["migraine", "headache"]},
        {"id": "holiday", "said": "a turkey for 12 Thanksgiving guests", "any": ["turkey", "thanksgiving", "12 guests"]},
        {"id": "stock", "said": "complained Oikos was out of stock last week", "any": ["out of stock"]}],
}

E, I, N, T = "EXPLICIT", "IMPLICIT", "NOISE", "TRANSACTION"
# Each session: list of (kind, beat). EXPLICIT = she states it as her preference. IMPLICIT = she
# only chooses it (the assistant offers options); she must not explain or call it a preference.
SESSIONS = {
    1: [
        [(I, "assistant offers milk options; she picks Organic Valley whole milk"),
         (I, "adds eggs, bananas and spinach"), (I, "mentions it's for the kids' breakfast")],
        [(E, "says she prefers Rao's pasta sauce even though it costs more")],
        [(E, "says they're trying to eat high-protein meals on weekdays"),
         (E, "asks for no cilantro, she can't stand it")],
        [(E, "says Fridays they normally do vegetarian dinners")],
        [(E, "wants Chobani Greek yogurt, but never the strawberry flavor")],
        [(I, "assistant offers name-brand and Kroger brand paper towels and dish soap; she picks "
             "the Kroger brand both times")],
        [(I, "assistant offers several breads; she picks Dave's Killer Bread"),
         (I, "reorders eggs, bananas and spinach")],
        [(N, "orders 40 cupcakes for a coworker's retirement on Friday")],
        [(E, "says her son is allergic to tree nuts, so no almonds or cashews in snacks"),
         (I, "picks the family-size bags of pretzels and crackers")],
        [(T, "reschedules today's pickup to 5 pm")],
        [(E, "says she tries to keep the weekly order around $175")],
        [(E, "says organic matters only for berries and leafy greens; conventional is fine "
             "otherwise")],
        [(I, "picks Organic Valley milk again"), (I, "picks Dave's Killer Bread again"),
         (I, "mentions 'the four of us' in passing")],
        [(N, "complains the Main Street store was out of avocados and asks when it closes")],
        [(I, "assistant offers trash bags and cleaning spray; she picks the Kroger brand"),
         (I, "picks family-size granola bars")],
        [(T, "asks the price of a rotisserie chicken and adds one")],
        [(I, "weekly reorder: eggs, bananas, spinach, Organic Valley milk, Dave's Killer Bread, "
             "Chobani yogurt")],
        [(T, "asks for the status of last week's pickup order")],
    ],
    2: [
        [(E, "says she's been buying Chobani but lately prefers Oikos; use Oikos for yogurt "
             "from now on")],
        [(E, "says they don't need vegetarian Fridays anymore; they're trying Mediterranean meals "
             "instead")],
        [(I, "assistant offers regular and low-sodium chicken broth and canned beans; she picks "
             "low-sodium both times without saying why")],
        [(I, "assistant offers coffee; she picks Private Selection"),
         (I, "picks Organic Valley milk")],
        [(I, "picks Rao's for pasta night without comment"),
         (E, "asks for high-protein dinner ideas")],
        [(N, "buys 30 burger buns and hot dogs for a neighbor's BBQ")],
        [(I, "assistant offers soy sauce and crackers; she picks the low-sodium versions")],
        [(I, "picks the Kroger brand paper towels again")],
        [(I, "weekly reorder: eggs, bananas, spinach, Organic Valley milk, Oikos yogurt")],
        [(T, "reschedules pickup to Saturday morning")],
        [(N, "buys gluten-free pasta for a friend visiting this weekend")],
        [(I, "picks Private Selection coffee again"), (I, "picks a low-sodium soup")],
        [(E, "asks for a Mediterranean meal plan for the week")],
        [(T, "asks how much salmon is per pound")],
        [(E, "asks for high-protein lunch ideas for weekdays")],
        [(I, "picks Dave's Killer Bread again")],
        [(I, "weekly reorder plus Private Selection coffee and Rao's sauce")],
        [(T, "asks whether her order is ready for pickup")],
    ],
    3: [
        [(I, "assistant suggests Dave's Killer Bread as usual; she says 'no, the Simple Truth "
             "whole wheat this time' without explaining")],
        [(E, "says they upped the weekly grocery budget to $200")],
        [(E, "says she's trying to cut down on added sugar; asks for low-sugar cereal options")],
        [(I, "adds a 12-pack of LaCroix sparkling water")],
        [(I, "again picks Simple Truth whole wheat over Dave's Killer Bread")],
        [(N, "mentions she's been getting migraines and asks for snack ideas")],
        [(I, "reorders Oikos yogurt and Organic Valley milk")],
        [(E, "asks for Mediterranean, high-protein dinners for the week")],
        [(N, "orders a turkey for 12 Thanksgiving guests")],
        [(I, "adds LaCroix again"), (I, "picks family-size snack packs")],
        [(I, "picks low-sodium broth again")],
        [(E, "reminds the assistant her son is allergic to tree nuts when choosing granola")],
        [(N, "complains Oikos was out of stock last week")],
        [(T, "reschedules pickup to 6 pm")],
        [(I, "picks Simple Truth whole wheat bread a third time"),
         (I, "reorders eggs, bananas and spinach")],
        [(I, "picks the Kroger brand cleaning supplies")],
        [(I, "adds LaCroix and Private Selection coffee")],
        [(T, "asks the price of avocados")],
    ],
}

# Asked after every round. "expect" = words the answer should contain after that round.
QUERIES = [
    {"id": "diet", "query": "What do you know about this user's dietary preferences?",
     "expect": {1: ["protein", "vegetarian"], 2: ["protein", "mediterranean", "sodium"],
                3: ["protein", "mediterranean", "sodium", "sugar"]}},
    {"id": "brands", "query": "What are this user's preferred grocery brands?",
     "expect": {1: ["rao", "chobani", "organic valley", "dave"],
                2: ["rao", "oikos", "organic valley", "private selection"],
                3: ["rao", "oikos", "organic valley", "simple truth", "private selection"]}},
    {"id": "yogurt", "query": "What yogurt brand should the shopping assistant recommend?",
     "expect": {1: ["chobani"], 2: ["oikos"], 3: ["oikos"]}},
    {"id": "meal_plan", "query": "What should I consider when creating a weekly meal plan?",
     "expect": {1: ["protein", "cilantro", "almond"], 2: ["protein", "mediterranean", "almond"],
                3: ["protein", "mediterranean", "almond", "sugar"]}},
    {"id": "avoid", "query": "What products should I avoid recommending?",
     "expect": {1: ["almond", "cilantro", "strawberry"], 2: ["almond", "cilantro", "strawberry"],
                3: ["almond", "cilantro", "strawberry"]}},
    {"id": "changes", "query": "What preferences have changed recently?",
     "expect": {1: [], 2: ["oikos", "mediterranean"], 3: ["simple truth", "200"]}},
    {"id": "health", "query": "Does the user have any health conditions?",
     "expect": {1: [], 2: [], 3: []}, "must_not": ["migraine"]},
]
