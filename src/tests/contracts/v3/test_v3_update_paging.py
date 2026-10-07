# Copyright (c) Maltego Technologies GmbH.
"""A client that pages results while the run is still going receives every entity update."""
import asyncio
import threading
import typing

import httpx
import pytest

from maltego.model.context import MaltegoContext
from maltego.model.server import MaltegoServerSettings
from maltego.server import MaltegoTransformServer
from tests.conftest import MOCK_HEADER_V3, MOCK_TRANSFORM_RUN_REQUEST_V3, NAMESPACE, PREFIX, Phrase

pytestmark = pytest.mark.contract

GATE_TIMEOUT = 10


class Gates:
    def __init__(self) -> None:
        self.first_update = threading.Event()
        self.polled = threading.Event()
        self.second_update = threading.Event()
        self.finish = threading.Event()


async def _wait(event: threading.Event) -> None:
    for _ in range(GATE_TIMEOUT * 100):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("gate not released")


@pytest.fixture
def gated_server() -> typing.Iterator[tuple[MaltegoTransformServer, Gates]]:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE, ns=NAMESPACE, author=NAMESPACE, api_prefix=PREFIX,
        full_host_url="https://maltoso.com/",
    )
    server = MaltegoTransformServer(settings=settings)
    gates = Gates()

    @server.register_transform(display_name="Update across polls", name="update_across_polls", transform_set="pytest")
    async def update_across_polls(input_entity: Phrase, context: MaltegoContext) -> list[Phrase]:
        tag = Phrase("v0")
        context.graph.add_entity(tag)
        tag.value = "v1"
        gates.first_update.set()
        await _wait(gates.polled)
        tag.value = "v2"
        gates.second_update.set()
        await _wait(gates.finish)
        return []

    server.setup(settings)
    server.runner.startup()
    yield server, gates
    server.runner.shutdown()


def _texts(events: list[dict]) -> list[str]:
    return [
        prop["value"]
        for event in events
        if event["data"].get("eventType") == "UPDATE"
        for prop in event["data"]["entity"].get("properties") or []
        if prop["name"] == "text"
    ]


@pytest.mark.asyncio
async def test_update_after_a_poll_reaches_a_client_that_already_read_the_earlier_update(
    gated_server: tuple[MaltegoTransformServer, Gates],
) -> None:
    server, gates = gated_server
    transform = f"{NAMESPACE}.update_across_polls"
    headers = {**MOCK_HEADER_V3, "user-agent": "Maltego Desktop/4.10.0 (Maltego One Eval; Pytest)"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        run = await client.post(f"{PREFIX}/transforms/{transform}/run", json=MOCK_TRANSFORM_RUN_REQUEST_V3, headers=headers)
        assert run.status_code == 201
        results_url = f"{PREFIX}/transforms/{transform}/run/{run.json()['result']['runId']}/results"

        pointer, received = 0, []

        async def poll() -> dict:
            nonlocal pointer
            response = await client.get(results_url, params={"eventPointer": pointer, "eventLimit": 50}, headers=headers)
            result = response.json()["result"]
            received.extend(result["events"])
            pointer += len(result["events"])
            return result

        assert await asyncio.to_thread(gates.first_update.wait, GATE_TIMEOUT)
        await poll()
        assert _texts(received) == ["v1"]

        gates.polled.set()
        assert await asyncio.to_thread(gates.second_update.wait, GATE_TIMEOUT)
        await poll()
        gates.finish.set()

        result = None
        for _ in range(GATE_TIMEOUT * 10):
            result = await poll()
            if result["state"] == "COMPLETED" and pointer >= result["eventCount"]:
                break
            await asyncio.sleep(0.1)

    assert result is not None and result["state"] == "COMPLETED"
    assert _texts(received) == ["v1", "v2"]
    assert pointer == result["eventCount"]
