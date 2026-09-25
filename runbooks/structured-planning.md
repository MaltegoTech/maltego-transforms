# Runbook: Structured Planning

Before a non-trivial SDK change, choose one planning format. A one-line fix
that does not change behavior, SDK API, packaging, release flow, or
generated-project output may skip planning.

## Choose a format

- **PRP**: use for an implementation-ready plan. Create it under `prps/` from
  `prps/templates/prp_base.md`.
- **OpenSpec**: use for an evolving behavioral contract. Create the proposed
  change under `openspec/changes/`; see `openspec/README.md`.

Do not duplicate the same plan in both formats. Update an existing active
artifact when it already covers the change.

## Select OpenSpec artifacts

Every OpenSpec change has a proposal and tasks. Add a spec delta when the
change alters observable behavior. Add a design when the work needs a durable
decision record; it is required for contracts and migrations.

- **Contracts**—discovery routes, transform execution, headers, serialized
  entities or errors, protocol versions, capabilities, or client-specific
  behavior—need specs and a compatibility design. The design records old and
  new consumer behavior, opt-in or fallback behavior, and proof for every
  supported consumer.
- **Toolchain and generated-project migrations**—dependencies, package
  managers, packaging, supported Python, CLI scaffolding, or templates—need a
  migration design. Record preserved workflows, transition or fallback, and
  packaging or template verification.

If no spec-level behavior changes, mark the change `skip_specs: true` in its
`.openspec.yaml` instead of creating an empty spec file. Refactors with no
observable behavior change and ordinary documentation changes normally belong
in a PRP instead.

## Include

State the intended behavior, scope and non-goals, compatibility expectations,
affected symbols or paths, tests, verification commands, and a clear definition
of done. Use only repository-verifiable, reproducible context.

## Before implementation

Read the chosen artifact in full, confirm its referenced symbols still exist,
and resolve open questions with source and tests. For OpenSpec, run:

```bash
openspec validate --all --strict
```
