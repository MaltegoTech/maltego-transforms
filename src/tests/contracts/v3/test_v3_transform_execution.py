# Copyright (c) Maltego Technologies GmbH.
import time
import typing
from unittest.mock import patch, MagicMock

import asyncio
import fastapi
import httpx
import pytest

from maltego.middlewares.verify_metadata_middleware import VerifyMetadataMiddleware
from maltego.model.context import MaltegoContext, MaltegoUserAgent
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoClient, MaltegoClientFilter
from maltego.pagination import PageBasedPaginator
from maltego.server import MaltegoTransformServer
from maltego.util import IntegrationClient
from maltego.model.types import ExecutionState
from maltego.protocol.v3.execution.transform_run import TransformRunPromptResponse
from tests.conftest import (
    EXAMPLE_TRANSFORM_TEST_CASES, GRAPH_BROWSER_1_0_0, GRAPH_BROWSER_2_0_0, GRAPH_BROWSER_2_1_0, GRAPH_BROWSER_3_0_0,
    GRAPH_BROWSER_3_0_2,
    MOCK_HEADER_V3,
    MOCK_TRANSFORM_RUN_REQUEST_GRAPH_V3,
    MOCK_TRANSFORM_RUN_REQUEST_V3, MOCK_TRANSFORM_RUN_REQUEST_V3_LIST_IN, MOCK_TRANSFORM_RUN_REQUEST_V3_PERSON_IN,
    MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN, MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_COUNT,
    MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_ENTITY, NAMESPACE, PREFIX, UA_4_0_0, UA_4_10_0, UA_4_7_0, UA_4_8_2,
    entity_of_type,
    UA_4_8_1,
)

pytestmark = pytest.mark.contract


def clean_response_data_list(result_response: typing.Any) -> typing.Any:
    return [clean_response_data(response.json()) for response in result_response]


def clean_response_data(data_in: typing.Any) -> typing.Any:
    data = data_in.copy()
    if "startTime" not in data.get("result", {}):
        return data
    data["result"]['startTime'] = 0
    for event in data["result"]['events']:
        if "entity" in event['data']:
            event['data']['entity']['id'] = 111
        if "link" in event['data']:
            event['data']['link']['sourceId'] = -1
            event['data']['link']['id'] = 111
            event['data']['link']['targetId'] = 999
    data["result"]['updateTime'] = 0
    data["result"]['runId'] = 0
    for i, _ in enumerate(data["result"]['events']):
        data["result"]['events'][i]["timestamp"] = 0
    return data


@pytest.mark.asyncio
async def run_v3_transform(
        async_client_example_server: httpx.AsyncClient,
        transform: typing.Any,
        payload: typing.Any,
        prefix: typing.Optional[str] = None,
        expected_run_response: int = 201,
        expected_status_response: int = 200,  # R3-1: GET returns 200, not 201
        headers: typing.Any = None,
        composed: bool = False,
) -> typing.Tuple[httpx.Response, typing.Union[httpx.Response, typing.List[httpx.Response]]]:
    if headers is None:
        headers = MOCK_HEADER_V3
    run_url = f"transforms/{transform}/run"
    if prefix:
        run_url = f"{prefix}/{run_url}"

    headers['user-agent'] = 'Maltego Desktop/4.10.0 (Maltego One Eval; Pytest)'
    if composed:
        headers["maltego-client-capabilities"] = "compositeEntities"
    run_response = await async_client_example_server.post(
        run_url,
        json=payload,
        headers=headers
    )
    print(
        f'Testing Transform {transform} '
        f'on URL {run_url} '
        f'Expected status code: {expected_run_response}. '
        f'Got {run_response.status_code}'
    )
    print(run_response.json())
    assert run_response.status_code == expected_run_response
    if expected_run_response > 299:
        return run_response, run_response
    data = run_response.json()
    run_id = data.get("result").get("runId")
    assert run_id
    status_url = f"transforms/{transform}/run/{run_id}/results"
    if prefix:
        status_url = f"{prefix}/{status_url}"
    status = None
    i = 0
    last_response = None
    event_count = 0
    status_responses = []  # type: ignore
    while status not in ("COMPLETED", "FAILED"):
        await asyncio.sleep(0.1)
        headers = MOCK_HEADER_V3
        if composed:
            headers["maltego-client-capabilities"] = "compositeEntities"
        response = await async_client_example_server.get(
            status_url,
            headers=headers,
        )
        print(response.json())
        event_count = response.json()["result"]["eventCount"]
        status_code = response.status_code
        assert status_code == expected_status_response
        last_response = response
        if expected_status_response in (500,):
            return run_response, status_responses  # type: ignore
        status = response.json().get("result").get("state")
        assert i <= 10
        i = i + 1

    fetched_event_count = 0
    while fetched_event_count < event_count:
        headers = MOCK_HEADER_V3
        if composed:
            headers["maltego-client-capabilities"] = "compositeEntities"
        response = await async_client_example_server.get(
            status_url,
            headers=headers,
            params={
                "eventPointer": fetched_event_count,
                "eventLimit": 50
            }
        )
        status_responses.append(response)
        fetched_event_count += len(response.json()["result"]["events"])

    assert status in ("COMPLETED", "FAILED")
    assert last_response is not None
    return run_response, status_responses


