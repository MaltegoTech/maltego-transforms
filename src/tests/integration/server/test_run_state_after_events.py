"""A terminal result is a reliable signal that all SDK-managed output is available."""
import asyncio
import datetime
import threading
import time

import pytest
from fastapi.testclient import TestClient

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.context import MaltegoContext
from maltego.model.entity import MEF, MaltegoEntity, MaltegoEntityConfig
from maltego.model.exception import MaltegoException, MaltegoWarning
from maltego.model.server import TransformRunnerType
from maltego.runner.transform_execution_context import ExecutionState
from maltego.runner.transform_result_set import TransformResultSet
from maltego.server import MaltegoServerSettings, MaltegoTransformServer

pytestmark = pytest.mark.integration
NS = "failorder"
DEADLINE = 10
TERMINAL = {"COMPLETED", "FAILED", "CANCELED"}


class Word(MaltegoEntity):
    TYPE_NAME = "failorder.Word"
    Config = MaltegoEntityConfig(value_property="text", display_name="Word", category="Test")
    text: str = MEF(name="text", display_name="Text", matching_rule="loose")


async def wait_gate(gate):
    deadline = time.monotonic() + DEADLINE
    while not gate.is_set():
        if time.monotonic() >= deadline:
            raise TimeoutError("test gate was not released")
        await asyncio.sleep(0.01)


class Gates:
    def __init__(self):
        self.phase = None
        self.phase_entered = threading.Event()
        self.phase_release = threading.Event()
        self.cleanup_entered = threading.Event()
        self.transform_release = threading.Event()
        self.cleanup_release = threading.Event()
        self.hold_cleanup = False
        self.slow_cleanup_only = False
        self.fail_after = False

    def release_all(self):
        self.phase_release.set()
        self.cleanup_release.set()
        self.transform_release.set()


class PhaseMiddleware(TransformMiddleware):
    def __init__(self, gates):
        self.gates = gates

    async def before_transform(self, transform, transform_input, properties, context, soft_limit, hard_limit):
        if self.gates.phase == "before":
            self.gates.phase_entered.set()
            await wait_gate(self.gates.phase_release)

    async def after_transform(self, transform, transform_input, output_entities, context, state, exceptions=None):
        if self.gates.phase == "after":
            self.gates.phase_entered.set()
            await wait_gate(self.gates.phase_release)
        if self.gates.fail_after:
            raise MaltegoException("after hook failed", code=500)


class CleanupMiddleware(TransformMiddleware):
    def __init__(self, gates):
        self.gates = gates

    async def before_transform(self, transform, transform_input, properties, context, soft_limit, hard_limit):
        pass

    async def after_transform(self, transform, transform_input, output_entities, context, state, exceptions=None):
        if not self.gates.hold_cleanup:
            return
        if self.gates.slow_cleanup_only and transform_input.value != "slow":
            return
        context.log.inform("cleanup started")
        self.gates.cleanup_entered.set()
        await wait_gate(self.gates.cleanup_release)
        context.log.inform("cleanup finished")


@pytest.fixture(params=[TransformRunnerType.ASYNC, TransformRunnerType.THREADED], ids=["async", "threaded"])
def server_client(request):
    gates = Gates()
    settings = MaltegoServerSettings(
        server_name=NS, ns=NS, author=NS, require_api_key=False,
        transform_runner=request.param, transform_execution_timeout=30, middleware_execution_timeout=30,
    )
    server = MaltegoTransformServer(settings=settings)
    server.runner.middlewares.extend([PhaseMiddleware(gates), CleanupMiddleware(gates)])

    @server.register_transform(display_name="warns", name="warns", description="raises a user warning")
    async def warns(input_entity: Word) -> Word:
        raise MaltegoWarning("Please provide a valid value.")

    @server.register_transform(display_name="breaks", name="breaks", description="raises a transform exception")
    async def breaks(input_entity: Word) -> Word:
        raise MaltegoException("The upstream said no.", code=502)

    @server.register_transform(display_name="waits", name="waits", description="waits for a test gate")
    async def waits(input_entity: Word, context: MaltegoContext) -> list[Word]:
        context.log.inform("transform started")
        if gates.phase in (None, "transform"):
            gates.phase_entered.set()
        await wait_gate(gates.transform_release)
        return []

    @server.register_transform(display_name="mixed", name="mixed", description="one failing and one successful input")
    async def mixed(input_entity: Word, context: MaltegoContext) -> list[Word]:
        if input_entity.value == "fail":
            raise MaltegoException("one child failed", code=502)
        context.log.inform("successful child")
        return []

    server.register_entity(Word)
    server.setup(settings)
    server.runner.startup()
    try:
        with TestClient(server.app) as client:
            try:
                yield server, client, gates
            finally:
                gates.release_all()
    finally:
        server.runner.shutdown()


