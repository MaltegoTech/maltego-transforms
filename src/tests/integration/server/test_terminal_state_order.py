"""A run's state is set once, after its after-transform middlewares, with the response headers they set.

`DELETE .../run/<id>` answers those headers. The runner used to set FINISHED when the transform ended, before the
middlewares ran; a client that stopped polling at FINISHED could delete the run without them.
"""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from maltego.model.context import MaltegoContext
from maltego.model.entity import MEF, MaltegoEntity, MaltegoEntityConfig
from maltego.model.exception import MaltegoHTTPDataProviderUnavailable
from maltego.runner.transform_execution_context import ExecutionState
from maltego.runner.transform_result_set import TransformResultSet
from maltego.server import MaltegoServerSettings, MaltegoTransformServer, TransformMiddleware

pytestmark = pytest.mark.integration

NS = "stateorder"
HEADER = "X-Run-Total"
# FINISHED included: it must never be set, it used to be set before the after-transform middlewares ran
TERMINAL = (ExecutionState.FINISHED, ExecutionState.FAILED, ExecutionState.TIMED_OUT, ExecutionState.CANCELED,
            ExecutionState.COMPLETED)


class Word(MaltegoEntity):
    TYPE_NAME = "stateorder.Word"
    Config = MaltegoEntityConfig(value_property="text", display_name="Word", category="Test")
    text: str = MEF(name="text", display_name="Text", matching_rule="loose")


class Scenarios(TransformMiddleware):
    """An after-transform hook that answers a response header, also on failed runs, plus the paths a run can end on: a
    before-transform refusal and an after-transform middleware that raises."""
    call_on_failure = True

    async def before_transform(self, transform, transform_input, properties, context, soft_limit, hard_limit):
        if transform.name.endswith("refuse"):
            raise MaltegoHTTPDataProviderUnavailable("Acme is down (503).")

    async def after_transform(self, transform, transform_input, output_entities, context, state, exceptions=None):
        if transform.name.endswith("after_raises"):
            raise RuntimeError("a middleware bug")
        context.response_headers[HEADER] = "5"


@pytest.fixture(scope="module")
def client():
    settings = MaltegoServerSettings(server_name=NS, ns=NS, author=NS, require_api_key=False)
    server = MaltegoTransformServer(settings=settings)

    @server.register_transform(display_name="down", name="down", description="the provider is down")
    async def down(input_entity: Word) -> Word:
        raise MaltegoHTTPDataProviderUnavailable("Acme is down (503).")

    @server.register_transform(display_name="broken", name="broken", description="a bug in the transform")
    async def broken(input_entity: Word) -> Word:
        raise RuntimeError("bug")

    @server.register_transform(display_name="ok", name="ok", description="a plain successful run")
    async def ok(input_entity: Word, settings: dict, limit: int, context: MaltegoContext) -> list[Word]:
        return [Word("x")]

    @server.register_transform(display_name="refuse", name="refuse",
                               description="a middleware refuses before the transform")
    async def refuse(input_entity: Word) -> Word:
        return Word(text="never")

    @server.register_transform(display_name="after_raises", name="after_raises",
                               description="an after-transform middleware raises")
    async def after_raises(input_entity: Word) -> Word:
        return Word("x")

    server.register_entity(Word)
    server.setup(settings)
    server.add_middleware(Scenarios())
    server.runner.startup()
    with TestClient(server.app) as c:
        yield c
    server.runner.shutdown()


def start(client: TestClient, name: str = "down", ns: str = NS):
    entity = {"id": "n1", "type": f"{ns}.Word", "valueRef": "text",
              "properties": [{"name": "text", "displayName": "text", "type": "STRING", "value": "x", "matchingRule": "loose"}]}
    body = {"input": {"metadata": {"entitiesTypesStat": {f"{ns}.Word": 1}, "entitiesTotalCount": 1,
                                   "linksTotalCount": 0, "rootEntitiesCount": 0},
                      "graph": {"entities": [entity], "links": []}},
            "limit": 12, "transformSettings": []}
    started = client.post(f"/api/v3/transforms/{ns}.{name}/run", json=body)
    assert started.status_code == 201
    return f"/api/v3/transforms/{ns}.{name}/run/{started.json()['result']['runId']}"


