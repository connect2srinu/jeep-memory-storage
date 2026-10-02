# Memory Bank Extraction POC — Results

Run 2026-10-02 12:18 UTC against a dedicated Memory Bank (`4879033919988563968`), one customer, 18 sessions, 96 customer turns. Extraction model gemini-3.5-flash, embeddings text-embedding-005, six shopping-focused memory topics. The governed control plane was not involved.

## Scorecard

| Check | Result |
|---|---|
| Planted stable preferences captured | 15 of 15 |
| Noise kept (should be 0) | 0 of 5 |
| Milk switch: Horizon is current | yes |
| Milk switch: Organic Valley still stored as current | no — the old fact was replaced |
| Facts stored at the end | 14 (from 96 customer turns) |
| Extraction time per session | median 19.1 s, max 263.6 s |
| Semantic search latency (35 calls) | p50 214 ms, p95 277 ms, max 292 ms |

## Targeted queries (top 5, closest first)

**What are this user's preferred grocery brands?** — expected 3/6 (missing: rao, annie, dave) · median 241 ms

1. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.742)*
2. The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock. *(distance 0.779)*
3. The user prefers family-size packages of Nature Valley granola bars. *(distance 0.796)*
4. The user prefers Horizon Organic 1-gallon whole milk, having switched from Organic Valley because it became too expensive. *(distance 0.804)*
5. The user prefers and regularly purchases Private Selection Breakfast Blend ground coffee. *(distance 0.807)*

**Which milk brand does the user buy now?** — expected 1/1 · median 238 ms

1. The user prefers Horizon Organic 1-gallon whole milk, having switched from Organic Valley because it became too expensive. *(distance 0.784)*
2. The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock. *(distance 0.840)*
3. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.851)*
4. The user prefers and regularly purchases Private Selection Breakfast Blend ground coffee. *(distance 0.854)*
5. The user prefers heart-healthy breakfast options that are also appealing to children. *(distance 0.856)*

**What kind of meals does the user plan?** — expected 2/2 · median 214 ms

1. The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. *(distance 0.782)*
2. The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers. *(distance 0.821)*
3. The user prefers vegetarian, high-protein dinners (such as lentil pasta and tofu stir-fry with firm tofu) and dislikes cilantro in recipes. *(distance 0.821)*
4. The user prefers heart-healthy breakfast options that are also appealing to children. *(distance 0.835)*
5. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.840)*

**How budget conscious is the user and where do they save money?** — expected 2/3 (missing: cheaper) · median 192 ms

1. The user is budget-conscious, looks for sales, digital coupons, and prefers purchasing budget-friendly store brands like Kroger, especially for household products like paper towels and dish soap. *(distance 0.774)*
2. The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers. *(distance 0.854)*
3. The user aims to keep her weekly grocery budget around $175. *(distance 0.860)*
4. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.861)*
5. The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. *(distance 0.918)*

**What should the assistant avoid or never substitute?** — expected 2/3 (missing: kraft) · median 212 ms

1. The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock. *(distance 0.995)*
2. The user prefers vegetarian, high-protein dinners (such as lentil pasta and tofu stir-fry with firm tofu) and dislikes cilantro in recipes. *(distance 0.997)*
3. The user prefers Dave's Killer Bread, specifically the 21 Whole Grains and Seeds variety, and does not accept white bread as a substitution for it. *(distance 1.015)*
4. The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. *(distance 1.016)*
5. The user prefers and regularly purchases Private Selection Breakfast Blend ground coffee. *(distance 1.016)*

**Does the user have any health conditions?** — unwanted: none · median 191 ms

1. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.918)*
2. The user prefers heart-healthy breakfast options that are also appealing to children. *(distance 0.930)*
3. The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. *(distance 0.936)*
4. The user prefers family-size packages of Nature Valley granola bars. *(distance 0.937)*
5. The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers. *(distance 0.943)*

**Is the user planning a party?** — unwanted: none · median 192 ms

1. The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. *(distance 0.982)*
2. The user prefers family-size packages of Nature Valley granola bars. *(distance 0.986)*
3. The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers. *(distance 0.995)*
4. The user aims to keep her weekly grocery budget around $175. *(distance 0.995)*
5. The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. *(distance 0.996)*

## Planted facts