def post(client, name, values=("x",)):
    entities = [
        {"id": f"n{i}", "type": Word.TYPE_NAME, "valueRef": "text", "properties": [
            {"name": "text", "displayName": "text", "type": "STRING", "value": value, "matchingRule": "loose"}
        ]}
        for i, value in enumerate(values)
    ]
    count = len(entities)
    body = {"input": {"metadata": {"entitiesTypesStat": {Word.TYPE_NAME: count}, "entitiesTotalCount": count,
                                   "linksTotalCount": 0, "rootEntitiesCount": 0},
                      "graph": {"entities": entities, "links": []}},
            "limit": 12, "transformSettings": []}
    started = client.post(f"/api/v3/transforms/{NS}.{name}/run", json=body)
    assert started.status_code == 201, started.text
    return f"/api/v3/transforms/{NS}.{name}/run/{started.json()['result']['runId']}"


def get(client, run, **params):
    response = client.get(f"{run}/results", params=params)
    assert response.status_code == 200, response.text
    return response


def wait_for(client, run, predicate):
    deadline = time.monotonic() + DEADLINE
    while time.monotonic() < deadline:
        response = get(client, run)
        if predicate(response.json()["result"]):
            return response
        time.sleep(0.01)
    pytest.fail(f"run {run} did not reach the expected condition before the deadline")


def terminal(client, run):
    return wait_for(client, run, lambda result: result["state"] in TERMINAL)


def texts(result):
    return [event["data"]["statusMessage"]["text"] for event in result["events"]
            if event["data"]["inputType"] == "STATUS_MESSAGE"]


def assert_active(response):
    assert response.json()["result"]["state"] in {"INITIALIZED", "RUNNING"}
    assert response.headers["maltego-run-state"] in {"INITIALIZED", "RUNNING"}


