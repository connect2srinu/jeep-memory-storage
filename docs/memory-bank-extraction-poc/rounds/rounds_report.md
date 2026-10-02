# Memory Bank Longitudinal POC — Interim (2 of 3 rounds)

Run 2026-10-02 14:02 UTC. One customer, a dedicated Memory Bank, 2 round(s) of about 100 customer turns each (204 in total). Extraction: Memory Bank with gemini-3.5-flash and seven shopping-focused memory topics. Retrieval: semantic search (top 8) and an answer written by gemini-2.5-flash from the retrieved memories only; the conversations are never sent again. The governed control plane was not involved.

## Final comparison chart

✓ in the profile · ✗ missing · ⚠ old value still stated as current · — not yet mentioned. **Explicit** = the customer said it; **implicit** = only shown by what she chose.

| Preference | Type | Before | After round 1 | After round 2 |
|---|---|---|---|---|
| Brands: milk | implicit | — | ✓ Organic Valley milk *(new)* | ✓ Organic Valley milk |
| Brands: pasta sauce | explicit | — | ✓ Rao's pasta sauce *(new)* | ✓ Rao's pasta sauce |
| Brands: yogurt | explicit | — | ✓ Chobani Greek yogurt *(new)* | ✓ Oikos Greek yogurt *(changed)* |
| Brands: bread | implicit | — | ✓ Dave's Killer Bread *(new)* | ✓ Dave's Killer Bread |
| Brands: coffee | implicit | — | — | ✓ Private Selection coffee *(new)* |
| Products: sparkling water | implicit | — | — | — |
| Diet: high protein | explicit | — | ✓ High-protein weekday meals *(new)* | ✓ High-protein weekday meals |
| Diet: friday meals | explicit | — | ✓ Vegetarian Fridays *(new)* | ✓ Mediterranean meals (instead of vegetarian Fridays) *(changed)* |
| Diet: low sodium | implicit | — | — | ✓ Low-sodium products *(new)* |
| Diet: low sugar | explicit | — | — | — |
| Restrictions: tree nuts | explicit | — | ✓ No tree nuts (son's allergy) *(new)* | ✓ No tree nuts (son's allergy) |
| Dislikes: cilantro | explicit | — | ✓ Dislikes cilantro *(new)* | ✓ Dislikes cilantro |
| Dislikes: yogurt flavor | explicit | — | ✓ No strawberry yogurt *(new)* | ✓ No strawberry yogurt |
| Budget: store brand | implicit | — | ✓ Kroger brand for paper and cleaning goods *(new)* | ✓ Kroger brand for paper and cleaning goods |
| Budget: weekly budget | explicit | — | ✓ Weekly budget about $175 *(new)* | ✓ Weekly budget about $175 |
| Products: organic produce | explicit | — | ✓ Organic only for berries and leafy greens *(new)* | ✓ Organic only for berries and leafy greens |
| Recurring: staples | implicit | — | ✓ Weekly eggs, bananas, spinach *(new)* | ✓ Weekly eggs, bananas, spinach |
| Recurring: snack size | implicit | — | ✓ Family-size snack packs *(new)* | ✓ Family-size snack packs |
| Household: household | implicit | — | ✓ Family of four with two kids *(new)* | ✓ Family of four with two kids |

## Explicit vs implicit

| Type | After round 1 | After round 2 |
|---|---|---|
| Explicit | 9 of 9 | 9 of 9 |
| Implicit | 6 of 6 | 8 of 8 |

Changed preferences:

- Round 2, yogurt (explicit): → Oikos Greek yogurt — captured, old value replaced
- Round 2, friday meals (explicit): → Mediterranean meals (instead of vegetarian Fridays) — captured, old value replaced

## Snapshot progression

| | Before | After round 1 | After round 2 |
|---|---|---|---|
| Facts stored | 0 | 19 | 20 |
| Customer turns processed (cumulative) | 0 | 102 | 204 |
| brand preferences | 0 | 10 | 10 |
| budget and value | 0 | 3 | 2 |
| diet and meal patterns | 0 | 1 | 2 |
| household | 0 | 3 | 2 |
| organic and quality | 0 | 4 | 4 |
| product restrictions and dislikes | 0 | 4 | 4 |
| recurring purchases | 0 | 5 | 6 |
| One-off details kept (should be none) | — | none | none |

## Retrieval tests (asked after every round, without the conversations)

### After round 1

**What do you know about this user's dietary preferences?** — 2/2 expected terms · search 272 ms

