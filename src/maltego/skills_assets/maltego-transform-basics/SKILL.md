---
name: "maltego-transform-basics"
description: "Load this skill when an agent needs surface-level Maltego transform authoring mechanics: function signatures, settings, context logging, entity returns, graph returns, IntegrationClient calls, or local discovery endpoints."
metadata:
  version: "1.0.0"
---

# Maltego Transform Basics Skill

## Purpose

Use this skill for quick mechanical lookups — function signatures, parameter injection rules, annotation propagation, and `context`/settings reference. For a step-by-step workflow to write a complete transform, use `maltego-transform-build` instead.

Provide a compact primer for common transform authoring mechanics. This is not a complete SDK reference; use `maltego-transform-docs` or local SDK source/tests for anything outside these basics.

## When to Load the Reference

Load `references/transform-authoring-patterns.md` when you need quick confirmation for:

- `@register_transform` function shape
- parameter injection for input entities, `settings`, `slider`/`limit`, and `context`
- `context.log.*` response shape
- standard entity imports and graph returns
- shared `IntegrationClient` usage
- common settings and discovery endpoint patterns

For migration-specific TRX mapping, use `maltego-trx-migration-planner` or `maltego-trx-migration-implementer` first, then load this skill only for the SDK target mechanics.
