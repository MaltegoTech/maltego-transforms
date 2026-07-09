---
name: "maltego-trx-migration-planner"
description: "Load this skill when planning a migration from TRX-based transforms to SDK: read-only project analysis, entity mapping, difficulty classification, and producing a migration plan."
compatibility: "Requires Python 3.10+ and local read access to the source TRX project; the analysis scripts use only the Python standard library."
metadata:
  version: "1.0.0"
---

# Maltego TRX Migration Planner Skill

## Purpose
Inspect a TRX-based transform project read-only and produce a structured migration plan that another agent (the implementer) can execute. Do NOT make code changes during planning.

## Golden Rule
**Produce a plan document BEFORE any broad code changes.** The planner's output is a migration plan — not code.

## Default Migration Contract

When the user asks for a TRX-to-SDK migration and does not provide a more
specific contract, infer this default:

- Preserve externally visible transform behavior.
- Preserve transform IDs/names unless incompatible with SDK naming.
- Preserve input/output entity types and key properties.
- Preserve settings semantics, including auth, optionality, popup/global
  behavior, and runtime names.
- Preserve API/client behavior, including request parameters, response parsing,
  pagination, retries, shared/singleton clients, and no-result handling.
- Preserve user-visible messages and error behavior where the SDK has an
  equivalent.
- Use source behavior evidence to decide what must be kept, but rewrite transform authoring to SDK-native APIs.
- Do not preserve TRX registry/wrapper/discovery artifacts unless explicitly requested.

If the source behavior is ambiguous, record a concrete assumption in the plan
and continue with the safest SDK-native migration. Do not ask the user to
provide obvious defaults that can be inferred from source.

## Step-by-Step: Plan a TRX Migration

### 1. Read-Only Project Inspection

Start with file discovery — no edits:

```bash
find . -name "*.py" | sort
ls -la
cat pyproject.toml 2>/dev/null || cat setup.py 2>/dev/null || cat requirements.txt 2>/dev/null
```

Identify:
- Project structure (single file vs. package)
- TRX version in use (`from maltego_trx.*` or `from extensions.*`)
- Number of transform classes
- Public transform IDs, display names, input entities, output entities, and
  settings from registries, decorators, CSV/config files, and transform classes
- API/client modules used by transforms, including shared clients and request
  construction helpers
- No-result, partial-result, exception, and user-message behavior
- If the source resembles the public `MaltegoTech/maltego-trx-examples`
  project, load `references/known-trx-examples.md` before planning so you can
  compare TRX patterns such as `register_transform_function`,
  `MaltegoTransform().returnOutput()`, `request.Slider`, sidecar CSV lookups,
  and entity aliases like `maltego_trx.entities.IPAddress`.

### 2. Run Contract and Inventory Scripts (if available)

If the migration scripts agent has provided scripts in `scripts/`:

```bash
python scripts/trx_contract.py <trx-project-path> --output source-contract.json
python scripts/trx_inventory.py <trx-project-path> --output inventory.json
python scripts/trx_migration_report.py inventory.json > migration-report-draft.md
python scripts/std_entity_lookup.py <entity-type>
```

See `scripts/README.md` for details. These scripts do not write code — they report only.

Treat `trx_contract.py` as the source-contract extraction step. Do not rely on
CSV/discovery metadata alone: generated or wrapper-heavy TRX projects may keep
the true transform behavior in decorator metadata and wrapper dispatch calls,
including wrapper output arguments that are missing from CSV files. Investigate
any `csv_output_drift`, `missing_csv_row`, or `multiple_wrapper_outputs`
warning before writing the migration plan.

### 3. Map TRX Patterns to SDK Equivalents

Load `references/trx-to-sdk-mapping.md` for the full mapping table.
If the project looks like the public TRX examples, also load
`references/known-trx-examples.md` to compare the legacy example shape against
the SDK-native target patterns.

Key mappings:
| TRX pattern | SDK equivalent |
|-------------|--------------|
| `class MyTransform(DiscoverableTransform)` | `@register_transform` async function |
| `request.Value` | `input_entity.value` |
| `response.addEntity(entity_type, value)` | `return [EntityClass(value=value)]` |
| `response.addUIMessage(msg)` | `context.log.inform(msg)` or `.partial(msg)`; emitted as `result.events[].data.statusMessage`, not `status.uiMessages` |
| `request.getTransformSetting(name)` | `settings.get(name)` (via `settings: Dict[str, Any]` param) |
| `request.Slider` | `slider: int` (or `limit: int`) function parameter — injected by name first, then `int` annotation |
| `request.getSourceEntity().getProperty(name)` | `input_entity.<property_name>` |

`request.Slider` is the legacy TRX source signal for Maltego's slider input. In
SDK transforms, add a `slider: int` (or `limit: int`) parameter to the transform
function. The SDK matches it by parameter name first (`slider` or `limit`), then
by `int` type annotation on any remaining unresolved parameter. Do not convert
slider input into a normal `TransformSetting` unless the source also defines an
ordinary transform setting for that value.

