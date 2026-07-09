# Docs Routing Reference

Intent-to-page routing table for `maltego-transform-docs`. Load this when you need to systematically match a user question to the most relevant docs pages before fetching.

---

## Intent Routing Table

| User intent / question topic | Pages to fetch (priority order) |
|------------------------------|----------------------------------|
| Create project / install / run template | `Installing and Setting Up the SDK`, `Maltego Transforms SDK Overview` |
| Agent skills / `--with-skills` / skill index | `Using AI Agent Skills with the SDK`, `Installing and Setting Up the SDK` |
| First transform / function signatures | `Writing Your First Transform (Quickstart)` |
| Standard entity selection | `Standard Entities Overview` |
| Custom / composed entities | `Composed Entities`, `Entity Features (Overlays, Links, Notes)` |
| Pydantic / entity property mapping | `Pydantic Mapping Patterns` |
| Settings (declare, access, types) | `Transform Settings` |
| Server configuration / discovery routes | `Server Configuration` |
| Middlewares | `Transform Middlewares` |
| Logging / error handling | `Logging`, `Error Handling` |
| Prompts | `Interactive Prompts` |
| Input constraints | `Input Constraints` |
| Auth / OAuth | `Authentication`, `OAuth Authentication` |
| API clients / HTTP calls / IntegrationClient | `Integration Client (HTTP Calls)` |
| Pagination | `Pagination` |
| Transform sets / machines | `Transform Sets`, `Machines (SDK)` |
| Runner / execution model | `Execution Runner` |
| API reference | `SDK API Reference` plus the specific API topic |
| TRX migration | `Moving from TRX to the current SDK` |

---

## How to Use This Table

1. Identify the user's primary question category from the table above.
2. Prefer the **first** listed article for the intent (the most specific match).
3. If the first article does not fully answer the question, use the **second** listed article.
4. Use at most **2-4 articles total** per session unless the user explicitly asks for more.
5. Use the selected article, local SDK source, or tests as authoritative SDK context — do not guess from memory.

---

## Routing Heuristics

- **API question + behavior uncertainty** → always fetch docs before answering; do not rely on static knowledge.
- **TRX migration + entity mapping** → `Moving from TRX to the current SDK` first, then `Standard Entities Overview`.
- **Settings + auth combined** → `Transform Settings` + `Authentication`.
- **New project setup** → `Installing and Setting Up the SDK` first, then `Writing Your First Transform (Quickstart)`.
- **Entity modeling** → `Standard Entities Overview` to check standard classes before proposing custom entities.

---

## When Published URLs Are Unknown

Freshdesk does not host a public text index for these docs. If a page-specific public link is not known:
- Do not invent Freshdesk article links.
- Cite the Freshdesk article title and local `SKILL.md`, SDK source, or test evidence instead of a guessed URL.
- Use the public SDK overview URL for broad docs references.
