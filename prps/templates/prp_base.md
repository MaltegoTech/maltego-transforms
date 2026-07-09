name: "Base PRP Template - Context-Rich with Validation Loops"
description: |
  Template optimized for AI agents to implement SDK changes with enough
  context and self-validation to reach working code through iterative
  refinement.

## Purpose

Use this template to write a PRP before any non-trivial SDK change. The PRP
should give an agent all context, constraints, and validation commands needed
to make the change without guessing at APIs or drifting scope.

## Core Principles

1. **Context is king**: Include all necessary documentation, examples, source
   files, and caveats.
2. **Validation loops**: Provide executable tests, lints, type checks, or
   runtime checks the agent can run and fix.
3. **Information dense**: Use concrete names, symbols, paths, and patterns from
   this codebase.
4. **Progressive success**: Start simple, validate, then enhance.
5. **Global rules**: Follow `AGENTS.md`, `CONTRIBUTING.md`, and the runbooks.

---

## Goal

[What needs to be built - be specific about the end state and desired behavior]

## Why

- [Business value and user impact]
- [Integration with existing features]
- [Problem this solves and who it solves it for]
- [Rejected approaches and why they are wrong for this repo]

## What

[User-visible behavior and technical requirements]

### Success Criteria

- [ ] [Specific measurable outcome]

## All Needed Context

### Documentation & References

```yaml
# MUST READ - include these in the implementer's context window
- file: AGENTS.md
  why: Repository rules, test gates, public-tooling constraints, and agent guidance

- file: runbooks/using-prps.md
  why: PRP expectations and execution rules

- file: [path/to/example.py]
  why: [Pattern to follow, gotchas to avoid]

- doc: [Public documentation URL]
  section: [Specific section about the API or behavior]
  critical: [Key insight that prevents common errors]

- docfile: [prps/ai_docs/file.md]
  why: [Project-local notes or docs pasted into the repo]
```

### Current Codebase Tree

Run `tree` or `find` from the repository root and paste the relevant slice.

```bash

```

### Desired Codebase Tree

List files to add or modify and each file's responsibility.

```bash

```

### Known Gotchas and Library Quirks

```python
# CRITICAL: [Library name or SDK component] requires [specific setup]
# Example: Transform functions must be async and fully typed for discovery.
# Example: The generated project is the canonical reference for starter behavior.
# Example: Use standard entities before defining custom entities.
```

## Implementation Blueprint

### Data Models and Structure

Describe the core models, settings, transforms, routes, or helpers. Include
exact names and signatures where they matter.

```python
# Examples:
# - pydantic models
# - transform input/output entity types
# - helper function signatures
# - configuration objects
```

### Tasks to Complete the PRP

```yaml
Task 1:
MODIFY src/existing_module.py:
  - FIND symbol: "class ExistingClass"
  - INJECT behavior in method: "existing_method"
  - PRESERVE existing public method signatures

CREATE src/new_feature.py:
  - MIRROR pattern from: src/similar_feature.py
  - KEEP error handling pattern identical

Task N:
...
```

### Per-Task Pseudocode

```python
# Task 1
# Pseudocode with critical details; do not write the entire implementation.
async def new_feature(param: str) -> Result:
    # PATTERN: validate input first (see src/validators.py)
    validated = validate_input(param)  # raises ValidationError

    # GOTCHA: pass context into IntegrationClient so limits/errors are tracked
    result = await client.get_json(url, context=context)

    # PATTERN: return typed entities so discovery advertises output types
    return [Domain(result["domain"])]
```

### Integration Points

```yaml
CONFIG:
  - add to: src/maltego/config.py
  - pattern: "SETTING = os.getenv('SETTING', 'default')"

CLI:
  - add to: src/maltego/_cli.py
  - pattern: "parse arguments explicitly and keep usage text current"

TESTS:
  - add to: src/tests/test_feature.py
  - pattern: "write the failing test first, then minimal implementation"
```

## Validation Loop

### Level 1: Syntax and Style

```bash
# Run these first where relevant; fix errors before proceeding.
poetry run ruff check src/path/to_changed_file.py
poetry run mypy src/maltego/path/to_changed_file.py --config-file resources/mypy.ini
```

Expected: no new errors in changed files. If errors appear, read the error,
fix the root cause, and rerun.

### Level 2: Unit Tests

```python
def test_happy_path():
    """Basic functionality works."""
    result = new_feature("valid_input")
    assert result.status == "success"


def test_validation_error():
    """Invalid input is rejected."""
    with pytest.raises(ValueError):
        new_feature("")
```

```bash
poetry run pytest src/tests/test_new_feature.py -q
```

Expected: pass. If failing, read the failure, understand the root cause, fix
code, and rerun. Do not mock around the behavior under test.

### Level 3: Integration or Runtime Test

```bash
# Start the generated project or SDK server if this PRP changes runtime behavior.
python project.py

# In another shell, confirm discovery or execution behavior.
curl http://127.0.0.1:3000/api/v3/transforms
```

Expected: [specific response, transform shape, or observable behavior]

## Final Validation Checklist

- [ ] All required tests pass: `[exact command]`
- [ ] No new lint/type errors in changed files: `[exact command]`
- [ ] Runtime/manual check succeeds: `[specific command]`
- [ ] Error cases are covered
- [ ] Logs are informative and do not expose raw entity values or secrets
- [ ] Documentation/runbooks are updated if behavior changed
- [ ] Definition of done has evidence for each item

---

## Anti-Patterns to Avoid

- Do not create new patterns when existing ones work.
- Do not skip validation because "it should work".
- Do not ignore failing tests; fix them.
- Do not use sync transform functions.
- Do not hardcode values that belong in configuration.
- Do not catch all exceptions unless an existing pattern explicitly requires it.
- Do not assume internal infrastructure, private feeds, or non-public tooling.