def cancel(client, run):
    response = client.post(f"{run}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "CANCELED"


def page_messages(client, run, count):
    messages = []
    for pointer in range(count):
        page = get(client, run, eventPointer=pointer, eventLimit=1).json()["result"]
        assert page["eventPointer"] == pointer
        assert page["eventCount"] == count
        assert len(page["events"]) == 1
        messages.extend(texts(page))
    assert not get(client, run, eventPointer=count, eventLimit=1).json()["result"]["events"]
    return messages


@pytest.mark.parametrize("name,message", [("warns", "Please provide a valid value."), ("breaks", "The upstream said no.")])
def test_failure_message_visible_while_cleanup_is_held(server_client, name, message):
    _, client, gates = server_client
    gates.hold_cleanup = True
    run = post(client, name)
    try:
        assert gates.cleanup_entered.wait(DEADLINE)
        response = get(client, run)
        assert_active(response)
        assert message in texts(response.json()["result"])
        gates.cleanup_release.set()
        response = terminal(client, run)
        assert response.json()["result"]["state"] == "FAILED"
        assert message in texts(response.json()["result"])
        assert "cleanup finished" in texts(response.json()["result"])
    finally:
        gates.release_all()

def test_after_hook_failure_message_precedes_final_cleanup(server_client):
    _, client, gates = server_client
    gates.fail_after = True
    gates.hold_cleanup = True
    gates.transform_release.set()
    run = post(client, "waits")
    try:
        assert gates.cleanup_entered.wait(DEADLINE)
        response = get(client, run)
        assert_active(response)
        assert "after hook failed" in texts(response.json()["result"])
        gates.cleanup_release.set()
        result = terminal(client, run).json()["result"]
        assert result["state"] == "FAILED"
        assert "after hook failed" in texts(result)
        assert "cleanup finished" in texts(result)
    finally:
        gates.release_all()



@pytest.mark.slow
@pytest.mark.parametrize("name,message", [("warns", "Please provide a valid value."), ("breaks", "The upstream said no.")])
def test_fast_failure_always_returns_its_message(server_client, name, message):
    _, client, _ = server_client
    for _ in range(200):
        run = post(client, name)
        try:
            response = terminal(client, run)
            result = response.json()["result"]
            assert result["state"] == "FAILED"
            assert texts(result) == [message]
            assert result["eventCount"] == 1
        finally:
            client.delete(run)


def test_terminal_snapshot_is_taken_before_reading_events(server_client, monkeypatch):
    _, client, gates = server_client
    run = post(client, "waits")
    try:
        assert gates.phase_entered.wait(DEADLINE)
        wait_for(client, run, lambda result: result["state"] == "RUNNING")
        count = TransformResultSet.event_count
        injected = []

        def count_then_end(result):
            value = count.fget(result)
            if result.state is ExecutionState.RUNNING and not injected:
                injected.append(True)
                result.push_exception(MaltegoException("a late event", code=500))
                result.state = ExecutionState.COMPLETED
            return value

        monkeypatch.setattr(TransformResultSet, "event_count", property(count_then_end))
        response = get(client, run)
        assert injected
        assert response.headers["maltego-run-state"] == "RUNNING"
        assert response.json()["result"]["state"] == "RUNNING"
        monkeypatch.undo()
        result = get(client, run).json()["result"]
        assert result["state"] == "COMPLETED"
        assert result["eventCount"] == len(result["events"]) == 2
        assert texts(result) == ["transform started", "a late event"]
    finally:
        gates.release_all()


def test_execution_timeout_waits_for_cleanup_and_maps_to_failed(server_client):
    server, client, gates = server_client
    server.runner.transform_execution_timeout = 1
    gates.hold_cleanup = True
    run = post(client, "waits")
    try:
        assert gates.phase_entered.wait(DEADLINE)
        assert gates.cleanup_entered.wait(DEADLINE)
        response = get(client, run)
        assert_active(response)
        assert any("Timeout after 1s" in text for text in texts(response.json()["result"]))
        gates.cleanup_release.set()
        response = terminal(client, run)
        assert response.headers["maltego-run-state"] == "TIMED_OUT"
        assert response.json()["result"]["state"] == "FAILED"
        assert "cleanup finished" in texts(response.json()["result"])
    finally:
        gates.release_all()


def test_inactivity_expiry_waits_for_cleanup_and_cannot_become_success(server_client):
    server, client, gates = server_client
    gates.hold_cleanup = True
    run = post(client, "waits")
    try:
        assert gates.phase_entered.wait(DEADLINE)
        result = server.runner.result(run.rsplit("/", 1)[1])
        old = result.update_time - datetime.timedelta(seconds=server.runner.retention_time + 1)
        result.update_time = old
        result.last_fetch_time = old
        server.runner.cleanup()
        assert gates.cleanup_entered.wait(DEADLINE)
        assert_active(get(client, run))
        gates.cleanup_release.set()
        response = terminal(client, run)
        assert response.headers["maltego-run-state"] == "TIMED_OUT"
        assert response.json()["result"]["state"] == "FAILED"
        assert "cleanup finished" in texts(response.json()["result"])
        assert get(client, run).json()["result"]["state"] == "FAILED"
    finally:
        gates.release_all()


@pytest.mark.parametrize("phase", ["before", "transform", "after"])
def test_cancel_acknowledges_immediately_but_result_waits_for_cleanup(server_client, phase):
    _, client, gates = server_client
    gates.phase = phase
    gates.hold_cleanup = True
    if phase == "after":
        gates.transform_release.set()
    run = post(client, "waits")
    try:
        assert gates.phase_entered.wait(DEADLINE)
        cancel(client, run)
        assert gates.cleanup_entered.wait(DEADLINE)
        assert_active(get(client, run))
        cancel(client, run)
        cancel(client, run)
        assert_active(get(client, run))
        gates.cleanup_release.set()
        response = terminal(client, run)
        assert response.json()["result"]["state"] == "CANCELED"
        assert "cleanup finished" in texts(response.json()["result"])
    finally:
        gates.release_all()


@pytest.mark.parametrize("outcome", ["FAILED", "CANCELED"])
def test_pages_are_retained_across_terminal_failure_or_cancel(server_client, outcome):
    _, client, gates = server_client
    gates.hold_cleanup = True
    run = post(client, "breaks" if outcome == "FAILED" else "waits")
    try:
        if outcome == "CANCELED":
            assert gates.phase_entered.wait(DEADLINE)
            cancel(client, run)
        assert gates.cleanup_entered.wait(DEADLINE)
        response = get(client, run, eventPointer=0, eventLimit=1)
        assert_active(response)
        first = texts(response.json()["result"])
        assert len(first) == 1
        gates.cleanup_release.set()
        result = terminal(client, run).json()["result"]
        assert result["state"] == outcome
        messages = page_messages(client, run, result["eventCount"])
        assert messages[0] == first[0]
        assert "cleanup started" in messages
        assert messages[-1] == "cleanup finished"
        assert ("The upstream said no." if outcome == "FAILED" else "transform started") in messages
    finally:
        gates.release_all()


def test_multiplexed_result_waits_for_all_children_and_preserves_failure(server_client):
    server, client, gates = server_client
    gates.hold_cleanup = True
    gates.slow_cleanup_only = True
    run = post(client, "mixed", ("fail", "slow"))
    try:
        assert gates.cleanup_entered.wait(DEADLINE)
        contexts = server.runner.get_execution_context(run.rsplit("/", 1)[1]).contexts
        failed_child = next(context for context in contexts if context.input.value == "fail")
        response = wait_for(client, run, lambda result: (
            failed_child.result.state is ExecutionState.FAILED and "one child failed" in texts(result)
        ))
        assert_active(response)
        gates.cleanup_release.set()
        response = terminal(client, run)
        result = response.json()["result"]
        assert result["state"] == "FAILED"
        assert "one child failed" in texts(result)
        assert "successful child" in texts(result)
        assert "cleanup finished" in texts(result)
    finally:
        gates.release_all()
