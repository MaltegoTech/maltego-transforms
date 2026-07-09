# Runbook: Commit messages

The repository follows [Conventional Commits](https://www.conventionalcommits.org/).
Use the smallest truthful type and a short imperative summary:

```text
<type>: <summary>
```

Examples:

```text
fix: handle missing transform input
docs: clarify snapshot testing
test: cover public export filtering
chore: refresh commit message tooling
```

Before committing, install the commit-msg hook:

```bash
poetry install --with dev
pre-commit install --hook-type commit-msg
```

The hook runs Commitizen through pre-commit and checks the message before Git
creates the commit. If the hook fails, rewrite the message in Conventional
Commits format and commit again.
