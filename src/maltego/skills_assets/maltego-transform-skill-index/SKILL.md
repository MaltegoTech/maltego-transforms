---
name: "maltego-transform-skill-index"
description: "Load this skill first when working inside a generated maltego-transforms SDK project to determine which focused skill to use for the current task."
metadata:
  version: "1.0.0"
---

# Maltego Transform Skill Index

## Purpose
This is the entry skill for agents working inside a generated `maltego-transforms` SDK project. Its only job is to route you to the correct focused skill — do NOT use this skill to do actual work.

## Skills Are Provider-Agnostic

All skills in this set are provider-agnostic. They do not assume any internal infrastructure, proprietary deployment pipelines, or secret management systems. Use them with any standard Python/FastAPI deployment.

## Routing Table

Read the task. Load **one** focused skill. Do NOT load all skills or all reference files at once.

| Task | Skill to load |
|------|---------------|
| Design transforms for a new data source (entity modeling, transform sets, settings, pagination) | `maltego-transform-design` |
| Implement / build SDK transforms (write async `@register_transform` functions) | `maltego-transform-build` |
| Check common transform authoring mechanics (parameters, settings, context logging, graph returns) | `maltego-transform-basics` |
| Test a local transform server (syntax checks, HTTP discovery, request/response assertions) | `maltego-transform-test` |
| Discover what transforms and entities a running server exposes | `maltego-transform-discover` |
| Look up SDK API docs, entity schemas, or server configuration | `maltego-transform-docs` |
| Plan a migration from TRX to SDK (read-only analysis, produce migration plan) | `maltego-trx-migration-planner` |
| Execute a TRX-to-SDK migration plan (rewrite transforms, map entities) | `maltego-trx-migration-implementer` |

## TRX Migration Workflow

Recommended path:

1. Use `maltego-trx-migration-planner` to create an evidence-backed migration contract.
2. Use `maltego-trx-migration-implementer` to rewrite transform authoring to SDK-native APIs.

Optional deep dives:

- Load `maltego-transform-docs` only when installed source, tests, or generated examples do not settle an SDK API question.
- Load `maltego-transform-basics` only when common transform authoring mechanics need a quick reference.
- Load `maltego-transform-discover` only when direct discovery needs deeper debugging.
- Load `maltego-transform-test` only when transform execution, mocks, or runtime checks need more detail.

Required outcomes:

- Migration plan with source behavior evidence and SDK evidence.
- SDK-native transform code with no TRX authoring imports or wrappers.
- Runtime behavior checks for representative transforms.
- Direct SDK discovery through `/api/v3/transforms` that matches the source contract.
- Migration completion gates from `maltego-trx-migration-implementer`.
- Portable artifacts that use workspace-relative paths.

## Rules

1. **One skill at a time** — load the most specific matching skill only.
2. **Do not load references until needed** — each skill has on-demand reference files; load them only when the task requires deep context.
3. **Do not guess at internal infrastructure** — these skills work with standard HTTP servers, no proprietary tooling assumed.
4. **When in doubt about routing**, load `maltego-transforms` (the package-level SDK skill) for orientation first.
