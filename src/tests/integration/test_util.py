# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=protected-access
import time
import pathlib
import pytest
import asyncio
import toml
import uuid
from httpx import Response
import httpx
from maltego.model.graph import MaltegoGraph
from unittest.mock import MagicMock

from maltego.server import MaltegoContext, __version__
from maltego.model.exception import MaltegoException
from maltego.util import IntegrationClient  # , OffsetPaginator

mock_request = MagicMock()
mock_request.headers = {}

CONTEXT = MaltegoContext(MaltegoGraph(), mock_request)
CLIENT_CALL_ARGS_GET = {
    "url": "https://test.com/api",
    "headers": {"Authorization": "Auth"},
    "params": {"filter": "test"},
}

CLIENT_CALL_ARGS_POST_EMPTY = {
    "url": "https://test.com/api",
    "headers": {"Authorization": "Auth"},
    "params": {"filter": "test"},
}
CLIENT_CALL_ARGS_POST = {
    "url": "https://test.com/api",
    "headers": {"Authorization": "Auth"},
    "params": {"filter": "test"},
    "json": {'a': 'b'},
    "content": "None"
}


@pytest.mark.packaging
def test_version_in_sync():
    pyproject_toml = pathlib.Path(__file__).resolve().parents[3] / "pyproject.toml"
    toml_version = None
    with open(pyproject_toml, encoding='utf-8') as file:
        toml_version = toml.load(file)["tool"]["poetry"]["version"]
    init_version = __version__
    assert toml_version
    assert init_version
    assert toml_version == init_version


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_basic_get(mocked_integration_client):
    # Given an external client
    integration_client, last_mock_call = mocked_integration_client

    # When calling an httpx method
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)

    # Then the underlying mock get method is called with the correct args
    assert last_mock_call["method"] == "GET"
    assert last_mock_call["kwargs"]["url"] == CLIENT_CALL_ARGS_GET["url"]
    assert last_mock_call["kwargs"]["params"] == CLIENT_CALL_ARGS_GET["params"]
    assert last_mock_call["kwargs"]["headers"] == CLIENT_CALL_ARGS_GET["headers"]
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_basic_post(mocked_integration_client):
    # Given an external client
    integration_client, last_mock_call = mocked_integration_client

    # When calling an httpx method with some content
    response = await integration_client.post(**CLIENT_CALL_ARGS_POST, context=CONTEXT)

    # Then the underlying mock get method is called with the correct args
    assert last_mock_call["method"] == "POST"
    assert last_mock_call["kwargs"]["url"] == CLIENT_CALL_ARGS_POST["url"]
    assert last_mock_call["kwargs"]["params"] == CLIENT_CALL_ARGS_POST["params"]
    assert last_mock_call["kwargs"]["headers"] == CLIENT_CALL_ARGS_POST["headers"]
    assert last_mock_call["kwargs"]["json"] == CLIENT_CALL_ARGS_POST["json"]
    assert response.content == CLIENT_CALL_ARGS_POST["json"]

    # When calling an httpx method with empty content
    response = await integration_client.post(**CLIENT_CALL_ARGS_POST_EMPTY, context=CONTEXT)
    # Then the underlying mock get method is called with the correct args
    assert last_mock_call["method"] == "POST"
    assert last_mock_call["kwargs"]["url"] == CLIENT_CALL_ARGS_POST["url"]
    assert last_mock_call["kwargs"]["params"] == CLIENT_CALL_ARGS_POST["params"]
    assert last_mock_call["kwargs"]["headers"] == CLIENT_CALL_ARGS_POST["headers"]
    assert response.content == b'{"json": true}'
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_rate_limiting(mocked_integration_client):
    # Given an external client where the max calls per second is one
    integration_client, _ = mocked_integration_client
    # When call the api multiple times
    start = time.time()
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    end_first = time.time()
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    end_second = time.time()
    # Then the first call is almost instant, and the second call waits a second
    dur_first = end_first - start
    assert dur_first < 0.01, "First call should be close to instant"
    dur_second = end_second - end_first
    assert dur_second > 0.1, "Second call should wait tenth a second to respect throttle"
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_rate_limiting_order(minimal_integration_client):
    # Given an external client
    integration_client, _ = minimal_integration_client
    tasks = []
    uuid_ = uuid.uuid4()
    mock_request = MagicMock()
    mock_request.headers = {}
    for i in range(0, 10):
        tasks.append(asyncio.create_task(integration_client.get(**dict(CLIENT_CALL_ARGS_GET, **{"id": i, "uuid": uuid_}), context=MaltegoContext(
            MaltegoGraph(), mock_request, api_key=str(i)
        ))))

    for task in tasks:
        res = await task
        assert res.json().get("call_num") == res.json().get("request_id")
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_rate_limiting_order_fairness(minimal_integration_client):
    integration_client, _ = minimal_integration_client
    tasks = []
    counter = 0
    uuid_ = uuid.uuid4()
    mock_request = MagicMock()
    mock_request.headers = {}
    for i in range(0, 10):
        if i > 0 and i % 2 == 0:
            counter += 1
        print(f"{counter=}")
        tasks.append(
            asyncio.create_task(
                integration_client.get(
                    **dict(CLIENT_CALL_ARGS_GET, **{"id": counter, "uuid": uuid_}),
                    context=MaltegoContext(MaltegoGraph(), mock_request, api_key=str(counter))
                )
            )
        )

    di = {}
    for i, task in enumerate(tasks):
        res = await task
        request_id = res.json().get("request_id")
        call_num = res.json().get("call_num")
        if request_id not in di:
            di[request_id] = [call_num]
        else:
            di[request_id].append(call_num)

    for i, res in di.items():
        assert res[0] == i
        assert res[1] == (i + 5)

    # When calling an httpx method

    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_non_200_response(monkeypatch, snapshot):
    client = IntegrationClient(
        max_calls_per_period=1,
        period_length_seconds=60
    )

    last_mock_call = {}

    async def mock_request(method, **kwargs) -> Response:
        last_mock_call["method"] = method
        last_mock_call["kwargs"] = kwargs
        return Response(status_code=429,
                        content=b'{"error": {"type":"rate_limit_exceeded", "message":"rate limit, wait 20 minutes"}}')

    monkeypatch.setattr(client.httpx_client, "request", mock_request)
    with pytest.raises(MaltegoException):
        try:
            await client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
        except MaltegoException as maltego_exception:
            assert isinstance(maltego_exception, MaltegoException)
            assert maltego_exception.response
            assert maltego_exception.response.status_code == 429
            assert snapshot == maltego_exception.response.json()
            assert maltego_exception.response.json().get(
                'error').get('type') == 'rate_limit_exceeded'
            raise MaltegoException
    assert client.rate_throttler._leak_task is not None
    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_429_response_maps_to_data_provider_unavailable(monkeypatch):
    """Regression: 429 used to fall through to a bare, untyped MaltegoException
    via the generic else branch, indistinguishable from any other unhandled
    4xx. It now gets its own explicit mapping to a typed exception so
    connectors can react to rate-limiting specifically."""
    from maltego.model.exception import MaltegoHTTPDataProviderUnavailable

    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)

    async def mock_request(method, **kwargs) -> Response:
        return Response(status_code=429, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_request)
    with pytest.raises(MaltegoHTTPDataProviderUnavailable) as exc_info:
        await client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    assert exc_info.value.response.status_code == 429
    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_unhandled_4xx_maps_to_data_provider_invalid_response(monkeypatch):
    """Regression: any 4xx not covered by a specific branch (401/403/404/429)
    used to raise a bare, untyped MaltegoException. It now raises the typed
    MaltegoHTTPDataProviderInvalidResponse so connectors can distinguish
    "upstream rejected this request" from "SDK-internal transport failure"
    instead of catching the same untyped exception for both."""
    from maltego.model.exception import MaltegoHTTPDataProviderInvalidResponse

    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)

    async def mock_request(method, **kwargs) -> Response:
        return Response(status_code=418, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_request)
    with pytest.raises(MaltegoHTTPDataProviderInvalidResponse) as exc_info:
        await client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    assert exc_info.value.response.status_code == 418
    client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_request_method(mocked_integration_client):
    integration_client, last_mock_call = mocked_integration_client
    await integration_client.request("GET", **CLIENT_CALL_ARGS_GET, context=CONTEXT)
    assert last_mock_call["method"] == "GET"
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_integration_client_aclose_is_idempotent(monkeypatch):
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)
    closed_calls = []
    original_aclose = client.httpx_client.aclose

    async def spy_aclose():
        closed_calls.append(True)
        return await original_aclose()

    monkeypatch.setattr(client.httpx_client, "aclose", spy_aclose)

    await client.aclose()
    await client.aclose()  # second call must be a no-op

    assert len(closed_calls) == 1


