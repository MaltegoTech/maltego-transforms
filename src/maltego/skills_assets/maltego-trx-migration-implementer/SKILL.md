---
name: "maltego-trx-migration-implementer"
description: "Load this skill when executing a TRX-to-SDK migration plan: rewriting transform classes to async SDK functions, mapping entities, and preserving unsupported patterns."
compatibility: "Requires Python 3.10+ and local access to the source TRX project; post-migration verification needs a running SDK server (default http://127.0.0.1:8080)."
metadata:
  version: "1.0.0"
---

# Maltego TRX Migration Implementer Skill

## Purpose
Execute a migration plan produced by the `maltego-trx-migration-planner` skill. Rewrite TRX transform classes to SDK async functions. Do NOT make broad edits without a plan.

## Golden Rule
**A migration plan MUST exist before you make broad code changes.** If no plan exists, run `maltego-trx-migration-planner` first.

## Workflow Shape

Recommended path:

1. Read the planner's migration contract and source behavior evidence.
2. Implement the SDK-native rewrite.
3. Verify the required outcomes.
4. If the source resembles the public `MaltegoTech/maltego-trx-examples`
   project, load `references/known-trx-examples.md` from `maltego-trx-migration-planner` for a local comparison of
   `register_transform_function`, `MaltegoTransform().returnOutput()`,
   `request.Slider`, and sidecar CSV lookup patterns.

Optional deep dives:

- Load `maltego-transform-docs` only when installed source, tests, or generated examples do not settle an SDK API question.
- Load `maltego-transform-discover` only when direct discovery needs deeper debugging.
- Load `maltego-transform-test` only when transform execution, mocks, or runtime checks need more detail.
- load the same reference, `references/known-trx-examples.md` (from `maltego-trx-migration-planner`), when
  implementing function-style TRX transforms or public-example-shaped
  migrations that mirror the bundled public example patterns.
- Treat public-example-shaped migrations as a reason to load the same reference
  before editing.

Required outcomes:

- The planner's migration plan/contract is consumed (not regenerated); record any deviations in `migration-report.md`.
- SDK-native transform code with no TRX authoring imports or wrappers.
- Runtime checks pass for representative transforms, not only mocked helper tests.
- Direct SDK discovery through `/api/v3/transforms` matches the source contract.
- Portable artifacts that use workspace-relative paths.
- Migration completion gates pass before claiming success.

## Migration Completion Gates

A matching transform count is not sufficient. Do not declare completion until
all gates below pass or each deviation is explicitly documented.

1. **Source contract extraction** — use the planner's source-contract evidence.
   It must include decorator metadata and wrapper dispatch calls. Do not rely on
   CSV/discovery metadata alone; wrapper output arguments may be the only place
   typed dispatch behavior appears.
2. **Exact discovery parity** — compare `/api/v3/transforms` with the source
   contract for transform IDs, display names, input constraints, settings, and
   transform sets. Watch for namespace double-prefixing.
3. **Behavior-routing parity** — test representative source dispatch patterns,
   especially each distinct `(transformName, output_arg)` or equivalent routing
   pair.
4. **Runtime entrypoint parity** — documented command must exist and start the server from a clean checkout.
5. **Deliverable hygiene** — No `.agents/`, starter example transforms, `.venv/`, `wheelhouse/`, `__pycache__/`, MTZ/XML discovery artifacts, or generated local caches in the commit candidate unless the user explicitly asks to keep one.
6. **Report truthfulness** — Re-run verification after cleanup edits.
   migration-report.md and eval-run-log.md must not reference deleted files,
   stale commands, or unverified success.

Load `maltego-transform-test` for the run-and-poll mechanics. Do not mark the migration complete while verification artifacts are stale.

## Step-by-Step: Execute a Migration

### 1. Read the Migration Plan

Open the migration plan document (e.g., `migration-report.md` or `MIGRATION_PLAN.md`).

Check:
- `## Migration Contract`
- `## Source Behavior Evidence`
- Transform-by-transform mapping table
- Entity mapping table
- Manual decision points
- Risk classification (Simple / Medium / Complex)

Read and follow the `## Migration Contract` section before editing. Preserve the behavior contract before preserving source shape. Do not invent transform IDs, settings, entity mappings, or client behavior; derive them from the plan and source evidence. Do not copy TRX registry/wrapper/discovery artifacts unless the migration contract explicitly asks for compatibility-mode execution.
Document every contract deviation in `migration-report.md`.

### 2. Use Helper Scripts (if available)

If `scripts/trx_to_sdk_candidates.py` is available:

```bash
python scripts/trx_to_sdk_candidates.py <trx-project-path>
```

Review the output before applying. Dry-run is the default — never apply blindly.
Use `--write --report <migration-report.json> --output-dir <new-dir>` only after reviewing the generated candidates.

See `scripts/README.md` for full usage.

### 3. Implement Simple Transforms First

For each **Simple** transform in the plan:

1. Create a new `async` function file (or add to existing module).
2. Map `request.Value` → `input_entity.value`.
3. Map `response.addEntity(type_str, value)` → `return [EntityClass(value=value)]`.
4. Annotate the return type with the entity class(es) emitted (`-> list[EntityClass]`). This is published as the transform's output type in `/api/v3/transforms`; a bare `-> list` advertises no output type.
5. Decorate with `@register_transform`.
6. Run syntax check: `python -m py_compile <file>`.

The `name=` argument to `@register_transform` is the canonical transform ID suffix. It must exactly match the planned SDK transform ID suffix (for example, `place_details`, not `place_places` or `place_details_impl`).

Example rewrite:

```python
# TRX (old)
class DomainToIP(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        domain = request.Value
        for ip in resolve(domain):
            response.addEntity("maltego.IPv4Address", ip)

# SDK (new)
from maltego.server import register_transform
from maltego.model.context import MaltegoContext
from maltego.entities import Domain, IPv4Address

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    domain = input_entity.value
    return [IPv4Address(value=ip) for ip in await resolve_async(domain)]
```

### 4. Implement Medium Transforms

For each **Medium** transform:

1. Map settings: `request.getTransformSetting("KEY")` → `settings.get("KEY")` (via `settings: Dict[str, Any]` param).
2. Map TRX slider input: `request.Slider` → a `slider: int` (or `limit: int`) transform parameter. The SDK injects the Maltego slider value into that argument. Detection is name-based first (`slider` or `limit`), then by `int` annotation on any remaining parameter.
3. Map entity properties: `entity.addProperty(name, ...)` → `entity.<typed_attr> = value` or `entity.add_property(...)`.
4. Map multi-entity responses → return `MaltegoGraph` with multiple `add_entity()` calls, or annotate a union return (`-> list[A | B]`) when the source `addEntity` calls emit more than one entity type. Multiple/union return types are supported and all propagate to discovery; do not collapse a multi-type output to a bare `-> list`.
5. Declare settings in the `@register_transform` decorator.

Slider example:

```python
@register_transform(
    display_name="Fetch Products (Offset Pagination) [New Maltego Integration]",
    description="Fetch products from DummyJSON API using offset/limit pagination",
    transform_set=TRANSFORM_SET,
)
async def fetch_dummyjson_products(
    input_entity: Phrase,   # first positional param → single entity
    slider: int,            # name "slider" → Maltego slider value
    context: MaltegoContext,
) -> list[Phrase]:
    limit = slider
    ...
```

Use `settings: Dict[str, Any]` for declared transform settings. Use
`slider: int` (or `limit: int`) for the built-in Maltego slider input.
The SDK matches these by parameter name first, then by `int` type annotation.

### 5. Handle Complex Transforms

For each **Complex** transform:
- Do NOT attempt an automated rewrite for features with genuinely no SDK equivalent (preserve them as `TODO` items).
- However, ensure the following previously complex idioms are fully rewritten:
  - Entity overlays → rewrite using `entity.add_overlay()`
  - Link labels → supported natively. Use `link.set_property()` and `LinkColor`/`LinkStyle`/`LinkThickness`.
  - `UIM_PARTIAL` progress → rewrite using `context.log.partial()`

### 6. Remove TRX Registry Boilerplate

Remove or do not migrate:
- `registry.write_config(...)` — not needed in the SDK.
- `registry.write_local_mtz(...)` — not needed in the SDK.
- `registry.add_transform(...)` — not needed; `@register_transform` handles this.
- `if __name__ == "__main__": app.run(...)` — replaced by `project.py` calling `run_server()`.

### 7. Verify After Each Batch

After migrating each batch of transforms:

```bash
# Syntax check
python -m py_compile src/transforms/*.py

# Import check (replace run with the project's entrypoint module)
python -c "import run; print('OK')"

# Start server and check direct SDK discovery
python run.py &
sleep 2
curl -s http://127.0.0.1:8080/api/v3/transforms | python -m json.tool
```

Then execute representative transforms by POSTing to
`/api/v3/transforms/<transform_id>/run`, capture `result.runId`, poll
`/api/v3/transforms/<transform_id>/run/<runId>/results`, and verify emitted
entities, links, and status-message events against the source contract.

### 8. Keep Planning Artifacts Portable

Do not use absolute paths in planning or migration artifacts. Any JSON, YAML, or Markdown artifact written during migration must use paths relative to the workspace root. Do not call `os.path.abspath()`, `Path.resolve()`, or similar helpers when writing artifact paths unless the user explicitly asks for machine-local diagnostics.

### 9. Prefer SDK Rewrites Over Compatibility Shims

Do NOT:
- Wrap TRX classes in compatibility adapters as the permanent solution.
- Keep `DiscoverableTransform` subclasses alongside SDK functions long-term.
- Import from `maltego_trx` in the migrated code.

The target state is a clean SDK codebase with no TRX dependencies.

## References

> This skill is designed to be installed together with the rest of the set (via `--with-skills`). It loads several files from `maltego-trx-migration-planner` — `references/known-trx-examples.md` and `references/standard-entity-selection.md`. If you install skills individually, install the planner alongside this one or those references will be missing.

- Load `references/trx-to-sdk-mapping.md` for the full pattern-by-pattern mapping table.
- Load `maltego-transform-basics` for target SDK mechanics such as function signatures, settings injection, `context.log`, entity returns, graph returns, and `IntegrationClient` calls.

## Routing

- **No plan yet**: load `maltego-trx-migration-planner` first.
- **Testing the migrated server needs deeper guidance**: load `maltego-transform-test`.
- **Direct discovery needs deeper debugging**: load `maltego-transform-discover`.
- **Entity selection**: load `references/standard-entity-selection.md` from `maltego-trx-migration-planner`.
- **Public TRX example comparisons**: load
  `references/known-trx-examples.md` (from `maltego-trx-migration-planner`) when the migration source looks like the
  bundled public TRX examples or uses legacy function-style registration.

## What NOT to Do

- Do NOT make broad edits without a migration plan.
- Do NOT use MTZ discovery or classic package assumptions.
- Do NOT import `maltego_trx` in migrated transform code.
- Do NOT keep TRX compatibility shims as the default output.
- Do NOT declare a TRX pattern unsupported or a no-op without checking the SDK source or docs; if it truly has no equivalent, preserve it as a TODO with the evidence you checked.
- Do NOT assume proprietary internal infrastructure.
