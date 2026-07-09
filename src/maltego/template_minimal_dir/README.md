# New Maltego integration

This project was generated with ``maltego-transforms start --minimal``. Bare is
the default project manager, so the generated project starts without a
``pyproject.toml`` unless you ask for one explicitly. It is a setup-only
starter for developers who want to add their own transform modules without the
SDK example files.

To generate a Poetry starter project, run:

```bash
maltego-transforms start --project-manager poetry <project_name>
```

To generate a uv starter project, run:

```bash
maltego-transforms start --project-manager uv <project_name>
```

## What's in this project

- ``project.py`` defines ``MaltegoServerSettings`` and starts the local server.
- ``transforms/`` is an empty package where you can add transform modules.
- ``--project-manager bare`` keeps the current bare layout, ``poetry`` writes a
  ``pyproject.toml`` for Poetry, and ``uv`` writes a ``pyproject.toml``
  intended for uv.
- Local development starts over HTTP by default. For HTTPS, generate local
  certificates yourself and keep private keys out of source control.

## Setup

Create a virtual environment using Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project dependencies:

```bash
pip install -r requirements.txt
```

## Run

Start the server:

```bash
source .venv/bin/activate
python project.py
```

The seed endpoint will be available at ``http://127.0.0.1:3000/seed``.

To run locally with HTTPS, generate a local certificate pair under an
untracked directory such as ``.local/`` and set those paths on
``ServerHTTPSettings`` in ``project.py``:

```python
settings = MaltegoServerSettings(
    server_name="New Maltego Integration",
    ns="acme.new_maltego_integration",
    author="Acme Corp",
    http_settings=ServerHTTPSettings(
        protocol="https",
        cert_key=".local/server.key",
        cert_file=".local/server.crt",
        cors_allowed_origins=["https://app.maltego.com"],
    ),
)

run_server(settings=settings)
```

## First edits to make

- Update ``server_name``, ``ns``, and ``author`` in ``project.py``.
- Add transform modules under ``transforms/``.
- Import those modules from ``project.py`` so their ``@register_transform``
  decorators run at startup.
- Generate local HTTPS certificates only when you need HTTPS during
  development, and never commit private keys or real credentials.