@pytest.mark.asyncio
@pytest.mark.slow
async def test_async_execution(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    start = time.time()
    runs = []
    ids = []
    for i in range(1, 5):
        runs.append(
            async_client_example_server.post(
                f"/api/v3/transforms/{PREFIX}.{NAMESPACE}.transform_async/run",
                json=MOCK_TRANSFORM_RUN_REQUEST_V3,
                headers=MOCK_HEADER_V3
            )
        )
    for i in runs:  # type:ignore
        result = await i  # type:ignore
        assert result.status_code == 201
        data = result.json()
        ids.append(data.get("result").get("runId"))
        assert snapshot == clean_response_data(data)
    await asyncio.sleep(1)  # Give Transforms 1 sec to execute
    num_runs = 0
    while len(ids) > 0:
        for i, run_id in enumerate(ids):
            result = await async_client_example_server.get(
                f"/api/v3/transforms/{PREFIX}.{NAMESPACE}.transform_async/run/{run_id}/results",
                headers=MOCK_HEADER_V3
            )
            assert result.status_code == 200  # R3-1: GET returns 200, not 201
            data = result.json()
            assert num_runs < 10
            if data["result"]["state"] == "COMPLETED":
                assert len(data["result"]["events"]) == 2
                assert snapshot == clean_response_data(data)
                ids.pop(i)
        num_runs += 1
        await asyncio.sleep(0.1)  # Super racey

    exec_time = time.time() - start
    assert exec_time < 2


@pytest.mark.asyncio
async def test_graph_transform(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.Graph",
        MOCK_TRANSFORM_RUN_REQUEST_GRAPH_V3
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_list_transform(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.List",
        MOCK_TRANSFORM_RUN_REQUEST_V3
    )
    assert len(status_response) == 1
    assert len(status_response[0].json()["result"]['events']) == 2
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)

    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.List",
        MOCK_TRANSFORM_RUN_REQUEST_V3_LIST_IN
    )
    assert len(status_response) == 1
    assert len(status_response[0].json()["result"]['events']) == 6
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_run_transform(async_client_mock_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_mock_server,
        f"{NAMESPACE}.Test",
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        prefix=PREFIX
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)
    # result gained 3 additive count fields (atomic/composite/incompleteComposite)
    assert len(run_response.json()["result"]) == 10
    assert len(status_response) == 1
    assert len(status_response[0].json()["result"]['events']) == 2


