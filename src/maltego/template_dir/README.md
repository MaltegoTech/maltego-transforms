# New Maltego integration

This project was generated with ``maltego-transforms start``. Bare is the
default project manager, so the generated project starts without a
``pyproject.toml`` unless you ask for one explicitly. It is intended to be both
a runnable starter project and a reference for the SDK's common patterns. To
generate only the setup files without example transform modules, use
``maltego-transforms start --minimal <project_name>``.

To generate a Poetry starter project, run:

```bash
maltego-transforms start --project-manager poetry <project_name>
```

To generate a uv starter project, run:

```bash
maltego-transforms start --project-manager uv <project_name>
```

## What's in this project

- ``project.py`` imports the example transforms, defines ``MaltegoServerSettings``,
  and starts the local server.
- ``transforms/quickstart_example.py`` shows the basic transform and custom
  entity flow.
- ``transforms/entity_features_example.py`` demonstrates overlays, notes,
  display fields, and link metadata.
- ``transforms/pagination_example.py`` shows paginated API patterns.
- ``transforms/input_constraints_example.py``,
  ``transforms/logging_example.py``, ``transforms/prompts_example.py``, and
  ``transforms/error_handling_example.py`` cover the corresponding runtime
  features.
- ``transforms/middleware_example.py`` shows how to keep authorization,
  auditing, and logging in a `TransformMiddleware` instead of the transform
  itself, so those concerns can be swapped out independently.
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

To run locally with HTTPS, generate a local certificate pair outside source
control:

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout .local/server.key \
  -out .local/server.crt \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Then set those paths on ``ServerHTTPSettings`` in ``project.py``:

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
- Remove the example transform modules you do not need and add your own.
- Generate local HTTPS certificates only when you need HTTPS during
  development, and never commit private keys or real credentials.
