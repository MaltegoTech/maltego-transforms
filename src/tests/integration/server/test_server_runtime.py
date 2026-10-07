# Copyright (c) Maltego Technologies GmbH.
"""Server lifespan cleanup scheduling and ``API_*`` FastAPI settings."""
import asyncio
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from maltego.server import MaltegoServerSettings, MaltegoTransformServer

pytestmark = pytest.mark.integration


@pytest.fixture
def api_env(monkeypatch):
    for name in list(os.environ):
        if name.upper().startswith("API_"):
            monkeypatch.delenv(name)
    return monkeypatch


def _server(**kwargs) -> MaltegoTransformServer:
    return MaltegoTransformServer(
        settings=MaltegoServerSettings(server_name="runtime", ns="runtime", author="pytest", **kwargs)
    )


@pytest.mark.asyncio
async def test_lifespan_startup_completes_and_cleanup_runs():
    """Regression: fastapi-restful 0.6.0 ``repeat_every`` blocked startup forever."""
    server = _server(scheduled_cleanup_seconds=1)
    ran = asyncio.Event()

    async def run_lifespan() -> None:
        async with server.app.router.lifespan_context(server.app):
            await ran.wait()

    with (
        patch.object(server.runner, "cleanup", side_effect=ran.set) as cleanup,
        patch.object(server.runner, "shutdown", wraps=server.runner.shutdown) as shutdown,
    ):
        await asyncio.wait_for(run_lifespan(), 10)

    assert cleanup.call_count >= 1
    shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_cleanup_continues_after_failure():
    server = _server(scheduled_cleanup_seconds=1)
    second_call = asyncio.Event()
    calls = 0

    def cleanup() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        second_call.set()

    async def run_lifespan() -> None:
        async with server.app.router.lifespan_context(server.app):
            await second_call.wait()

    with patch.object(server.runner, "cleanup", side_effect=cleanup):
        await asyncio.wait_for(run_lifespan(), 10)

    assert calls >= 2


def test_fastapi_defaults_without_api_env(api_env):
    app = _server().app
    assert (app.debug, app.title, app.version, app.openapi_url, app.root_path) == (
        False, "FastAPI", "0.1.0", "/openapi.json", ""
    )
    assert (app.docs_url, app.redoc_url) == (None, None)


def test_fastapi_settings_read_api_env(api_env):
    api_env.setenv("API_DEBUG", "true")
    api_env.setenv("API_OPENAPI_PREFIX", "/pfx")
    api_env.setenv("api_title", "Lower")
    api_env.setenv("API_DOCS_URL", "/docs")
    app = _server().app
    assert (app.debug, app.root_path, app.title) == (True, "/pfx", "Lower")
    assert (app.docs_url, app.redoc_url) == (None, None)


def test_fastapi_settings_disable_docs(api_env):
    api_env.setenv("API_DISABLE_DOCS", "1")
    assert _server().app.openapi_url is None


def test_fastapi_settings_invalid_value_fails_construction(api_env):
    api_env.setenv("API_DEBUG", "notabool")
    with pytest.raises(ValidationError):
        _server()