@pytest.mark.asyncio
async def test_legacy_v3_transform_run_routes_remain_available(
    async_client_mock_server: httpx.AsyncClient,
) -> None:
    transform = f"{NAMESPACE}.Test"
    run_response = await async_client_mock_server.post(
        f"{PREFIX}/api/v3/transforms/{transform}/run",
        json=MOCK_TRANSFORM_RUN_REQUEST_V3,
        headers=MOCK_HEADER_V3,
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["result"]["runId"]

    results_response = await async_client_mock_server.get(
        f"{PREFIX}/api/v3/transforms/{transform}/run/{run_id}/results",
        headers=MOCK_HEADER_V3,
    )
    assert results_response.status_code == 200  # R3-1: GET returns 200, not 201

    status_response = await async_client_mock_server.get(
        f"{PREFIX}/api/v3/transforms/{transform}/run/{run_id}/status",
        headers=MOCK_HEADER_V3,
    )
    assert status_response.status_code == 200  # R3-1: GET returns 200, not 201

    delete_response = await async_client_mock_server.delete(
        f"{PREFIX}/api/v3/transforms/{transform}/run/{run_id}",
        headers=MOCK_HEADER_V3,
    )
    assert delete_response.status_code == 200


@pytest.mark.asyncio
async def test_run_transform_examples(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    for transform_name, test_details in dict(EXAMPLE_TRANSFORM_TEST_CASES).items():
        run_response, result_response = await run_v3_transform(
            async_client_example_server,
            transform_name,
            test_details["v3payload"],
            expected_run_response=test_details["expected_v3status_run"],
            expected_status_response=test_details["expected_v3status_result"]
        )
        assert snapshot == clean_response_data(run_response.json())
        snapshot.assert_match(
            [clean_response_data(response.json())
             for response in result_response]
        )


@pytest.mark.asyncio
async def test_run_transform_404(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    run_response, _ = await run_v3_transform(
        async_client_example_server,
        "maltego.404",
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        expected_run_response=404,
    )
    assert run_response.headers["content-type"].startswith("application/json")
    assert list(run_response.json()) == ["detail"]
    assert snapshot == clean_response_data(run_response.json())


@pytest.mark.asyncio
async def test_prompt_response_keeps_protocol_and_state_headers(
    mock_server_example: MaltegoTransformServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = mock_server_example.v3server
    assert server is not None

    class FakeRunner:
        def result(self, run_id: str) -> typing.Any:
            return type("FakeResult", (), {"state": ExecutionState.COMPLETED})()

        async def prompt_response(self, run_id: str, prompt_id: str, transform_prompt_response: typing.Any) -> None:
            return None

    fake_runner = FakeRunner()
    monkeypatch.setattr(server, "transform_runner", fake_runner)

    fastapi_response = fastapi.Response()
    result = await server.post_prompt_response(
        transform_id=f"{PREFIX}.{NAMESPACE}.transform",
        run_id="run-123",
        prompt_id="prompt-123",
        response=fastapi_response,
        transform_run_prompt_response=TransformRunPromptResponse(
            reason="COMPLETED",
            result={"choice": "A"},
        ),
        maltego_protocol_version=None,
    )

    assert result.status_code == 204
    assert result.headers["maltego-protocol-version"] == "3.1"
    assert result.headers["maltego-run-state"] == ExecutionState.COMPLETED.value


@pytest.mark.asyncio
async def test_run_transform_wrong_input_entity_type(async_client_example_server: httpx.AsyncClient,
                                                     snapshot: typing.Any) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_person"
    run_response, _ = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        expected_run_response=400,
    )
    assert snapshot == clean_response_data(run_response.json())

    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3_PERSON_IN,
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_context_log(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_logging"
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        expected_run_response=201,
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)
    assert len(status_response) == 1
    events = status_response[0].json()["result"]["events"]
    assert len(events) == 6

    assert events[0]["data"]["inputType"] == "STATUS_MESSAGE"
    assert events[0]["data"]["statusMessage"]["text"] == "debug"

    assert events[1]["data"]["inputType"] == "STATUS_MESSAGE"
    assert events[1]["data"]["statusMessage"]["text"] == "inform"

    assert events[2]["data"]["inputType"] == "STATUS_MESSAGE"
    assert events[2]["data"]["statusMessage"]["text"] == "fatal"

    assert events[3]["data"]["inputType"] == "STATUS_MESSAGE"
    assert events[3]["data"]["statusMessage"]["text"] == "partial"

    assert events[4]["data"]["inputType"] == "ENTITY"
    assert events[5]["data"]["inputType"] == "LINK"


@pytest.mark.asyncio
async def test_entity_update(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_update_entity"
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        expected_run_response=201,
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)
    # NYI!! Reactivate later
    assert len(status_response) == 1
    # assert status_response[0].json()["events"][0]["data"]["eventType"] == "UPDATE"


@pytest.mark.asyncio
async def test_list_in_to_single_input(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform"
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3_LIST_IN,
        expected_run_response=201,
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)
    assert len(status_response) == 1
    assert len(status_response[0].json()["result"]["events"]) == 4


@pytest.mark.asyncio
async def test_verify_metadata_wrong_entities(
        mock_server_example: MaltegoTransformServer,
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any
) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform"
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_ENTITY,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )
    assert len(mock_server_example.runner.middlewares) == 2
    assert isinstance(
        mock_server_example.runner.middlewares[0], VerifyMetadataMiddleware)
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_verify_metadata_wrong_count(
        mock_server_example: MaltegoTransformServer,
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any
) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform"
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_COUNT,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )
    assert len(mock_server_example.runner.middlewares) == 2
    assert isinstance(
        mock_server_example.runner.middlewares[0], VerifyMetadataMiddleware)
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_verify_link_properties(
        mock_server_example: MaltegoTransformServer,
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any
) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_link_properties_test"
    run_response, result_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )
    assert len(mock_server_example.runner.middlewares) == 2
    assert isinstance(
        mock_server_example.runner.middlewares[0], VerifyMetadataMiddleware)

    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == [clean_response_data(
        response.json()) for response in result_response]