def wait_terminal(client: TestClient, url: str, pause: float) -> None:
    for _ in range(5000):
        if client.get(f"{url}/results").json()["result"]["state"] in ("FAILED", "TIMED_OUT", "CANCELED", "COMPLETED"):
            return
        time.sleep(pause)
    pytest.fail(f"{url} never reached a terminal state")


# run -> the header the run ends with (after every middleware ran); None = no header
FINAL = {"down": "5", "broken": "5", "ok": "5", "refuse": "5", "after_raises": None}


@pytest.mark.parametrize("name", sorted(FINAL))
def test_the_headers_are_final_when_the_terminal_state_is_published(client, monkeypatch, name):
    """Deterministic: the header the run answers at the moment its terminal state is set is the one it ends with, and the
    state is set once."""
    seen = []
    state = TransformResultSet.state

    def set_state(self, value):
        if value in TERMINAL:
            seen.append((value.value, self.context.response_headers.get(HEADER)))
        state.fset(self, value)

    monkeypatch.setattr(TransformResultSet, "state", property(state.fget, set_state))
    url = start(client, name)
    wait_terminal(client, url, 0.001)
    final = client.delete(url).headers.get(HEADER)
    assert final == FINAL[name]
    assert [value for _, value in seen] == [final], f"terminal state(s) published as {seen}, the run ends with {final!r}"


NS2 = "stateorder2"


class Word2(MaltegoEntity):
    TYPE_NAME = "stateorder2.Word"
    Config = MaltegoEntityConfig(value_property="text", display_name="Word", category="Test")
    text: str = MEF(name="text", display_name="Text", matching_rule="loose")


@pytest.fixture(scope="module")
def slow_client():
    """A server whose transform execution timeout is 1 s and whose only transform never ends by itself."""
    settings = MaltegoServerSettings(server_name=NS2, ns=NS2, author=NS2, require_api_key=False, transform_execution_timeout=1)
    server = MaltegoTransformServer(settings=settings)

    @server.register_transform(display_name="sleepy", name="sleepy", description="never ends by itself")
    async def sleepy(input_entity: Word2) -> Word2:  # never returns
        while True:  # short sleeps: a cancel from the endpoint's thread takes effect when the runner's loop next wakes
            await asyncio.sleep(0.02)

    server.register_entity(Word2)
    server.setup(settings)
    server.add_middleware(Scenarios())
    server.runner.startup()
    with TestClient(server.app) as c:
        yield c
    server.runner.shutdown()


@pytest.mark.parametrize("how", ["timeout", "cancel"])
def test_the_headers_are_final_when_a_timed_out_or_canceled_run_is_published(slow_client, monkeypatch, how):
    """TIMED_OUT (the transform runs past `transform_execution_timeout`) and CANCELED (`POST .../cancel`): the after-transform
    middleware's header is there when the state is set, and the state is set once."""
    seen = []
    state = TransformResultSet.state

    def set_state(self, value):
        if value in TERMINAL:
            seen.append((value.value, self.context.response_headers.get(HEADER)))
        state.fset(self, value)

    monkeypatch.setattr(TransformResultSet, "state", property(state.fget, set_state))
    url = start(slow_client, "sleepy", NS2)
    if how == "cancel":
        time.sleep(0.3)  # let the transform start: a cancel before that has nothing to cancel
        assert slow_client.post(f"{url}/cancel").status_code == 200
    for _ in range(5000):
        got = slow_client.get(f"{url}/results").json()["result"]["state"]
        if got in ("FAILED", "TIMED_OUT", "CANCELED", "COMPLETED"):
            break
        time.sleep(0.005)
    else:
        pytest.fail("never reached a terminal state")
    final = slow_client.delete(url).headers.get(HEADER)
    assert final == "5"
    assert [value for _, value in seen] == [final], f"terminal state(s) published as {seen}, the run ends with {final!r}"
    assert seen[0][0] == {"timeout": "TIMED_OUT", "cancel": "CANCELED"}[how]