| Planted | Captured as |
|---|---|
| Bought Organic Valley milk (sessions 1-13) *(superseded)* | The user prefers Horizon Organic 1-gallon whole milk, having switched from Organic Valley because it became too expensive. |
| Switched to Horizon organic milk (session 14 on) | The user prefers Horizon Organic 1-gallon whole milk, having switched from Organic Valley because it became too expensive. |
| Prefers Chobani Greek yogurt | The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock. |
| Prefers Rao's pasta sauce | The user prefers Rao's Homemade Marinara Sauce, prioritizing its quality for their family despite the higher price. |
| Prefers Dave's Killer Bread | The user prefers Dave's Killer Bread, specifically the 21 Whole Grains and Seeds variety, and does not accept white bread as a substitution for it. |
| Buys Private Selection coffee | The user prefers and regularly purchases Private Selection Breakfast Blend ground coffee. |
| Store brand (Kroger) for paper towels and cleaning supplies | The user is budget-conscious, looks for sales, digital coupons, and prefers purchasing budget-friendly store brands like Kroger, especially for household products like paper towels and dish soap. |
| Avoids Kraft mac and cheese, buys Annie's | The user prefers Annie's brand for mac and cheese and refuses the Kraft brand. |
| Vegetarian, high-protein weeknight dinners | The user prefers vegetarian, high-protein dinners (such as lentil pasta and tofu stir-fry with firm tofu) and dislikes cilantro in recipes. |
| Family of four with two kids | The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers. |
| Weekly budget around $175; asks for cheaper options on snacks | The user aims to keep her weekly grocery budget around $175.<br>The user is budget-conscious, looks for sales, digital coupons, and prefers purchasing budget-friendly store brands like Kroger, especially for household products like paper towels and dish soap. |
| Family-size packs for snacks | The user prefers family-size packages of Nature Valley granola bars. |
| Weekly staples: eggs, bananas, spinach | The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread. |
| Fage is fine if Chobani is out; never swap Dave's for white bread | The user prefers Dave's Killer Bread, specifically the 21 Whole Grains and Seeds variety, and does not accept white bread as a substitution for it.<br>The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock. |
| Organic only for berries and leafy greens | The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items. |
| Dislikes cilantro | The user prefers vegetarian, high-protein dinners (such as lentil pasta and tofu stir-fry with firm tofu) and dislikes cilantro in recipes. |

## Noise (should not be kept)

| Said once | Kept as |
|---|---|
| 40 cupcakes for a coworker's retirement party | not kept |
| complained the Main Street store was out of avocados | not kept |
| gluten-free crackers for a visiting friend | not kept |
| her doctor said her cholesterol is high (health data) | not kept |
| asked what time the store closes | not kept |

## All stored facts

- The user prefers heart-healthy breakfast options that are also appealing to children.
- The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items.
- The user aims to keep her weekly grocery budget around $175.
- The user prefers and regularly purchases Private Selection Breakfast Blend ground coffee.
- The user prefers Annie's brand for mac and cheese and refuses the Kraft brand.
- The user prefers family-size packages of Nature Valley granola bars.
- The user is budget-conscious, looks for sales, digital coupons, and prefers purchasing budget-friendly store brands like Kroger, especially for household products like paper towels and dish soap.
- The user prefers Dave's Killer Bread, specifically the 21 Whole Grains and Seeds variety, and does not accept white bread as a substitution for it.
- The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, milk, yogurt, and bread.
- The user prefers Rao's Homemade Marinara Sauce, prioritizing its quality for their family despite the higher price.
- The user prefers vegetarian, high-protein dinners (such as lentil pasta and tofu stir-fry with firm tofu) and dislikes cilantro in recipes.
- The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock.
- The user prefers Horizon Organic 1-gallon whole milk, having switched from Organic Valley because it became too expensive.
- The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers.

## Facts after session 13 (before the milk switch)

- The user prefers heart-healthy breakfast options that are also appealing to children.
- The user prefers organic options for berries and leafy greens, but generally prefers conventional options for other grocery items.
- The user aims to keep her weekly grocery budget around $175.
- The user prefers Private Selection Breakfast Blend ground coffee.
- The user prefers Annie's brand for mac and cheese and refuses the Kraft brand.
- The user prefers family-size packages of Nature Valley granola bars.
- The user prefers purchasing budget-friendly store brands, specifically opting for the Kroger brand for household products like paper towels and dish soap.
- The user prefers Dave's Killer Bread, specifically the 21 Whole Grains and Seeds variety.
- The user routinely does a weekly grocery order for Sunday pickup consisting of staples like eggs, bananas, spinach, and milk.
- The user prefers Rao's Homemade Marinara Sauce, prioritizing its quality for their family despite the higher price.
- The user prefers vegetarian, high-protein dinners and dislikes cilantro in recipes.
- The user prefers Chobani Greek yogurt and accepts Fage plain Greek yogurt as a substitute when Chobani is out of stock.
- The user prefers Organic Valley brand milk.
- The user shops for their family household of four people, which includes two children aged 8 and 11, and buys groceries for their school lunches, snacks, and lunchbox fillers.

Scoring is keyword based (see `plan.py`); read the stored facts above to confirm. Latency is measured from this workstation, so it includes network time.