@pytest.mark.asyncio
async def test_non_existing_entity(
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any,
) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_child3"
    run_response, _ = await run_v3_transform(
        async_client_example_server,
        transform_name,
        entity_of_type("maltego.foo"),
        expected_run_response=400,
    )

    assert snapshot == clean_response_data(run_response.json())


@pytest.mark.asyncio
async def test_child_entity(
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any,
) -> None:
    child1_entity_transform_request = entity_of_type("maltego.Child1Entity")
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_child1"
    run_response, result_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        child1_entity_transform_request,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )

    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == [clean_response_data(
        response.json()) for response in result_response]

    transform_name = f"{PREFIX}.{NAMESPACE}.transform_parent1"
    run_response, result_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        child1_entity_transform_request,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )

    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == [clean_response_data(
        response.json()) for response in result_response]


@pytest.mark.asyncio
async def test_run_transform_unknown_input_entity_type(
        async_client_example_server: httpx.AsyncClient,
        snapshot: typing.Any,
) -> None:
    transform_name = f"{PREFIX}.{NAMESPACE}.transform_unknown_input"
    run_response, result_response = await run_v3_transform(
        async_client_example_server,
        transform_name,
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        expected_run_response=201,
        expected_status_response=200  # R3-1: GET returns 200
    )

    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == [clean_response_data(
        response.json()) for response in result_response]


@pytest.mark.asyncio
async def test_link_property_transform(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.transform_link_properties_test",
        MOCK_TRANSFORM_RUN_REQUEST_GRAPH_V3
    )
    assert snapshot == clean_response_data(run_response.json())
    assert snapshot == clean_response_data_list(status_response)


@pytest.mark.asyncio
async def test_stream_all_items_unsafe():
    # Mock response for successful request
    common_content = [{"data": "some data"} for _ in range(5)]
    special_content = [{"data": "different data"}]
    common_response = httpx.Response(200, json=common_content)
    special_response = httpx.Response(200, json=special_content)

    def response_to_items(resp):
        data = resp.json()
        if isinstance(data, list):
            return data

        raise ValueError("Could not return items from api response.")

    # Side effect function to return different responses
    def request_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            return common_response
        else:
            return special_response

    call_count = 0

    with patch('httpx.AsyncClient.request', side_effect=request_side_effect):
        integration_client = IntegrationClient()

        paginator = PageBasedPaginator(
            client=integration_client,
            response_to_items=response_to_items,
            page_size=5,
            page_size_param_name="pageSize",
            page_param_name="pageIndex"
        )
        all_items = []
        page_fetched = 0
        mock_request = MagicMock()
        mock_request.headers = {}
        async for items in paginator.stream_all_items_unsafe(
                slider=4000,
                context=MaltegoContext(request=mock_request, graph=MaltegoGraph()),
                params={"pageSize": 5, "pageIndex": 0},
                headers={},
                url="some_url.api",
        ):
            page_fetched += 1
            all_items.extend(items)
        assert len(all_items) == 16
        assert page_fetched == 4


