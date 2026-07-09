# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Dict

import asyncio
import json

import httpx
import pytest

from maltego.util import IntegrationClient


GLOBAL = {}


@pytest.fixture()
def mocked_integration_client(monkeypatch: Any) -> Any:
    # Given an external client
    external_client = IntegrationClient(
        max_calls_per_period=2, period_length_seconds=0.2
    )

    last_mock_call: Dict[Any, Any] = {}

    async def mock_request(method: str, **kwargs: Dict[Any, Any]) -> httpx.Response:
        last_mock_call["method"] = method
        last_mock_call["kwargs"] = kwargs
        res = httpx.Response(status_code=200)
        monkeypatch.setattr(
            res,
            "_content",
            (
                b'{"json": true}'
                if "json" not in kwargs or kwargs["json"] is None
                else kwargs["json"]
            ),
        )
        return res

    monkeypatch.setattr(external_client.httpx_client, "request", mock_request)
    return external_client, last_mock_call


@pytest.fixture()
def minimal_integration_client(monkeypatch: Any) -> Any:
    # Given an external client
    external_client = IntegrationClient(
        max_calls_per_period=1,
        max_concurrent=1,
        max_concurrent_per_key=1,
        period_length_seconds=0.1,
    )

    last_mock_call: Dict[Any, Any] = {}

    async def mock_request(method: str, **kwargs: Dict[Any, Any]) -> httpx.Response:
        await asyncio.sleep(0.2)
        last_mock_call["method"] = method
        last_mock_call["kwargs"] = kwargs
        uuid_ = kwargs.get("uuid")
        if uuid_ not in GLOBAL:
            GLOBAL[uuid_] = 0
        res = httpx.Response(status_code=200)
        monkeypatch.setattr(
            res,
            "_content",
            bytes(
                json.dumps({"call_num": GLOBAL[uuid_], "request_id": kwargs.get("id")}),
                encoding="utf-8",
            ),
        )
        GLOBAL[uuid_] = GLOBAL[uuid_] + 1
        return res

    monkeypatch.setattr(external_client.httpx_client, "request", mock_request)
    return external_client, last_mock_call
