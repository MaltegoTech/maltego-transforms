# Runbook: Using PRPs (structured planning prompts)

A **PRP** is a structured requirement/planning prompt you write *before* touching code for any non-trivial SDK change: a new feature, a migration, a cross-cutting refactor, or any change where multiple approaches could look plausible. It is the plan an agent (or a human) executes. A good PRP is the single highest-leverage way to keep an agent from hallucinating APIs, drifting scope, or "fixing" things that were deliberately left alone.

PRPs are required for non-trivial changes. Skip one only for a one-line fix that does not change behavior, public API, packaging, release flow, or generated project output.

## Where PRPs live

- Put PRPs under `prps/`.
- Start from `prps/templates/prp_base.md`.
- Name each PRP for the change, for example `prps/add-rate-limit-context-prp.md`.
- Keep all paths workspace-relative and all commands runnable with public tooling.

## Anatomy of a good PRP

1. **Background & the "why" (read first).** State the current behavior and the problem. Crucially, list **rejected approaches** and *why* they were rejected — this stops an agent from confidently re-implementing a dead end. This section is often the most valuable part.
2. **Scope + explicit non-goals.** Name what changes and, separately, what must **not** change (existing endpoints, wire fields, semantics). Non-goals prevent scope creep and accidental regressions.
3. **Files to touch — located by symbol, not line number.** Point at functions/classes by name (`V3Server._register_routes`, `TransformResultSet.event_count`). Line numbers drift; symbols don't. If you cite a line, mark it as a drift-prone anchor.
4. **The design, concretely.** Route shapes, function signatures, field names, data flow. For public/wire-facing names, get them right the first time — they are unrenameable after release.
5. **Points that need verification.** Flag any assumption the implementer must confirm against real code (e.g. event ordering) rather than guess. Say "verify X in `file.py`, derive the rule, document it, test it" instead of asserting a rule you're unsure of.
6. **Test matrix.** Enumerate cases per file, including regression cases proving unchanged behavior stays unchanged.
7. **Verification commands.** The exact `pytest` / lint / type commands to run, and any schema/discovery check.
8. **Definition of done.** A checklist. Each item is objectively checkable.

## How an agent should execute a PRP

1. Read `AGENTS.md`, then read the whole PRP — especially Background and Non-goals — before editing anything.
2. Locate code by the symbols the PRP names; confirm they still exist.
3. Do the verification steps the PRP flags **before** finalizing behavior; document what you found.
4. Implement, then run the full test matrix + verification commands. Paste real output.
5. Walk the definition-of-done checklist and confirm each item with evidence.

## Principles

- **Additive and backward-compatible by default.** Prefer new opt-in routes/fields over changing existing semantics.
- **Name things correctly up front**, especially anything on the public wire.
- **Verify, don't assume.** If the PRP or the code is ambiguous, derive the answer from source and tests, document the assumption, and cover it with a test.
- **Portable artifacts only** — workspace-relative paths, public tooling, no internal infrastructure assumptions.