@pytest.mark.asyncio
async def test_stream_all_items():
    # Mock response for successful request
    common_content = [{"data": "some data"} for _ in range(5)]
    special_content = [{"data": "different data"}]
    common_response = httpx.Response(200, json=common_content)
    special_response = httpx.Response(200, json=special_content)

    def response_to_items(resp):
        data = resp.json()
        if isinstance(data, list):
            return data

        raise ValueError("Could not return items from api response.")

    # Side effect function to return different responses
    def request_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            return common_response
        else:
            return special_response

    call_count = 0

    with patch('httpx.AsyncClient.request', side_effect=request_side_effect):
        integration_client = IntegrationClient()

        paginator = PageBasedPaginator(
            client=integration_client,
            response_to_items=response_to_items,
            page_size=5,
            page_size_param_name="pageSize",
            page_param_name="pageIndex"
        )
        all_items = []
        page_fetched = 0
        mock_request = MagicMock()
        mock_request.headers = {}
        async for items in paginator.stream_all_items(
                slider=4000,
                context=MaltegoContext(request=mock_request, graph=MaltegoGraph()),
                params={"pageSize": 5, "pageIndex": 0},
                headers={},
                url="some_url.api",
        ):
            page_fetched += 1
            all_items.extend(items)
        assert len(all_items) == 16
        assert page_fetched == 4


@pytest.mark.asyncio
async def test_transform_read_display_names(async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.transform_read_display_names",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN
    )
    run_result = run_response.json()["result"]
    assert run_result["state"] == "INITIALIZED"
    assert run_result["eventCount"] == 0

    assert isinstance(status_response, list)
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]["events"]
    entity_values = [
        event["data"]["entity"]["properties"][0]["value"]
        for event in result_events
        if event["data"]["inputType"] == "ENTITY"
    ]
    assert entity_values == ["Text", "User ID", "Post Id", "daterange", "datetime"]


@pytest.mark.asyncio
async def test_client_version_filtering(async_client_example_server: httpx.AsyncClient) -> None:
    # 4.8.1, 4.8.2 for desktop
    # 3.0.0, 3.0.1 for desktop
    desktop_client_excluding_headers = UA_4_8_2
    desktop_client_including_headers = UA_4_8_1
    graph_browser_excluding_headers = GRAPH_BROWSER_3_0_2
    graph_browser_including_headers = GRAPH_BROWSER_3_0_0
    transform_response_desktop_excluding = await async_client_example_server.get('/api/v3/transforms', headers=desktop_client_excluding_headers)
    assert transform_response_desktop_excluding.status_code == 200
    transform_response_desktop_including = await async_client_example_server.get('/api/v3/transforms', headers=desktop_client_including_headers)
    assert transform_response_desktop_including.status_code == 200
    assert len(
        (transform_response_desktop_including.json())["transforms"]
    ) == len((transform_response_desktop_excluding.json())["transforms"])+2

    transform_response_web_excluding = await async_client_example_server.get('/api/v3/transforms', headers=graph_browser_excluding_headers)
    assert transform_response_web_excluding.status_code == 200
    transform_response_web_including = await async_client_example_server.get('/api/v3/transforms', headers=graph_browser_including_headers)
    assert transform_response_web_including.status_code == 200

    assert len(
        (transform_response_web_including.json())["transforms"]
    ) == len((transform_response_web_excluding.json())["transforms"])+2


# Filters
filters = [
    MaltegoClientFilter(
        max_clients=[{"name": "Maltego Desktop", "version": (4, 8, 1)}],
        min_clients=[{"name": "Maltego Desktop", "version": (4, 5, 0)}],
    ),
    MaltegoClientFilter(
        max_clients=[MaltegoClient(
            name="Maltego Graph Browser", version=(2, 0, 0))],
        min_clients=[MaltegoClient(
            name="Maltego Graph Browser", version=(1, 0, 0))],
    ),
    MaltegoClientFilter(
        max_clients=[("Maltego Desktop", (4, 7, 0)),
                     ("Maltego Graph Browser", (2, 0, 0))],
        min_clients=[("Maltego Desktop", (4, 5, 0)),
                     ("Maltego Graph Browser", (1, 0, 0))],
    ),
]


