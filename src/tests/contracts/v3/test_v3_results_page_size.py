# Copyright (c) Maltego Technologies GmbH.
"""Test requested V3 page sizes, capped at ``v3_page_size_max``.

A client stopping at its result limit requests the remainder once with
``eventLimit = eventCount - read``; that page must not be fixed at 50.
Composite pages include the whole result containing the requested boundary.
"""

import asyncio
import typing

import httpx
import pytest

from maltego.server import MaltegoTransformServer
from tests.conftest import MOCK_HEADER_V3, MOCK_TRANSFORM_RUN_REQUEST_V3, NAMESPACE, PREFIX

pytestmark = pytest.mark.contract

# 40 composite results yield 240 events, exceeding the default page size.
TRANSFORM = f"{PREFIX}.{NAMESPACE}.oversize_composed_affiliation_transform"
HEADERS = {
    **MOCK_HEADER_V3,
    "maltego-client-capabilities": "compositeEntities",
    "user-agent": "Maltego Desktop/4.10.0 (Maltego One Eval; Pytest)",
}
DEFAULT_PAGE = 50
RESULT_EVENTS = 6
# Allow all 40 results to complete.
RUN_REQUEST = {**MOCK_TRANSFORM_RUN_REQUEST_V3, "limit": 1000}


def _assert_page_size(page: dict[str, typing.Any], size: int) -> None:
    # Composite pages include the whole result containing the requested boundary.
    assert size <= len(page["events"]) < size + RESULT_EVENTS


async def _completed_run(client: httpx.AsyncClient) -> str:
    run_response = await client.post(f"transforms/{TRANSFORM}/run", json=RUN_REQUEST, headers=HEADERS)
    assert run_response.status_code == 201
    run_id = run_response.json()["result"]["runId"]
    for _ in range(50):
        await asyncio.sleep(0.1)
        state = (await client.get(_results_url(run_id), headers=HEADERS)).json()["result"]["state"]
        if state == "COMPLETED":
            return run_id
    raise AssertionError(f"run {run_id} did not complete")


def _results_url(run_id: str) -> str:
    return f"transforms/{TRANSFORM}/run/{run_id}/results"


async def _page(client: httpx.AsyncClient, run_id: str, **params: int) -> dict[str, typing.Any]:
    response = await client.get(_results_url(run_id), headers=HEADERS, params=params)
    assert response.status_code == 200
    return response.json()["result"]


@pytest.mark.asyncio
async def test_a_page_holds_the_rest_of_the_run_when_the_client_asks_for_it(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    run_id = await _completed_run(async_client_example_server)
    first = await _page(async_client_example_server, run_id, eventPointer=0, eventLimit=DEFAULT_PAGE)
    total = first["eventCount"]
    assert total > 2 * DEFAULT_PAGE

    read = len(first["events"])
    rest = await _page(async_client_example_server, run_id, eventPointer=read, eventLimit=total - read)

    assert len(first["events"]) + len(rest["events"]) == total
    assert rest["incompleteCompositeEntity"] is False


@pytest.mark.asyncio
async def test_a_page_without_event_limit_keeps_the_default_size(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    run_id = await _completed_run(async_client_example_server)

    page = await _page(async_client_example_server, run_id, eventPointer=0)

    _assert_page_size(page, DEFAULT_PAGE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page_size_max", "explicit_page", "default_page"),
    [(100, 100, DEFAULT_PAGE), (20, 20, 20)],
)
async def test_v3_page_size_max_caps_every_page(
    async_client_example_server: httpx.AsyncClient,
    mock_server_example: MaltegoTransformServer,
    monkeypatch: pytest.MonkeyPatch,
    page_size_max: int,
    explicit_page: int,
    default_page: int,
) -> None:
    run_id = await _completed_run(async_client_example_server)
    assert mock_server_example.v3server is not None
    monkeypatch.setattr(mock_server_example.v3server._settings, "v3_page_size_max", page_size_max)

    explicit = await _page(async_client_example_server, run_id, eventPointer=0, eventLimit=1000)
    default = await _page(async_client_example_server, run_id, eventPointer=0)

    _assert_page_size(explicit, explicit_page)
    _assert_page_size(default, default_page)