@pytest.mark.asyncio
async def test_integration_client_aclose_cancels_leak_task(monkeypatch):
    """aclose() must cleanly cancel the rate throttler background task without raising."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)

    async def mock_request(method, **kwargs):
        return httpx.Response(status_code=200, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_request)

    # Make a request so _leak_task is created
    await client.get(url="https://test.com/api", context=CONTEXT)
    assert client.rate_throttler._leak_task is not None

    # aclose() must not raise even though _leak_task is pending
    await client.aclose()

    assert client._closed
    assert client.rate_throttler._leak_task is None


@pytest.mark.asyncio
async def test_integration_client_async_context_manager(monkeypatch):
    async def mock_request(method, **kwargs):
        return httpx.Response(status_code=200, content=b"{}")

    async with IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0) as client:
        monkeypatch.setattr(client.httpx_client, "request", mock_request)
        await client.get(url="https://test.com/api", context=CONTEXT)
        assert not client._closed

    assert client._closed


@pytest.mark.asyncio
async def test_integration_client_reset_preserves_proxy_settings(monkeypatch):
    """_reset_client must rebuild httpx client with the original proxies and trust_env."""
    built_kwargs: list = []
    original_build = IntegrationClient._build_httpx_client

    def spy_build(self, proxies=None, trust_env=True):
        built_kwargs.append({"proxies": proxies, "trust_env": trust_env})
        return original_build(self, proxies=proxies, trust_env=trust_env)

    monkeypatch.setattr(IntegrationClient, "_build_httpx_client", spy_build)

    proxy_val = {"http://": "http://proxy.example.com:8080"}
    client = IntegrationClient(proxies=proxy_val, trust_env=False)

    assert built_kwargs[0]["proxies"] == proxy_val
    assert built_kwargs[0]["trust_env"] is False

    # Trigger a reset
    with pytest.raises(Exception):
        await client._reset_client()

    assert built_kwargs[1]["proxies"] == proxy_val
    assert built_kwargs[1]["trust_env"] is False


@pytest.mark.asyncio
async def test_integration_client_transport_errors_reach_call_httpx_method(monkeypatch):
    """ConnectError/ReadTimeout/TimeoutException/RemoteProtocolError must not be swallowed
    by _client_call_retrying_if_reset — they should reach _call_httpx_method's handler."""
    from maltego.model.exception import MaltegoHTTPDataProviderUnavailable

    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)

    async def raise_connect_error(method, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(client.httpx_client, "request", raise_connect_error)

    with pytest.raises(MaltegoHTTPDataProviderUnavailable):
        await client.get(url="https://test.com/api", context=CONTEXT)


@pytest.mark.asyncio
async def test_integration_client_aclose_on_fresh_client_does_not_raise():
    """aclose() on a client that has never made a request must not raise."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)
    await client.aclose()
    assert client._closed
    assert client.rate_throttler._leak_task is None


@pytest.mark.asyncio
async def test_integration_client_request_after_aclose_raises_without_leaking_coroutine(monkeypatch):
    """get()/post() after aclose() must raise MaltegoException, not a cryptic httpx error."""
    from maltego.model.exception import MaltegoException

    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)
    await client.aclose()

    def fail_if_http_coroutine_is_created(*args, **kwargs):
        pytest.fail("closed clients must reject before creating the HTTP request coroutine")

    monkeypatch.setattr(client, "_call_httpx_method", fail_if_http_coroutine_is_created)

    with pytest.raises(MaltegoException) as exc_info:
        await client.get(url="https://test.com/api", context=CONTEXT)
    assert "closed" in exc_info.value.message.lower()


@pytest.mark.security
def test_build_httpx_client_disables_follow_redirects():
    """C3 — the underlying httpx.AsyncClient must never auto-follow redirects.

    Silently following a redirect could retarget an outbound request (with the
    original destination's headers/credentials) at an unintended internal/external
    host (SSRF via redirect). This must be an explicit SDK-level guarantee, not an
    incidental default inherited from httpx.
    """
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)
    assert client.httpx_client.follow_redirects is False


@pytest.mark.asyncio
async def test_throttler_semaphore_cleaned_up_after_idle(mocked_integration_client):
    """Semaphores are removed from semaphores_by_owner once all in-flight requests finish."""
    integration_client, _ = mocked_integration_client
    throttler = integration_client.connection_throttler

    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)

    # After the request completes the owner's semaphore and in-flight counter are cleared
    owner = integration_client.get_identifier(CONTEXT, None)
    assert owner not in throttler.semaphores_by_owner
    assert owner not in throttler._in_flight_by_owner

    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_put(mocked_integration_client):
    integration_client, last_mock_call = mocked_integration_client
    await integration_client.put(
        url="https://test.com/api",
        context=CONTEXT,
        json={"name": "updated"},
        headers={"Authorization": "Auth"},
    )
    assert last_mock_call["method"] == "PUT"
    assert last_mock_call["kwargs"]["url"] == "https://test.com/api"
    assert last_mock_call["kwargs"]["json"] == {"name": "updated"}
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_patch(mocked_integration_client):
    integration_client, last_mock_call = mocked_integration_client
    await integration_client.patch(
        url="https://test.com/api",
        context=CONTEXT,
        json={"name": "patched"},
    )
    assert last_mock_call["method"] == "PATCH"
    assert last_mock_call["kwargs"]["json"] == {"name": "patched"}
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_delete(mocked_integration_client):
    integration_client, last_mock_call = mocked_integration_client
    await integration_client.delete(url="https://test.com/api", context=CONTEXT)
    assert last_mock_call["method"] == "DELETE"
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_head(mocked_integration_client):
    integration_client, last_mock_call = mocked_integration_client
    await integration_client.head(url="https://test.com/api", context=CONTEXT)
    assert last_mock_call["method"] == "HEAD"
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_new_methods_dispatch_correct_verb(mocked_integration_client):
    """Verify put/patch/delete/head each dispatch the correct HTTP method string."""
    integration_client, last_mock_call = mocked_integration_client
    for method, fn in [
        ("PUT", integration_client.put),
        ("PATCH", integration_client.patch),
        ("DELETE", integration_client.delete),
        ("HEAD", integration_client.head),
    ]:
        await fn(url="https://test.com/api", context=CONTEXT)
        assert last_mock_call["method"] == method
    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_run_throttled_called_for_new_methods(monkeypatch):
    """Verify new HTTP methods invoke run_throttled, not a bypass path."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)
    throttled_calls = []
    original_run_throttled = client.run_throttled

    async def spy_run_throttled(awaitable, context, client_identifier=None):
        throttled_calls.append(True)
        return await original_run_throttled(awaitable, context, client_identifier=client_identifier)

    async def mock_request(method, **kwargs):
        return httpx.Response(status_code=200, content=b"{}")

    monkeypatch.setattr(client, "run_throttled", spy_run_throttled)
    monkeypatch.setattr(client.httpx_client, "request", mock_request)

    await client.put(url="https://test.com/api", context=CONTEXT)
    await client.patch(url="https://test.com/api", context=CONTEXT)
    await client.delete(url="https://test.com/api", context=CONTEXT)
    await client.head(url="https://test.com/api", context=CONTEXT)
    await client.request("GET", url="https://test.com/api", context=CONTEXT)

    assert len(throttled_calls) == 5
    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_throttler_override_concurrency_respected(mocked_integration_client):
    """override_concurrency_limit_for creates a new semaphore with the overridden limit."""
    integration_client, _ = mocked_integration_client
    throttler = integration_client.connection_throttler

    integration_client.override_concurrency_limit_for(context=CONTEXT, new_limit=3)
    owner = integration_client.get_identifier(CONTEXT, None)

    # The override is stored in user_concurrency_overrides
    assert throttler.user_concurrency_overrides[owner] == 3

    # After a request the new semaphore was created with the overridden value (3)
    await integration_client.get(**CLIENT_CALL_ARGS_GET, context=CONTEXT)
    # Once idle the semaphore is cleaned up
    assert owner not in throttler.semaphores_by_owner

    integration_client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_throttler_no_premature_cleanup_during_concurrent_same_owner(monkeypatch):
    """Semaphore for an owner must not be deleted while another same-owner request is in flight."""
    client = IntegrationClient(
        max_concurrent=10,
        max_concurrent_per_key=5,
        max_calls_per_period=100,
        period_length_seconds=1.0,
    )
    throttler = client.connection_throttler
    owner = client.get_identifier(CONTEXT, None)

    barrier = asyncio.Event()
    first_started = asyncio.Event()

    async def slow_request(method, **kwargs):
        first_started.set()
        await barrier.wait()
        return httpx.Response(status_code=200, content=b"{}")

    async def fast_request(method, **kwargs):
        return httpx.Response(status_code=200, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", slow_request)
    t1 = asyncio.create_task(client.get(url="https://test.com", context=CONTEXT))
    await first_started.wait()

    # While the first request is in flight the owner semaphore must still be present
    assert owner in throttler.semaphores_by_owner
    assert throttler._in_flight_by_owner.get(owner, 0) >= 1

    monkeypatch.setattr(client.httpx_client, "request", fast_request)
    t2 = asyncio.create_task(client.get(url="https://test.com", context=CONTEXT))

    barrier.set()
    await asyncio.gather(t1, t2)

    # Only after both finish the semaphore should be cleaned up
    assert owner not in throttler.semaphores_by_owner
    assert owner not in throttler._in_flight_by_owner
    client.rate_throttler._leak_task.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_client_request_error_mapping(monkeypatch):
    """Verify request() routes through _call_httpx_method so error mapping applies."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=1.0)

    async def mock_request(method, **kwargs):
        return httpx.Response(status_code=401, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_request)
    from maltego.model.exception import MaltegoHTTPDataProviderAPIKeyInvalid
    with pytest.raises(MaltegoHTTPDataProviderAPIKeyInvalid):
        await client.request("PUT", url="https://test.com/api", context=CONTEXT)
    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_throttler_in_flight_counter_cleaned_up_on_exception(monkeypatch):
    """_in_flight_by_owner must be decremented and semaphore removed even when the awaitable raises."""
    from maltego.model.exception import MaltegoHTTPDataProviderUnavailable

    client = IntegrationClient(
        max_concurrent=10,
        max_concurrent_per_key=5,
        max_calls_per_period=100,
        period_length_seconds=1.0,
    )
    throttler = client.connection_throttler
    owner = client.get_identifier(CONTEXT, None)

    async def failing_request(method, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(client.httpx_client, "request", failing_request)

    with pytest.raises(MaltegoHTTPDataProviderUnavailable):
        await client.get(url="https://test.com", context=CONTEXT)

    assert owner not in throttler._in_flight_by_owner
    assert owner not in throttler.semaphores_by_owner
    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_aclose_unblocks_rate_throttled_coroutines(monkeypatch):
    """aclose() must unblock coroutines blocked on the rate-throttler semaphore.

    Scenario: semaphore is exhausted (1 slot, 1 request in-flight), a second
    request blocks at acquire(). aclose() must drain the semaphore so the
    blocked coroutine can proceed rather than hanging forever when _leak_task
    is cancelled.
    """
    from contextlib import suppress as ctx_suppress

    client = IntegrationClient(
        max_calls_per_period=1,       # only 1 call allowed per period
        period_length_seconds=60.0,   # very long period — _leak_task won't fire
    )

    mock_req = MagicMock()
    mock_req.headers = {}
    first_context = MaltegoContext(MaltegoGraph(), mock_req)

    async def mock_request(method, **kwargs):
        return httpx.Response(status_code=200, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_request)

    # Consume the single rate-throttler slot; _leak_task is now sleeping for 60 s
    await client.get(url="https://test.com/api", context=first_context)
    assert client.rate_throttler._leak_task is not None
    # The semaphore is now exhausted (value=0)
    assert client.rate_throttler._sem is not None

    # Queue a second request that will block on the exhausted semaphore
    second_done = asyncio.Event()

    async def second_request():
        try:
            await client.get(url="https://test.com/api", context=first_context)
        except Exception:  # noqa: BLE001
            pass
        finally:
            second_done.set()

    task = asyncio.create_task(second_request())
    # Yield once so the task can start and block at the semaphore
    await asyncio.sleep(0)

    # aclose() must drain the semaphore and unblock the waiting coroutine.
    # Without the drain, cancelling _leak_task would cause the blocked coroutine
    # to wait forever since nothing else would ever release the semaphore.
    await client.aclose()

    # The second request must complete (in any state) within a short timeout.
    # If aclose() doesn't drain the semaphore, this would hang.
    try:
        await asyncio.wait_for(second_done.wait(), timeout=2.0)
    finally:
        task.cancel()
        with ctx_suppress(Exception):
            await task

    assert client._closed
    assert second_done.is_set(), "Blocked coroutine hung after aclose() — semaphore was not drained"