@pytest.mark.parametrize(
    "client_filter, headers, expected",
    [
        # Filter 1: Desktop only
        (filters[0], UA_4_7_0, True),  # Matches: within range
        (filters[0], UA_4_8_1, True),  # Matches: at max range
        (filters[0], GRAPH_BROWSER_2_0_0, False),  # Fails: unsupported client
        (filters[0], GRAPH_BROWSER_3_0_0, False),  # Fails: unsupported client

        # Filter 2: Graph Browser only
        (filters[1], UA_4_7_0, False),  # Fails: unsupported client
        (filters[1], UA_4_8_1, False),  # Fails: unsupported client
        (filters[1], GRAPH_BROWSER_3_0_0, False),  # Fails: exceeds max
        (filters[1], GRAPH_BROWSER_2_0_0, True),  # Matches: within range

        # Filter 3: Desktop and Graph Browser
        (filters[2], UA_4_7_0, True),  # Matches: within range
        (filters[2], UA_4_8_1, False),  # Fails: exceeds max
        (filters[2], GRAPH_BROWSER_3_0_0, False),  # Fails: exceeds max
        (filters[2], GRAPH_BROWSER_1_0_0, True),  # Matches: within range
    ],
)
def test_client_filter(client_filter, headers, expected):
    """
    Testing MaltegoClientFilter against different headers/user agent
    """
    user_agent_str = headers.get("user-agent", None)
    user_agent = MaltegoUserAgent(user_agent_str)

    match, message = client_filter.match(user_agent, headers)
    print(client_filter, headers, expected)
    assert match == expected


@pytest.mark.asyncio
async def test_entity_display_name_type_coercion(async_client_example_server: httpx.AsyncClient, snapshot: typing.Any) -> None:
    expected_list_got_str = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.ExtendedPhraseListStr": 1
                },
                "entitiesTotalCount": 1,
                "linksTotalCount": 0,
                "rootEntitiesCount": 1
            },
            "graph": {
                "entities": [
                    {
                        "id": "2fse051hmsm01",
                        "valueRef": "text",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "text",
                                "value": "something",
                                "type": "STRING",
                                "displayName": "Text",
                                "matchingRule": "loose"
                            },
                            {
                                "name": "list_str",
                                "value": "brr",
                                "type": "STRING",
                                "displayName": "List of Strings",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.ExtendedPhraseListStr",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    }
                ],
                "links": []
            }
        },
        "limit": 12,
        "transformFields": [
            {
                "name": "test.oauth.token",
                "value": 111
            }
        ],
        "transformSettings": []
    }
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.extended_phrase_list_str_input_test",
        expected_list_got_str,
    )
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 2

    assert result_events[0]["data"]["inputType"] == "ENTITY"
    assert result_events[0]["data"]["entity"]["type"] == "maltego.ExtendedPhraseListStr"
    assert result_events[0]["data"]["entity"]["properties"][1]["value"] == ["brr"]

    expected_str_got_list = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.ExtendedPhraseListStr": 1
                },
                "entitiesTotalCount": 1,
                "linksTotalCount": 0,
                "rootEntitiesCount": 1
            },
            "graph": {
                "entities": [
                    {
                        "id": "2fse051hmsm01",
                        "valueRef": "text",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "text",
                                "value": ["something", "else"],
                                "type": "STRING",
                                "displayName": "Text",
                                "matchingRule": "loose"
                            },
                            {
                                "name": "list_str",
                                "value": ["brr"],
                                "type": "STRING",
                                "displayName": "List of Strings",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.ExtendedPhraseListStr",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    }
                ],
                "links": []
            }
        },
        "limit": 12,
        "transformFields": [
            {
                "name": "test.oauth.token",
                "value": 111
            }
        ],
        "transformSettings": []
    }

    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.extended_phrase_list_str_input_test",
        expected_str_got_list,
    )
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 2

    assert result_events[0]["data"]["inputType"] == "ENTITY"
    assert result_events[0]["data"]["entity"]["type"] == "maltego.ExtendedPhraseListStr"
    assert result_events[0]["data"]["entity"]["properties"][0]["value"] == "something, else"


