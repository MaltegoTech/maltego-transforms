# OpenSpec

This directory is the repository's standard OpenSpec root. Keep it at the
repository root: the OpenSpec CLI discovers `openspec/config.yaml`,
`openspec/specs/`, and `openspec/changes/` there.

For every non-trivial SDK change, complete either a PRP or an OpenSpec change
before editing code. Use a PRP under `prps/` for an implementation-ready plan;
use OpenSpec when the work needs an evolving behavioral contract. Small,
one-line fixes that do not change behavior, SDK API, packaging, release
flow, or generated-project output may skip both.
See [`runbooks/structured-planning.md`](../runbooks/structured-planning.md) for
the selection rule.

## Layout

- `specs/` contains the source-of-truth behavior, organized by SDK domain.
- `changes/` contains proposed changes and the artifacts they require.
- `schemas/` contains the shared SDK schema and templates.

## One schema, selective artifacts

Every change uses the `sdk` schema. Start with `proposal.md` and `tasks.md`.
Add the other artifacts only when their trigger applies.

| Artifact | Add it when | It must cover |
| --- | --- | --- |
| `specs/` | A behavior, protocol, discovery result, serialized response, error, capability, or generated-project outcome changes | Normative requirements and observable scenarios |
| `design.md` | The work makes a decision that tasks cannot carry: it is always required for a contract change or a migration | Compatibility matrix, fallback or migration path, and focused proof |

For a change with no spec-level behavior delta, create
`.openspec.yaml` in its directory with `skip_specs: true`; do not create an
empty spec file. A routine refactor or documentation-only change normally
belongs in a PRP instead.

Create every OpenSpec change with the shared schema:

```bash
openspec new change <change-name>
```

## Working with OpenSpec

Start by reviewing the active work and select only the artifacts its risk
requires. For a protocol, discovery, serialized response, error, header,
capability, or client-specific change, add both specs and design: the design
must explain backward compatibility for existing consumers. For a dependency,
packaging, or generated-project migration, add design and record the preserved
workflow and fallback. Validate the result before implementation and again
before archiving:

```bash
openspec list
openspec validate --all --strict
```

Use repository-relative paths and repository-verifiable, reproducible evidence.
Keep secrets, credentials, and environment-specific operational details out of
all artifacts.
