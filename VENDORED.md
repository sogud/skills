# Vendored sources

## marketingskills

Nine marketing skills from [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills), commit `88c79f6528a9347420e57ceb1fff9a60de651768` (2026-10-30). License: MIT, Copyright (c) 2025 Corey Haines. Each skill directory includes that upstream `LICENSE`.

This repository has no separate discoverable directory and no skill index. Every `<name>/SKILL.md` is a global skill (`workspace.yaml` repo `skills`, checked out at `system/agents-config/skills/own/`). `link-globals` symlinks each one into the user-level skill directories. Skill bodies are read when a skill is selected, not on every turn.

`product-marketing` is left model-invocable so positioning and `.agents/product-marketing.md` stay available. The other eight set `disable-model-invocation: true`, the same frontmatter already used by `update-harness` and `iamadhd`. They stay installed and can be invoked by name, and they are not offered for automatic loading. After pulling this repo into `skills/own`, rerun `link-globals --force` so the new directories are linked.

| Skill | Tier | Upstream version |
| --- | --- | --- |
| `product-marketing` | global | 2.2.0 |
| `copywriting` | discoverable | 2.3.2 |
| `launch` | discoverable | 2.2.0 |
| `onboarding` | discoverable | 2.0.2 |
| `directory-submissions` | discoverable | 2.1.4 |
| `ai-seo` | discoverable | 2.12.0 |
| `social` | discoverable | 2.4.1 |
| `competitor-profiling` | discoverable | 2.1.5 |
| `reverse-engineer-marketing` | discoverable | 1.0.0 |

`product-marketing` writes `.agents/product-marketing.md` in the product being marketed. The other eight read that file first (also `.claude/product-marketing.md` and the legacy `product-marketing-context.md` name). Those paths are unchanged. References between these nine skills are by skill name, and each skill's `references/` files (plus `reverse-engineer-marketing/scripts/teardown.mjs` and `directory-submissions/references/submission-tracker-template.csv`) are included.

### Local edits

- `disable-model-invocation: true` on the eight discoverable skills.
- In `reverse-engineer-marketing`, relative links to upstream `tools/integrations/` and `tools/REGISTRY.md` now point at that same commit on GitHub. `tools/clis/` was not copied.

Author `evals/evals.json` files were not copied. They are not referenced by the skill bodies.

### Optional paid APIs

Kept optional. Nothing here requires an API key.

- `reverse-engineer-marketing/scripts/teardown.mjs` uses `SCRAPECREATORS_API_KEY` only for `sc-ads`. Without the key, use the `ads` command for free ad-library links. DataForSEO, Semrush, Ahrefs, Similarweb, Apify, TheirStack, Exa, and Browserbase are named as optional sources.
- `competitor-profiling` can use Firecrawl and DataForSEO MCP when connected, and tells the agent to use another SEO source when DataForSEO is not.

### Upstream skills named here but not vendored

These names are left as written. They are not in this repo:

`ab-testing`, `ad-creative`, `ads`, `analytics`, `aso`, `attribution`, `churn-prevention`, `co-marketing`, `cold-email`, `community-marketing`, `competitors`, `content-strategy`, `conversion-tracking`, `copy-editing`, `cro`, `customer-research`, `emails`, `events`, `free-tools`, `influencer-marketing`, `lead-magnets`, `link-building`, `marketing-ideas`, `marketing-loops`, `marketing-plan`, `marketing-psychology`, `offers`, `paywalls`, `popups`, `pricing`, `programmatic-seo`, `prospecting`, `public-relations`, `referrals`, `revops`, `sales-enablement`, `schema`, `seo-audit`, `signup`, `site-architecture`, `sms`, `video`.

The densest map is `reverse-engineer-marketing/references/play-routing.md`. Description lines also point at a few of these for adjacent tasks (for example copywriting points at `emails`, `popups`, `copy-editing`, and `offers`).