> The user prefers high-protein meals for dinners, and vegetarian dinners on Fridays, including MorningStar Farms veggie burgers. They prefer organic for berries, leafy greens, and Gala apples, and conventional for other items. They consume dairy (Chobani vanilla Greek yogurt, Organic Valley whole milk and 2% milk) and eggs (Organic Valley). They also consume Kellogg's Frosted Flakes cereal and Kraft Macaroni & Cheese.

**What are this user's preferred grocery brands?** — 2/4 expected terms, missing dave, rao · search 475 ms

> Organic Valley, Chobani, Kellogg's, Snyder's of Hanover, Nature Valley, Kroger store brand, MorningStar Farms.

**What yogurt brand should the shopping assistant recommend?** — 1/1 expected terms · search 811 ms

> Chobani.

**What should I consider when creating a weekly meal plan?** — 3/3 expected terms · search 268 ms

> Consider:
> *   High-protein dinners (vegetarian on Fridays).
> *   A weekly grocery budget around $175.
> *   Incorporating large eggs, bananas, spinach, milk, bread, and yogurt.
> *   Organic berries, leafy greens, and Gala apples; conventional for other produce.
> *   Avoiding cilantro.
> *   Avoiding almonds and cashews due to a tree nut allergy.
> *   Using Organic Valley brand for dairy (whole milk, 2% milk in two-gallon quantities) and eggs.
> *   Using Dave's Killer Bread 21 Whole Grains.

**What products should I avoid recommending?** — 3/3 expected terms · search 448 ms

> Low-quality coffee, strawberry-flavored yogurt, non-Organic Valley dairy products and eggs, non-organic berries, non-organic leafy greens, non-organic Gala apples, organic items other than berries, leafy greens, and Gala apples, snacks containing almonds or cashews, cilantro, mushy strawberries, and non-Kroger brand household essentials.

**What preferences have changed recently?** — no expected terms · search 387 ms

> The facts do not say what preferences have changed recently.

**Does the user have any health conditions?** — no expected terms · search 302 ms

> The facts do not state that the user has any health conditions.

### After round 2

**What do you know about this user's dietary preferences?** — 3/3 expected terms · search 262 ms

> The user prefers high-protein meals for dinners and weekday lunches, focuses on Mediterranean meals, and stopped preparing vegetarian dinners on Fridays. They prefer low-sodium options for food and pantry items. They buy organic for berries, leafy greens, and Gala apples, and conventional for other items. They prefer MorningStar Farms brand veggie burgers, Kellogg's Frosted Flakes, Oikos brand yogurt (no substitutions), Organic Valley 2% milk, and bananas that are still a little green.

**What are this user's preferred grocery brands?** — 1/4 expected terms, missing oikos, private selection, rao · search 376 ms

> Organic Valley, Kellogg's, Snyder's of Hanover, Nature Valley, Kroger (store brand), MorningStar Farms, Dave's Killer Bread.

**What yogurt brand should the shopping assistant recommend?** — 1/1 expected terms · search 277 ms

> Oikos.

**What should I consider when creating a weekly meal plan?** — 3/3 expected terms · search 182 ms

> Consider: high-protein dinners and weekday lunches, Mediterranean meals, no vegetarian dinners on Fridays, low-sodium options, avoiding cilantro, and avoiding almonds/cashews due to a tree nut allergy. They shop for their family and aim for a $175 weekly budget.

**What products should I avoid recommending?** — 3/3 expected terms · search 243 ms

> You should avoid recommending:
> *   Strawberry-flavored yogurt.
> *   Chobani brand yogurt.
> *   Conventional berries, leafy greens, and Gala apples.
> *   High-sodium chicken broth, canned black beans, soy sauce, saltine crackers, and soup.
> *   Snacks containing almonds or cashews.
> *   Dishes or products containing cilantro.

**What preferences have changed recently?** — 1/2 expected terms, missing mediterranean · search 243 ms

> The user changed from preferring Chobani vanilla Greek yogurt to Oikos brand. They also stopped preparing vegetarian dinners on Fridays.

**Does the user have any health conditions?** — no expected terms · search 245 ms

> The facts do not say.

## Tokens and cost

Extraction tokens are Memory Bank's real usage of the extraction model, read from Cloud Monitoring for each round's extraction window (that model is used by nothing else). Output includes the model's reasoning tokens.

| Round | Conversation tokens | Extraction input | Extraction output | Answer input | Answer output | Memory tokens | Compression (cumulative) | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 4,669 | 88,837 | 50,494 | 1,764 | 4,125 | 448 | 10 : 1 | $0.5985 |
| 2 | 4,095 | 97,527 | 60,814 | 2,168 | 3,498 | 613 | 14 : 1 | $0.7030 |
| **Total** | **8,764** | **186,364** | **111,308** | **3,932** | **7,623** | | | **$1.3016** |