# ---------------------------------------------------------------------------
# Cancel endpoint + top-level entity counts (atomic/composite). The per-page
# incompleteCompositeEntity field lives only on /results, not on the summary.
# ---------------------------------------------------------------------------


async def _run_to_completion(
    client: httpx.AsyncClient,
    transform: str,
    payload: typing.Any,
    headers: typing.Any = None,
    composed: bool = False,
) -> str:
    """POST a run and poll /results until COMPLETED. Returns the run_id."""
    if headers is None:
        headers = dict(MOCK_HEADER_V3)
    headers["user-agent"] = "Maltego Desktop/4.10.0 (Maltego One Eval; Pytest)"
    if composed:
        headers["maltego-client-capabilities"] = "compositeEntities"
    run_response = await client.post(
        f"transforms/{transform}/run", json=payload, headers=headers
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["result"]["runId"]
    status_url = f"transforms/{transform}/run/{run_id}/results"
    state = None
    for _ in range(20):
        await asyncio.sleep(0.1)
        response = await client.get(status_url, headers=headers)
        state = response.json()["result"]["state"]
        if state in ("COMPLETED", "FAILED"):
            break
    assert state == "COMPLETED"
    return run_id


@pytest.mark.asyncio
async def test_cancel_endpoint_cancels_without_deleting(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    run_id = await _run_to_completion(
        async_client_example_server, transform, MOCK_TRANSFORM_RUN_REQUEST_V3
    )

    cancel_response = await async_client_example_server.post(
        f"transforms/{transform}/run/{run_id}/cancel",
        headers=MOCK_HEADER_V3,
    )
    assert cancel_response.status_code == 200
    summary = cancel_response.json()
    assert summary["state"] == "CANCELED"
    assert "atomicEntityCount" in summary
    assert "compositeEntityCount" in summary
    # incompleteCompositeEntity is a per-page concept and lives only on /results,
    # not on the cancel/DELETE summary.
    assert "incompleteCompositeEntity" not in summary
    assert summary["atomicEntityCount"] >= 1
    assert summary["compositeEntityCount"] == 0

    # run is still alive and drainable via /results
    results_response = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=MOCK_HEADER_V3,
    )
    assert results_response.status_code == 200
    assert len(results_response.json()["result"]["events"]) >= 1

    # an explicit DELETE still tears the run down
    delete_response = await async_client_example_server.delete(
        f"transforms/{transform}/run/{run_id}",
        headers=MOCK_HEADER_V3,
    )
    assert delete_response.status_code == 200

    # after teardown the run is gone (404)
    gone_response = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=MOCK_HEADER_V3,
    )
    assert gone_response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_endpoint_without_client_capabilities(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    run_id = await _run_to_completion(
        async_client_example_server, transform, MOCK_TRANSFORM_RUN_REQUEST_V3
    )
    headers = {
        key: value
        for key, value in MOCK_HEADER_V3.items()
        if key.lower() != "maltego-client-capabilities"
    }
    cancel_response = await async_client_example_server.post(
        f"transforms/{transform}/run/{run_id}/cancel",
        headers=headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["state"] == "CANCELED"


@pytest.mark.asyncio
async def test_cancel_endpoint_404_for_unknown_run(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    cancel_response = await async_client_example_server.post(
        f"transforms/{transform}/run/does-not-exist/cancel",
        headers=MOCK_HEADER_V3,
    )
    assert cancel_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_summary_includes_counts(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    run_id = await _run_to_completion(
        async_client_example_server, transform, MOCK_TRANSFORM_RUN_REQUEST_V3
    )
    delete_response = await async_client_example_server.delete(
        f"transforms/{transform}/run/{run_id}",
        headers=MOCK_HEADER_V3,
    )
    assert delete_response.status_code == 200
    summary = delete_response.json()
    assert summary["atomicEntityCount"] >= 1
    assert summary["compositeEntityCount"] == 0
    # incompleteCompositeEntity is per-page and not part of the summary shape.
    assert "incompleteCompositeEntity" not in summary


@pytest.mark.asyncio
async def test_delete_cancelled_param_behavior_unchanged(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    run_id = await _run_to_completion(
        async_client_example_server, transform, MOCK_TRANSFORM_RUN_REQUEST_V3
    )
    delete_response = await async_client_example_server.delete(
        f"transforms/{transform}/run/{run_id}?Cancelled=true",
        headers=MOCK_HEADER_V3,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["state"] == "CANCELED"


@pytest.mark.asyncio
async def test_results_counts_atomic_run(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.transform"
    run_id = await _run_to_completion(
        async_client_example_server, transform, MOCK_TRANSFORM_RUN_REQUEST_V3
    )
    response = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=MOCK_HEADER_V3,
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["atomicEntityCount"] >= 1
    assert result["compositeEntityCount"] == 0
    assert result["incompleteCompositeEntity"] is False


@pytest.mark.asyncio
async def test_results_counts_composite_run(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    transform = f"{PREFIX}.{NAMESPACE}.composed_affiliation_transform"
    run_id = await _run_to_completion(
        async_client_example_server,
        transform,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        composed=True,
    )
    # large window: whole graph fits, so no composite is split
    response = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers={**MOCK_HEADER_V3, "maltego-client-capabilities": "compositeEntities"},
        params={"eventPointer": 0, "eventLimit": 1000},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    # one composite parent (AffiliationComposite) is counted as composite; its
    # children (Person, Aliases, UniqueIdentifier) are composite children and so
    # are excluded from BOTH counts -- the run emits no top-level atomic entity.
    assert result["compositeEntityCount"] == 1
    assert result["atomicEntityCount"] == 0
    assert result["incompleteCompositeEntity"] is False


@pytest.mark.asyncio
async def test_results_incomplete_composite_at_boundary(
    async_client_example_server: httpx.AsyncClient,
) -> None:
    # oversize transform emits 40 composite groups -> a small window cuts one
    transform = f"{PREFIX}.{NAMESPACE}.oversize_composed_affiliation_transform"
    run_id = await _run_to_completion(
        async_client_example_server,
        transform,
        MOCK_TRANSFORM_RUN_REQUEST_V3,
        composed=True,
    )
    composed_headers = {
        **MOCK_HEADER_V3,
        "maltego-client-capabilities": "compositeEntities",
    }
    # In the served output the input entity is not echoed, so each composite
    # group is 6 contiguous events:
    #   [0] composite parent (AffiliationComposite)
    #   [1] composite child (Person, value-entity)
    #   [2] composite child (UniqueIdentifier)
    #   [3] composite property link
    #   [4] composite property link
    #   [5] ordinary connecting link (input->parent; NOT composite-tagged) <- last
    # Cutting after the parent (limit=1) leaves composite children/links
    # un-returned -> incomplete.
    response = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=composed_headers,
        params={"eventPointer": 0, "eventLimit": 1},
    )
    assert response.status_code == 200
    assert response.json()["result"]["incompleteCompositeEntity"] is True
    total = response.json()["result"]["eventCount"]

    # Boundary on the TRAILING ordinary connecting link (limit=5 -> first
    # un-returned event is the non-composite input->parent link of group 0): the
    # composite entity's internals (parent + children + composite property
    # links) are all present, so this is NOT mid-composite by design. This pins
    # the "composite-internals-complete" semantics against future
    # emission/link-tagging refactors.
    boundary_on_connecting_link = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=composed_headers,
        params={"eventPointer": 0, "eventLimit": 5},
    )
    assert (
        boundary_on_connecting_link.json()["result"]["incompleteCompositeEntity"]
        is False
    )

    # The final page (whose window reaches the last emitted event) sits on a
    # clean boundary because the run COMPLETED on a whole composite group.
    # Page size is server-capped, so step the pointer to the tail explicitly.
    page_size = 50
    last_pointer = max(0, total - page_size)
    last_page = await async_client_example_server.get(
        f"transforms/{transform}/run/{run_id}/results",
        headers=composed_headers,
        params={"eventPointer": last_pointer, "eventLimit": page_size},
    )
    assert last_page.json()["result"]["incompleteCompositeEntity"] is False
