# Contributing to maltego-transforms

We'd love your contributions to `maltego-transforms`! Whether you're fixing a
bug, improving docs, or adding a feature — thank you for taking the time.

> **tl;dr** — `poetry install --with dev` to set up, `poetry run pytest` to
> run tests, `poetry run ruff check src/` for lint. Open an issue before
> starting anything substantial.

## Prerequisites

- **Python 3.10–3.14**
- [**Poetry**](https://python-poetry.org/) for dependency management
- [**git**](https://git-scm.com/)
- [**pre-commit**](https://pre-commit.com/) (optional but recommended)

## Development setup

```bash
git clone https://github.com/maltegotech/maltego-transforms.git
cd maltego-transforms
poetry install --with dev
pre-commit install --hook-type commit-msg   # optional: checks commit messages
```

## Running the tests

```bash
poetry run pytest
```

Tests are organized with markers (`unit`, `integration`, `contract`,
`packaging`, `template`, `security`, `snapshot`, `slow`) — see `pytest.ini`.
Run a focused subset with:

```bash
poetry run pytest -m unit
```

A passing test suite is the merge gate.

## Code style

[ruff](https://github.com/astral-sh/ruff) handles formatting and linting and
**is** a merge gate. pylint and mypy are configured and worth running locally
for deeper analysis, but are not required to be clean before merging.

```bash
poetry run ruff check src/          # lint
poetry run ruff format src/         # format
poetry run pylint src/ --rcfile resources/.pylintrc   # informational
poetry run mypy src/maltego --strict --config-file resources/mypy.ini  # informational
```

Before committing, avoid checking in credentials, keys, generated artifacts,
or local environment files.

## Commit messages

This repository follows [Conventional Commits](https://www.conventionalcommits.org/).
Commit messages should use the `<type>: <summary>` form, for example
`fix: handle missing transform input` or `docs: clarify snapshot testing`.

The dev dependencies include `pre-commit` and Commitizen. To check commit
messages locally before they are created, install the commit-msg hook:

```bash
poetry install --with dev
pre-commit install --hook-type commit-msg
```

You can also check a commit message file manually with:

```bash
poetry run cz check --commit-msg-file .git/COMMIT_EDITMSG
```

## AI policy

We welcome AI-assisted contributions. Please:

- Review and understand the code before submitting — you are accountable for
  what you submit, not your tool.
- Use a PRP for non-trivial AI-assisted changes before editing code; see
  `runbooks/using-prps.md` and `prps/templates/prp_base.md`.
- Write a clear PR description in your own words.
- Run the tests yourself; do not rely on the AI to verify correctness.

Mass-generated or unexplained pull requests will be closed without review.

## Documentation

Full SDK documentation lives at
[docs.maltego.com](https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview).
This repository does not contain the documentation source.

## Submitting a pull request

1. Fork the repository and create a feature branch off `main`.
2. For non-trivial changes, write or update a PRP under `prps/` **before**
   editing code. Use `runbooks/using-prps.md` and `prps/templates/prp_base.md`
   as your guide. One-line fixes that do not change behavior, public API,
   packaging, release flow, or generated project output can skip this step.
3. Make your change with tests.
4. Ensure `poetry run pytest` passes and `ruff check` is clean.
5. Update `CHANGELOG.md` under an `Unreleased` heading for any user-facing
   change.
6. Open a pull request with a description of what changed and why.

For substantial changes, open an issue first to align on approach before
investing significant time.

## Reporting bugs and requesting features

Please use GitHub Issues. When reporting a bug, include the package version:

```bash
python -c "from importlib.metadata import version; print(version('maltego-transforms'))"
```

A minimal reproduction makes triage much faster.

## Security issues

Do not open a public issue for security vulnerabilities. See
[SECURITY.md](SECURITY.md) for responsible disclosure.


## Contributors

Thank you to everyone who has contributed to `maltego-transforms`:

- Ege Kaan Gürkan ([@EgeKaanGurkan](https://github.com/EgeKaanGurkan))
- Elif Sahin ([@esmaltego](https://github.com/esmaltego))
- Gert Geringer ([@gertgeringer](https://github.com/gertgeringer))
- Robin Lösch ([@crest42](https://github.com/crest42))
- Tendai Marengereke ([@tendai-zw](https://github.com/tendai-zw))
