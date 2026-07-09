# maltego-transforms

**The Python SDK for building Maltego transform servers.**

<!-- Badges activate once the repo goes public and the ci.yml workflow lands; they won't render against a private repo. -->
![Tests](https://github.com/MaltegoTech/maltego-transforms/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/maltego-transforms.svg)
![Python](https://img.shields.io/pypi/pyversions/maltego-transforms.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
<!-- ![Coverage](https://codecov.io/gh/MaltegoTech/maltego-transforms/branch/main/graph/badge.svg) — add once Codecov is configured -->

---

A **transform** takes one or more Maltego entities as input — an IP address, a domain, a person, a document, or your own custom object — and returns related entities as output. Transforms are how Maltego expands a graph, and `maltego-transforms` is the fastest way to write and run your own.

## Install

```bash
pip install maltego-transforms
```

Requires Python `>=3.10,<3.15`.

## Your first transform

```python
from maltego.server import (
    MaltegoContext,
    MaltegoEntity,
    MaltegoServerSettings,
    register_transform,
    run_server,
    setup,
)


@register_transform(
    display_name="Hello World [My Transforms]",
    transform_set="My Transforms",
)
async def hello_world(
    input_entity: MaltegoEntity,
    context: MaltegoContext,
) -> MaltegoEntity:
    context.log.inform(f"Hello from {context.remote_ip}")
    return MaltegoEntity["maltego.Phrase"](f"Hello, {input_entity.value}")  # type: ignore


if __name__ == "__main__":
    settings = MaltegoServerSettings(
        server_name="My Transform Server",
        ns="my.transforms",
        author="i@example.com",
    )
    setup(settings)
    run_server(settings=settings, ssl=False)  # plain HTTP for local development
```

Save this as `project.py` and run it:

```bash
python project.py
```

This starts a local HTTP server on `127.0.0.1:3000`, serving a seed URL at `/seed`. Add that URL to Maltego to discover and install your transforms. SSL is on by default for anything beyond local dev — see [HTTPS, Certificates, and Browser Trust](https://docs.maltego.com/en/support/solutions/articles/15000062366-https-certificates-and-browser-trust), which the Graph Browser client requires.

Prefer a ready-made project over a blank file?

```bash
maltego-transforms start my_project
cd my_project
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python project.py
```

This scaffolds a runnable project with example transforms covering the most common patterns.

## Runbooks

Repository runbooks live in [`runbooks/`](runbooks/) and capture repeatable
workflows for contributors and coding agents, including writing PRPs for
non-trivial changes and choosing the right test command.

## Features

- **Decorator-based registration** — `@register_transform` turns any function into a discoverable transform
- **Typed input and output** — plain Python type hints; the SDK infers and validates entity types for you
- **Async and streaming** — write `async def` transforms, or use `AsyncGenerator` to stream results as they're found
- **OAuth** — built-in support for OAuth-authenticated transforms
- **Transform settings** — expose configurable options (API keys, limits, toggles) that users fill in from the Maltego client
- **Input constraints** — control which entities a transform is even offered for, before it runs
- **Middlewares** — hook into the request/response lifecycle for logging, auth, or shared setup

## Standard entities

Want typed entity classes instead of raw dictionaries? [`maltego-transforms-std-entities`](https://docs.maltego.com/en/support/solutions/articles/15000062357-standard-entities-overview) ships ready-made classes like `Person`, `DNSName`, and `IPv4Address`:

```bash
pip install maltego-transforms-std-entities
```

```python
from maltego.entities import DNSName, IPv4Address
from maltego.server import register_transform

@register_transform
async def dns_to_ip(input_entity: DNSName) -> IPv4Address:
    return IPv4Address("1.1.1.1")
```

## Building with an AI coding agent

Scaffold a project with agent skills for authoring and testing transforms:

```bash
maltego-transforms start my-project --with-skills
```

This drops a skill index into `.agents/skills/` that points your coding agent at the right focused skill for the task at hand — building a new transform, migrating an existing one, or debugging discovery. See [Using AI Agent Skills with the SDK](https://docs.maltego.com/en/support/solutions/articles/15000062361-using-ai-agent-skills-with-the-sdk) for details.

## Documentation

Full docs — configuration, authentication, entity modeling, pagination, and the complete API reference — start at the **[Maltego Transforms SDK overview](https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview)**.

## Support

Questions or issues? Reach out through the [Maltego Support Portal](https://support.maltego.com/) or your Maltego account contact.

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

## License

`maltego-transforms` is licensed under the [MIT License](LICENSE).
