---
name: "maltego-transforms"
description: "Load this skill when working in the maltego-transforms SDK repository or answering broad SDK questions about authoring, packaging, or understanding the SDK."
metadata:
  version: "1.0.0"
---

# Maltego Transforms SDK Skill

## Purpose
Orient agents working in the `maltego-transforms` SDK repository. Use this skill as the entry point for general SDK questions and to route to focused skills for specific tasks. If you are working inside a generated SDK project (rather than the SDK repository itself), start from `maltego-transform-skill-index` instead.

## SDK Scope

- **SDK style**: current async-first transform server SDK
- **Server framework**: FastAPI-based
- **Transform registration**: `@register_transform` decorator (async functions only)
- **Entity typing**: Strongly typed input/output entities
- **Public packages**:
  - `maltego-transforms` — core SDK
  - `maltego-transforms-std-entities` — standard entity library
- **Supported Python**: `>=3.10,<3.15`
- **Docs overview**: `https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview`

## Routing — Load the Right Skill

Do NOT load all reference files up front. Route to the focused skill that matches the task:

| Task | Skill to load |
|------|--------------|
| Design transforms for a data source | `maltego-transform-design` |
| Implement / build transforms | `maltego-transform-build` |
| Test a local transform server | `maltego-transform-test` |
| Discover server assets (transforms, entities) | `maltego-transform-discover` |
| Check common transform authoring mechanics | `maltego-transform-basics` |
| Plan a TRX-to-SDK migration | `maltego-trx-migration-planner` |
| Execute a TRX-to-SDK migration | `maltego-trx-migration-implementer` |
| Look up API docs | `maltego-transform-docs` |

## Step-by-Step: Orient in the SDK Repo

1. Check `pyproject.toml` for the installed SDK version and dependencies.
2. Check `src/maltego/` for server entry points, runners, and model definitions.
3. Check `src/tests/` for existing test patterns before writing new tests.
4. Load `maltego-transform-basics` only when you need common transform authoring mechanics.
5. For entity selection, check the `maltego-transforms-std-entities` package (a pip dependency, not a skill) before creating custom entities.

## What NOT to Do

- Do NOT default to legacy TRX patterns.
- Do NOT invent custom entities before checking standard ones.
- Do NOT assume internal infrastructure — this SDK is provider-agnostic.
- Do NOT load detailed references unless the active task requires them.
