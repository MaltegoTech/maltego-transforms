---
name: "maltego-transform-docs"
description: "Load this skill when you need to choose the relevant official SDK docs article for SDK API behavior, transform authoring details, entity modeling, settings, auth, pagination, server configuration, or TRX migration guidance."
compatibility: "Uses the public Freshdesk SDK overview, linked SDK article titles, local SDK source, and tests. Do not invent page-specific public URLs."
metadata:
  version: "1.0.0"
---

# maltego-transform-docs Skill

Use this skill whenever working with the `maltego-transforms` SDK: writing or editing transforms, modeling entities, configuring the server, handling auth, or migrating from maltego-trx.

## Rules

- **NEVER guess SDK APIs from memory.** Use the relevant Freshdesk SDK article, local SDK source, or tests before answering or editing code.
- If a page-specific public link is not known, cite the Freshdesk article title and local source/test evidence instead of inventing a URL.
- Do **not** read every docs page. Select only 2–4 articles that are directly relevant to the user's intent.

## Workflow

1. **Start from the SDK overview** when a general public docs URL is enough: `https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview`.
2. **Identify intent** from the user's message using the routing table below.
3. **Select 2–4 Freshdesk article titles** that match the intent.
4. **Use known published URLs when available.** If the exact public link is not known, cite the article title and local source/test evidence instead of linking to a guessed URL.

## Routing Table

| Intent | Page(s) to fetch |
|--------|-----------------|
| create project / install / run template | `Installing and Setting Up the SDK`, `Maltego Transforms SDK Overview` |
| agent skills / --with-skills / TRX migration skills | `Using AI Agent Skills with the SDK`, `Installing and Setting Up the SDK` |
| first transform / function signatures | `Writing Your First Transform (Quickstart)` |
| standard entity selection | `Standard Entities Overview` |
| custom/composed entities | `Composed Entities`, `Entity Features (Overlays, Links, Notes)` |
| pydantic/entity mapping | `Pydantic Mapping Patterns` |
| settings | `Transform Settings` |
| server configuration / discovery routes | `Server Configuration` |
| middlewares | `Transform Middlewares` |
| logging / errors | `Logging`, `Error Handling` |
| prompts | `Interactive Prompts` |
| input constraints | `Input Constraints` |
| auth / OAuth | `Authentication`, `OAuth Authentication` |
| API clients / HTTP calls | `Integration Client (HTTP Calls)` |
| pagination | `Pagination` |
| transform sets / machines | `Transform Sets`, `Machines (SDK)` |
| runner/execution model | `Execution Runner` |
| API reference | `SDK API Reference` plus the specific API topic |
| TRX migration | `Moving from TRX to the current SDK` |

Load `references/docs-routing.md` for full routing heuristics and guidance on choosing between multiple pages for the same intent.

## Public URL Handling

Freshdesk does not host a public text-index endpoint for these docs. Use the known SDK overview URL for broad links. For page-specific references without a known published link, cite the article title and local source/test evidence instead of inventing a URL.