### 4. Map Entity Strings to Standard Classes

Load `references/standard-entity-selection.md` for entity class lookup.

For each `entity_type` string found in TRX code (e.g., `"maltego.Domain"`):
- Find the matching `maltego.entities` class.
- If no match exists, flag as a custom entity requiring design decision.

### 5. Classify Migration Difficulty

Load `references/trx-risk-taxonomy.md` for the full risk classification.

| Difficulty | Criteria |
|-----------|----------|
| **Simple** | Class body only uses `request.Value` + `response.addEntity()`. No settings, auth, overlays. |
| **Medium** | Uses settings, OAuth, multi-entity output, or chained transforms. |
| **Complex** | Uses overlays, link labels, entity properties, generated config, custom auth handlers, or raw XML. |

### 6. Identify Manual Decision Points

Flag these for human review in the migration plan:
- Custom entity types with no standard equivalent.
- TRX overlays or link decorations (no direct SDK equivalent).
- Custom authentication (e.g., OAuth flows coded in TRX) -> rewrite using `OAuthAuthenticator` and `OAuthMiddleware`.
- Generated local config files (iTDS-style).
- Raw XML construction in `response.addEntity()`.

### 7. Produce the Migration Plan Document

Write a migration plan with:

```markdown
# TRX Migration Plan: <project-name>

## Summary
- Total transforms: N
- Simple: N | Medium: N | Complex: N
- Estimated effort: S/M/L

## Public SDK Evidence
- SDK transform registration: <Freshdesk article title, e.g. "Writing Your First Transform (Quickstart)", or src/maltego/...>
- SDK entity/settings/context behavior: <Freshdesk article title, e.g. "Standard Entities Overview" or "Transform Settings", or src/maltego/...>

## Migration Contract
- Preserve externally visible transform behavior.
- Preserve transform IDs/names unless incompatible with SDK naming.
- Preserve input/output entity types and key properties.
- Preserve settings semantics.
- Preserve API/client behavior.
- Rewrite transform authoring to SDK-native APIs.
- Do not preserve TRX registry/wrapper/discovery artifacts unless explicitly requested.

## Source Behavior Evidence
- Transform IDs/names: <workspace-relative file>:<line or section>
- Settings: <workspace-relative file>:<line or section>
- API/client behavior: <workspace-relative file>:<line or section>
- Entity/property mapping: <workspace-relative file>:<line or section>
- No-result/error/user-message behavior: <workspace-relative file>:<line or section>
- Source contract extraction: <source-contract.json plus source files that prove transform IDs, decorator metadata, and wrapper dispatch calls>

## Transform Mapping Table
| TRX Class | SDK Function Name | Input Entity | Output Entities | Difficulty | Notes |
|-----------|-----------------|--------------|-----------------|-----------|-------|
| MyTransform | my_transform | Domain | IPv4Address | Simple | Direct rewrite |
| OAuthTransform | oauth_transform | Person | EmailAddress | Medium | Use `OAuthAuthenticator` |

## Entity Mapping Table
| TRX entity string | SDK class | Notes |
|-------------------|----------|-------|
| maltego.Domain | Domain | Standard |
| custom.MyType | — | Custom entity — design needed |

## Manual Decision Points
1. ...
2. ...

## Risky TRX Idioms Found
- ...

## Recommended Order of Migration
1. Simple transforms first (N transforms)
2. Medium transforms (N transforms)
3. Complex transforms — manual review first (N transforms)

## Assumptions
- ...
```

Use workspace-relative paths in JSON, YAML, and Markdown planning artifacts. Do not write machine-local absolute paths into planning artifacts.

Cite SDK evidence with public `https://` docs URLs or repository paths.
Use known public Freshdesk links when available, or article titles plus repository paths such as `src/maltego/...` and `src/tests/...` so later scoring can verify the claim without internal context. Do not invent page-specific public URLs.

### 8. Do NOT Recommend Classic Compatibility

Do NOT recommend:
- Wrapping TRX classes in the SDK compatibility shims as the default path.
- Keeping MTZ/classic discovery patterns.
- Retaining classic package assumptions.

The goal is a clean SDK rewrite.

## Routing

- **Execute the plan**: load `maltego-trx-migration-implementer`.
- **Entity selection details**: load `references/standard-entity-selection.md`.
- **Public TRX example comparisons**: load
  `references/known-trx-examples.md` when the source resembles
  `maltego-trx-examples` or uses `register_transform_function`,
  `MaltegoTransform().returnOutput()`, `request.Slider`, or sidecar CSV
  lookups.
- **Common SDK target mechanics**: load `maltego-transform-basics`.
- **Implementation workflow**: load `maltego-transform-build`.

## What NOT to Do

- Do NOT edit any code during planning.
- Do NOT skip the migration plan document — the implementer requires it.
- Do NOT recommend compatibility shims as the primary migration path.
- Do NOT declare a TRX pattern unsupported or a no-op without checking the SDK source or docs; if it truly has no equivalent, flag it as a manual decision point with the evidence you checked.
- Do NOT assume internal infrastructure.
