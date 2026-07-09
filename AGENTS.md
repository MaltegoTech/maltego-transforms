# AGENTS.md

Guidance for AI coding agents working in **`maltego-transforms`** — a Python SDK for building Maltego transform servers.

> This file is **provider-agnostic**: any AI coding agent (Claude, GPT, Gemini, Llama, etc.) should read it first. Provider-specific files (e.g. `CLAUDE.md`) may layer extra detail on top, but nothing here assumes a particular vendor or any internal Maltego infrastructure.

## What this repo is

`maltego-transforms` is the SDK for writing **transform servers**. A *transform* takes one or more Maltego entities as input (an IP, a domain, a person, a document, or your own custom type) and returns related entities as output — that is how Maltego expands a graph. You write async Python functions, decorate them, and the SDK serves them over an HTTP API that the Maltego client discovers and calls.

**Mental model:** entities in → transform function → related entities out. The SDK handles registration, typing, discovery (`/api/v3/transforms`), the FastAPI server, and serialization. You write the business logic.

## Where the code lives

| Path | What's there |
|------|--------------|
| `src/maltego/server/` | Transform server, `@register_transform`, FastAPI app, v3 API routes |
| `src/maltego/model/` | Core types: entities, graph, links, context, settings, exceptions, input constraints |
| `src/maltego/runner/` | Transform execution + paginated result streaming |
| `src/maltego/_cli.py` | The `maltego-transforms` CLI (project scaffolding) |
| `src/maltego/template_dir/` | The example-rich starter project (`maltego-transforms start` copies this) |
| `src/maltego/skills_assets/` | The provider-agnostic agent skills shipped by `--with-skills` |
| `src/tests/` | Tests, grouped by pytest markers (see below) |
| `runbooks/` | Operational guides for repeatable work such as PRPs and test runs |

Full documentation (quickstart, setup, entity features, pagination, migration, …) is published online from the Maltego Transforms SDK overview at https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview — this repository does not contain the documentation source.

**Standard entities** (`Phrase`, `Person`, `DNSName`, `IPv4Address`, …) live in the separate `maltego-transforms-std-entities` package, imported as `from maltego.entities import ...`. Prefer these before inventing custom entities.

## Setup, build, test (public tooling only)

Supported Python: **>=3.10, <3.15**. The repo uses **Poetry**.

```bash
# Working ON the SDK itself
poetry install
poetry run pytest -q                      # full suite
poetry run pytest -m unit -q              # fast subset (see markers below)
poetry run pytest src/tests/unit/test_runner.py -q

# Using the SDK to build a transform server
pip install maltego-transforms maltego-transforms-std-entities
```

Pytest markers (from `pytest.ini`) let you scope runs: `unit`, `integration`, `contract`, `packaging`, `template`, `security`, `snapshot`, `slow`. Async tests use `pytest-asyncio` with a session-scoped loop — write transform tests as `async def`.

The test suite is the merge gate: a change isn't done until `pytest` is green. `pylint`, `mypy`, and `autopep8` are configured and worth running, but they are **advisory** — the codebase is not currently clean under them, so they are not a gate. Do not commit keys, credentials, generated artifacts, or `.env` files.

## Write and run a transform

Scaffold a project (fastest path — the generated project is the canonical reference surface):

```bash
maltego-transforms start my_project          # example-rich starter (default: bare, requirements.txt)
maltego-transforms start --minimal my_project
maltego-transforms start --project-manager poetry my_project   # or: uv | bare
cd my_project && pip install -r requirements.txt && python project.py
# serves http://127.0.0.1:3000/seed
```

Minimal transform:

```python
from maltego.server import register_transform, MaltegoContext
from maltego.entities import Domain, IPv4Address   # standard entities first

@register_transform(display_name="Domain to IP")
async def domain_to_ip(input_entity: Domain, context: MaltegoContext) -> list[IPv4Address]:
    context.log.inform("looking up domain")        # metadata only — never log raw entity values (PII)
    return [IPv4Address("1.1.1.1")]
```

