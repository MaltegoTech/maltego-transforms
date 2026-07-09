# Runbook: Migrate a TRX transform to the SDK

Migrate legacy `maltego-trx` transforms into async, SDK-native transforms. The shipped agent skills automate most of this — use them.

## First-time setup

Install the SDK and the agent skills before planning the migration. If you are
already inside the target transform project, install skills locally:

```bash
pip install maltego-transforms
maltego-transforms install-skills --target .
```

To make the SDK skills available to agents from any project, install them in
the global skills directory instead:

```bash
pip install maltego-transforms
maltego-transforms install-skills --scope global
```

After a local install, agents should read
`.agents/skills/maltego-transform-skill-index/SKILL.md` first. That index
routes to the planner, implementer, testing, discovery, and docs skills.

## Recommended flow (with agent skills)

1. **Plan** — load `maltego-trx-migration-planner`. It reads the old TRX project read-only and produces an evidence-backed migration contract: what each transform does (source evidence) and the SDK API that replaces it (SDK evidence).
2. **Implement** — load `maltego-trx-migration-implementer`. It rewrites transforms into async `@register_transform` functions and maps entities to standard entities where possible.

If your runtime does not auto-discover local skills, point it explicitly at `.agents/skills/maltego-transform-skill-index/SKILL.md`.

## What "migrated" means (required outcomes)

- SDK-native code with **no TRX authoring imports or wrappers**.
- Standard entities used where available (custom entities only when needed).
- Runtime behavior checks for representative transforms.
- Direct SDK discovery via `/api/v3/transforms` matches the source contract.
- Portable artifacts using workspace-relative paths.

## Translation cheatsheet

| TRX idiom | SDK equivalent |
|-----------|----------------|
| `class MyTransform(DiscoverableTransform)` | `@register_transform` on an `async def` |
| sync method | `async def` |
| `request.Value` | `input_entity.value` / typed property |
| `response.addEntity(...)` | `return [Entity(...)]` or a `MaltegoGraph` |
| manual settings parsing | `settings: Dict[str, Any]` param + `TransformSetting(...)` |

The migration skills assume a clean SDK rewrite — they do not assume classic protocol packages, MTZ/iTDS/pTDS discovery, or any internal infrastructure.