### Projection to 1 million tokens

- Extraction read 21.3 input tokens per token of conversation (the model also reads its instructions and the existing memories), and wrote 59.7% as many output tokens as it read.
- **Per 1M extraction input tokens:** 1M × $1.50 + 597,261 output × $9.00 per 1M = **$6.88**.
- **Per 1M tokens of raw conversation:** $1.2813 × (1,000,000 / 8,764) = **$146.20** of extraction.
- Answers: 281 input tokens per question on average — only the retrieved memories, not the conversation history.
- Memory Bank operations (36 generate calls, 16 reads) cost $0.000004; storage of a few dozen short facts is negligible.

## Profile snapshots (as returned by Memory Bank)

### Before round 1

0 facts.

### After round 1 — 19 facts

**brand preferences**

- The user prefers Kraft brand Macaroni & Cheese, specifically referring to it as "the blue box kind".
- The user prefers family-sized or family pack packaging for snack items like crackers, specifically preferring Snyder's of Hanover pretzels and Nature Valley brand granola bars in large or family-size packaging.
- The user prefers Kellogg's Frosted Flakes brand cereal.
- The user prefers Dave's Killer Bread 21 Whole Grains.
- The user prefers Kroger store brand for household essentials like paper towels, dish soap, trash bags, and all-purpose cleaner, and seeks out sales and promotions like buy-one-get-one-half-off deals.
- The user prefers Chobani brand Greek yogurt, specifically vanilla, and typically purchases it in a quantity of four.
- The user prefers MorningStar Farms brand veggie burgers.
- The user prefers Rao's brand pasta sauce, even though it is more expensive.
- The user prefers Organic Valley brand for dairy products and eggs, particularly whole milk, 2% milk (regularly purchased in two-gallon quantities), and eggs.
- The user has a son and a daughter, shops for a household of four people, and shops for their children's lunches, preferring to buy her son the large 24oz box of Tyson Fun Nuggets (dinosaur chicken nuggets).

**budget and value**

- The user aims to keep their weekly grocery budget around $175.
- The user prefers Kroger store brand for household essentials like paper towels, dish soap, trash bags, and all-purpose cleaner, and seeks out sales and promotions like buy-one-get-one-half-off deals.
- The user prefers Rao's brand pasta sauce, even though it is more expensive.

**diet and meal patterns**

- The user prefers high-protein meals for dinners, but usually prepares vegetarian dinners on Fridays.

**household**

- The user's son has a tree nut allergy, so the household must avoid snacks containing almonds or cashews.
- The user shops for her husband, who is very particular about coffee and prefers high-quality or premium options.
- The user has a son and a daughter, shops for a household of four people, and shops for their children's lunches, preferring to buy her son the large 24oz box of Tyson Fun Nuggets (dinosaur chicken nuggets).

**organic and quality**

- The user prefers to buy organic specifically for berries, leafy greens, and Gala apples, and conventional for other items.
- The user dislikes mushy strawberries and prefers that fresh strawberries are carefully inspected for quality.
- The user shops for her husband, who is very particular about coffee and prefers high-quality or premium options.
- The user prefers Organic Valley brand for dairy products and eggs, particularly whole milk, 2% milk (regularly purchased in two-gallon quantities), and eggs.

**product restrictions and dislikes**

- The user dislikes mushy strawberries and prefers that fresh strawberries are carefully inspected for quality.
- The user's son has a tree nut allergy, so the household must avoid snacks containing almonds or cashews.
- The user's kids dislike strawberry-flavored yogurt.
- The user dislikes cilantro and wants to avoid it in all dishes.

**recurring purchases**

- The user prefers family-sized or family pack packaging for snack items like crackers, specifically preferring Snyder's of Hanover pretzels and Nature Valley brand granola bars in large or family-size packaging.
- The user prefers Kellogg's Frosted Flakes brand cereal.
- The user regularly orders large eggs, bananas, bags of spinach, milk, bread, and yogurt for their weekly grocery pickup.
- The user prefers Chobani brand Greek yogurt, specifically vanilla, and typically purchases it in a quantity of four.
- The user has a son and a daughter, shops for a household of four people, and shops for their children's lunches, preferring to buy her son the large 24oz box of Tyson Fun Nuggets (dinosaur chicken nuggets).

### After round 2 — 20 facts

**brand preferences**

