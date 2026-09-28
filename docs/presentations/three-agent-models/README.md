# Governed Memory: Three Agent Models

A 12-slide deck that explains the memory model with three example agents:

| Agent | Model |
|---|---|
| KSA | Private — keeps its own preferences, reads nothing from others |
| Cooklist | Hybrid — keeps its own and reads (and optionally writes) approved KSA preferences |
| Meal Planner | Consumer only — keeps nothing, reads approved preferences only |

It covers canonical vs dynamic preferences, sensitivity classifications, per-preference access
requests (read, or read + write), cross-agent writes, runtime enforcement, schema versions, setup
through the wizard, and open items.

- **Live deck (present, export to PowerPoint/PDF):**
  https://claude.ai/artifact/DBpEXu13RT1gjbysYQBFbk — private until shared from its Share menu.
- **Source in this folder:** `deck.json` (title, slide order, sections, fonts) and one
  `slides/<id>.html` per slide. Speaker notes are the `<aside>` at the end of each slide.

The slides use the Slides artifact format (inline-styled `<section>` elements plus `x-icon` and
`x-connector` tags), so open the live deck to view them. Edit the files here and republish them to
the same deck to update it.

Hands-on companion: [Three Agent Memory Models — UI Test Guide](../../three-agent-models-test-guide.md).