The input entity type comes from the **parameter annotation**; the output type(s) come from the **return annotation**. Both are published to `/api/v3/transforms` and drive which transforms the client offers. A bare `-> list` (untyped) breaks that routing.

## Agent skills — use these first

The SDK ships **provider-agnostic agent skills** (usable by any agent runtime that reads a skills directory). Generate them into a project with:

```bash
maltego-transforms start my_project --with-skills                    # writes .agents/skills/ + AGENTS.md
maltego-transforms start my_project --with-skills --skills-scope global   # ~/.agents/skills/
maltego-transforms install-skills --target .                         # add skills to an existing project
maltego-transforms install-skills --scope global                      # add skills globally
```

**How to use them (this is the main onboarding lever — it keeps you accurate and stops you guessing at APIs):**

1. Working *inside a generated project*? Read `.agents/skills/maltego-transform-skill-index/SKILL.md` **first**. It is a small routing table — it does not do the work, it points you to the one focused skill for your task.
2. Working *in the SDK repo itself*? Start from the `maltego-transforms` skill for orientation.
3. Load **one** focused skill at a time. Load its `references/` files only when the task actually needs them. Do not preload everything.

The focused skills: `maltego-transform-design` (model a new data source), `maltego-transform-build` (write transforms), `maltego-transform-basics` (quick mechanics reference), `maltego-transform-test` (local server testing), `maltego-transform-discover` (inspect a running server), `maltego-transform-docs` (look up SDK API / entity schemas), and the TRX migration pair `maltego-trx-migration-planner` → `maltego-trx-migration-implementer`.

## Conventions — do / don't

**Do**
- Write transforms as `async def` with full type hints on parameters and return.
- Import standard entities from `maltego.entities`; check them before defining custom ones.
- Pass `context=context` to every `IntegrationClient` call so limits/errors are tracked.
- Define each setting/transform-set name once as a module constant and reference it on both sides (`TransformSetting(name=...)` and `settings.get(...)`) — a mistyped literal silently reads back the default with no error.
- Keep credentials in `TransformSetting(auth=True, is_global=True)` and read them at runtime.
- Validate user-controlled `input_entity.value` before putting it in URLs, queries, or subprocess calls.
- Check `src/tests/` for an existing pattern before writing new tests.

**Don't**
- Don't write sync transforms, or use TRX idioms (`class MyTransform(DiscoverableTransform)`, `request.Value`, `response.addEntity()`).
- Don't hardcode API keys or base URLs.
- Don't log raw entity values — log operation metadata (log messages surface to the end user).
- Don't invent internal infrastructure, private feeds, or deployment specifics — the SDK is provider-agnostic and public tooling only.

## Where ground truth lives (look here before asking)

1. **The generated starter project** (`maltego-transforms start`) — runnable, canonical examples for every core pattern.
2. **The agent skill index** — routes you to the exact reference for your task.
3. **Installed source + `src/tests/`** — authoritative on actual behavior.
4. **Public docs:** https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview.

## How to verify your work

- `poetry run pytest` (scope with markers) — a green suite is the requirement. `pylint`/`mypy` are advisory (see above), not required to be clean.
- Start the server (`python project.py`) and confirm your transform appears in `GET /api/v3/transforms` with the expected input/output types. A missing transform or output type almost always means a missing/untyped annotation.
- Use the relevant runbook when the repo has one for the workflow, especially
  `runbooks/run-tests.md` for test selection and `runbooks/using-prps.md` for
  non-trivial changes.

## Structured planning with PRPs

For non-trivial SDK work (a new feature, a migration, a cross-cutting change), a short **PRP** (a structured requirement/planning prompt) is required *before* editing code. A good PRP dramatically reduces hallucinated APIs and rework. See `runbooks/using-prps.md` and start from `prps/templates/prp_base.md`. In short, a PRP states: the **why** (background + rejected approaches), explicit **scope / non-goals**, the **files to touch** (located by symbol, not brittle line numbers), a **test matrix**, **verification commands**, and a **definition of done**. Only one-line fixes that do not change behavior, public API, packaging, release flow, or generated project output can skip a PRP.