- The user prefers Kraft brand Macaroni & Cheese, specifically referring to it as "the blue box kind".
- The user prefers family-sized or family pack packaging for snack items like crackers, specifically preferring Snyder's of Hanover pretzels and Nature Valley brand granola bars in large or family-size packaging.
- The user prefers Kellogg's Frosted Flakes brand cereal.
- The user prefers Dave's Killer Bread 21 Whole Grains and Kroger brand whole wheat bread.
- The user shops for her husband, who is very particular about coffee and prefers high-quality or premium options, and regularly purchases Private Selection Breakfast Blend coffee.
- The user prefers Kroger store brand for household essentials like paper towels (specifically preferring the 12-roll big pack), dish soap, trash bags, and all-purpose cleaner, and seeks out sales and promotions like buy-one-get-one-half-off deals.
- The user prefers Oikos brand yogurt over Chobani and specifies that no substitutions should be made for Oikos. Previously, they preferred Chobani vanilla Greek yogurt, typically purchasing a quantity of four.
- The user prefers MorningStar Farms brand veggie burgers.
- The user prefers and regularly purchases Rao's brand pasta sauce (specifically Rao's Homemade Marinara), even though it is more expensive.
- The user prefers Organic Valley brand for organic milk, specifically choosing it for organic whole milk, though they have also used Horizon brand in the past. They currently order Organic Valley 2% milk in a two-gallon quantity (previously purchasing three gallons because their kids drink a lot of milk), and prefer Organic Valley brand for other dairy products and eggs.

**budget and value**

- The user aims to keep their weekly grocery budget around $175.
- The user prefers Kroger store brand for household essentials like paper towels (specifically preferring the 12-roll big pack), dish soap, trash bags, and all-purpose cleaner, and seeks out sales and promotions like buy-one-get-one-half-off deals.

**diet and meal patterns**

- The user prefers low-sodium options for food and pantry items, such as chicken broth, canned black beans, soy sauce, saltine crackers, and soup.
- The user prefers high-protein meals for dinners and weekday lunches, focuses on Mediterranean meals, having stopped preparing vegetarian dinners on Fridays, and shops for their family.

**household**

- The user's son has a tree nut allergy, so the household must avoid snacks containing almonds or cashews.
- The user has a son who plays soccer and drinks whole milk, and a daughter, shops for a household of four people, and shops for her children, including for their lunches, preferring to buy her son the large 24oz box of Tyson Fun Nuggets (dinosaur chicken nuggets).

**organic and quality**

- The user prefers to buy organic specifically for berries, leafy greens, and Gala apples, and conventional for other items.
- The user dislikes mushy strawberries and prefers that fresh strawberries are carefully inspected for quality.
- The user regularly orders large eggs, bananas (preferring them still a little green), bags of spinach, Organic Valley 2% milk, bread, and Oikos Greek yogurt for their weekly grocery pickup.
- The user prefers Organic Valley brand for organic milk, specifically choosing it for organic whole milk, though they have also used Horizon brand in the past. They currently order Organic Valley 2% milk in a two-gallon quantity (previously purchasing three gallons because their kids drink a lot of milk), and prefer Organic Valley brand for other dairy products and eggs.

**product restrictions and dislikes**

- The user dislikes mushy strawberries and prefers that fresh strawberries are carefully inspected for quality.
- The user's son has a tree nut allergy, so the household must avoid snacks containing almonds or cashews.
- The user's kids dislike strawberry-flavored yogurt.
- The user dislikes cilantro and wants to avoid it in all dishes.

**recurring purchases**

- The user prefers family-sized or family pack packaging for snack items like crackers, specifically preferring Snyder's of Hanover pretzels and Nature Valley brand granola bars in large or family-size packaging.
- The user prefers Kellogg's Frosted Flakes brand cereal.
- The user prefers Dave's Killer Bread 21 Whole Grains and Kroger brand whole wheat bread.
- The user shops for her husband, who is very particular about coffee and prefers high-quality or premium options, and regularly purchases Private Selection Breakfast Blend coffee.
- The user prefers Kroger store brand for household essentials like paper towels (specifically preferring the 12-roll big pack), dish soap, trash bags, and all-purpose cleaner, and seeks out sales and promotions like buy-one-get-one-half-off deals.
- The user prefers and regularly purchases Rao's brand pasta sauce (specifically Rao's Homemade Marinara), even though it is more expensive.

## Extraction time per session

| Round | Median | Max | Timeouts / throttling retried |
|---|---|---|---|
| 1 | 105.2 s | 534.8 s | 1 |
| 2 | 136.8 s | 943.7 s | 2 |

Scoring is keyword based against the planted ground truth in `plan_rounds.py`; read the snapshots to confirm. Prices: Vertex AI generative AI pricing and Gemini Enterprise Agent Platform pricing, checked 2026-10-02.
