# Copyright (c) Maltego Technologies GmbH.
import asyncio
import datetime
from unittest.mock import MagicMock

import pytest

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.context import MaltegoContext
from maltego.model.entity import MEF, MaltegoEntity, MaltegoEntityConfig
from maltego.model.event import TransformMessageEvent
from maltego.model.exception import MaltegoException, MaltegoTransformTimeoutError
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.types import ExecutionState
from maltego.runner import TransformRunner
from maltego.runner.transform_execution_context import (
    MultiplexedTransformExecutionContext,
    MultiplexedTransformResultSet,
    TransformExecutionContext,
)
from maltego.runner.transform_result_set import TERMINAL_STATES, TransformResultSet

pytestmark = pytest.mark.unit


class Input(MaltegoEntity):
    TYPE_NAME = "maltego.FinalityInput"
    Config = MaltegoEntityConfig(value_property="value", display_name="Input")
    value: str = MEF()


def make_transform(impl):
    return MaltegoTransform(
        impl=impl, name="finality", display_name="Finality", description="Finality",
        settings=[], transform_ns="test", composite_entities=False,
    )


def make_context(impl, middlewares=(), timeout=60):
    entity = Input("input")
    request = MagicMock()
    request.headers = {}
    context = MaltegoContext(MaltegoGraph(entities=[entity]), request, v3_request=True)
    return TransformExecutionContext(
        "finality", make_transform(impl), entity, {}, context, 12, timeout, timeout,
        list(middlewares),
    )


class Hook(TransformMiddleware):
    def __init__(self, before=None, after=None, call_on_failure=True):
        self.before = before
        self.after = after
        self.call_on_failure = call_on_failure

    async def before_transform(self, *args):
        if self.before:
            await self.before(*args)

    async def after_transform(self, *args, **kwargs):
        if self.after:
            await self.after(*args, **kwargs)


def messages(result):
    return [event.message for event in result.get_results() if isinstance(event, TransformMessageEvent)]


async def finish_task(task, *gates):
    for gate in gates:
        gate.set()
    if not task.done():
        task.cancel()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)


@pytest.mark.asyncio
async def test_failure_remains_nonterminal_until_afterhook_output():
    entered, release = asyncio.Event(), asyncio.Event()

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        raise MaltegoException("transform failed")

    async def after(transform, entity, output, context, state, exceptions=None):
        assert state == ExecutionState.FAILED
        entered.set()
        await release.wait()
        context.log.inform("cleanup output")

    execution = make_context(transform, [Hook(after=after)])
    running = asyncio.create_task(execution.start())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert execution.result.state not in TERMINAL_STATES
        assert not execution.done()
        assert execution.result.end_time is None
        release.set()
        await asyncio.wait_for(running, 2)
        assert execution.result.state == ExecutionState.FAILED
        assert "cleanup output" in messages(execution.result)
    finally:
        await finish_task(running, release)


@pytest.mark.asyncio
async def test_afterhook_failure_continues_eligible_hooks_and_skips_success_only():
    called = []

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        return []

    async def fail(*args, **kwargs):
        called.append("failure")
        raise MaltegoException("hook failed")

    async def skip(*args, **kwargs):
        called.append("success-only")

    async def cleanup(transform, entity, output, context, state, exceptions=None):
        called.append(state)
        context.log.inform("later cleanup")

    execution = make_context(transform, [Hook(after=fail), Hook(after=skip, call_on_failure=False), Hook(after=cleanup)])
    await execution.start()
    assert called == ["failure", ExecutionState.FAILED]
    assert execution.result.state == ExecutionState.FAILED
    assert "later cleanup" in messages(execution.result)
    assert len(execution.result.exceptions) == 1


@pytest.mark.asyncio
async def test_afterhook_timeout_preserves_limit_and_runs_later_cleanup():
    called = []

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        return []

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    async def cleanup(*args, **kwargs):
        called.append("cleanup")

    execution = make_context(transform, [Hook(after=stalled), Hook(after=cleanup)])
    execution.middleware_execution_timeout = 0.01
    await execution.start()
    assert called == ["cleanup"]
    assert execution.result.state == ExecutionState.FAILED
    assert "Timeout after" in execution.result.exceptions[0].message


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["prestart", "before", "transform", "after"])
async def test_cancellation_is_latched_and_cleanup_is_not_repeatedly_interrupted(phase):
    entered, release, cleanup_entered, cleanup_release = (asyncio.Event() for _ in range(4))
    calls = []

    async def before(*args):
        if phase == "before":
            entered.set()
            await release.wait()

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        calls.append("transform")
        if phase == "transform":
            entered.set()
            await release.wait()
        return []

    async def first_after(*args, **kwargs):
        if phase == "after":
            entered.set()
            await release.wait()

    async def after(transform, entity, output, context, state, exceptions=None):
        calls.append("cleanup")
        cleanup_entered.set()
        await cleanup_release.wait()
        context.log.inform("cleanup complete")

    execution = make_context(transform, [Hook(before=before, after=first_after), Hook(after=after)])
    if phase == "prestart":
        execution.cancel()
    running = asyncio.create_task(execution.start())
    try:
        if phase != "prestart":
            await asyncio.wait_for(entered.wait(), 2)
            execution.cancel()
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        execution.cancel()
        execution.cancel()
        assert execution.result.state not in TERMINAL_STATES
        assert execution.result.end_time is None
        cleanup_release.set()
        await asyncio.wait_for(running, 2)
        assert execution.result.state == ExecutionState.CANCELED
        assert calls.count("cleanup") == 1
        if phase in ("prestart", "before"):
            assert "transform" not in calls
        assert "cleanup complete" in messages(execution.result)
    finally:
        await finish_task(running, release, cleanup_release)


@pytest.mark.asyncio
async def test_hook_failure_outranks_cancellation():
    entered = asyncio.Event()

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        entered.set()
        await asyncio.Event().wait()
        return []

    async def fail(*args, **kwargs):
        raise MaltegoException("cleanup failed")

    execution = make_context(transform, [Hook(after=fail)])
    running = asyncio.create_task(execution.start())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        execution.cancel()
        await asyncio.wait_for(running, 2)
        assert execution.result.state == ExecutionState.FAILED
    finally:
        await finish_task(running)


@pytest.mark.asyncio
async def test_inactivity_timeout_stops_active_transform_and_waits_for_cleanup():
    entered, cleanup_entered, cleanup_release = (asyncio.Event() for _ in range(3))

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        entered.set()
        await asyncio.Event().wait()
        return []

    async def cleanup(transform, entity, output, context, state, exceptions=None):
        cleanup_entered.set()
        await cleanup_release.wait()
        context.log.inform("expired cleanup")
        raise MaltegoException("cleanup failure")

    execution = make_context(transform, [Hook(after=cleanup)])
    runner = TransformRunner([], 60, 60, retention_time=1)
    runner._TransformRunner__add(execution)
    running = asyncio.create_task(execution.start())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        stale = execution.result.update_time - datetime.timedelta(seconds=2)
        execution.result.update_time = stale
        execution.result.last_fetch_time = stale
        runner.cleanup()
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        assert execution.result.state not in TERMINAL_STATES
        execution.result.update_time = stale
        execution.result.last_fetch_time = stale
        runner.cleanup()
        assert runner.get_execution_context(execution.run_id) is execution
        cleanup_release.set()
        await asyncio.wait_for(running, 2)
        assert execution.result.state == ExecutionState.TIMED_OUT
        assert execution.done()
        assert sum(isinstance(exc, MaltegoTransformTimeoutError) for exc in execution.result.exceptions) == 1
        assert "expired cleanup" in messages(execution.result)
    finally:
        await finish_task(running, cleanup_release)



def test_multiplexed_outcome_waits_for_all_and_preserves_failure_precedence():
    request = MagicMock()
    request.headers = {}
    results = [TransformResultSet(MaltegoContext(MaltegoGraph(), request, v3_request=True)) for _ in range(2)]
    mux = MultiplexedTransformResultSet(results)
    results[0].state = ExecutionState.FAILED
    results[1].state = ExecutionState.RUNNING
    assert mux.state not in TERMINAL_STATES
    results[1].state = ExecutionState.COMPLETED
    assert mux.state == ExecutionState.FAILED
    results[1].state = ExecutionState.TIMED_OUT
    assert mux.state == ExecutionState.TIMED_OUT


@pytest.mark.asyncio
async def test_multiplexed_cancel_latches_not_yet_scheduled_children():
    started, release = asyncio.Event(), asyncio.Event()
    visited = []

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        visited.append(input_entity.value)
        started.set()
        await release.wait()
        return []

    request = MagicMock()
    request.headers = {}
    entities = [Input("first"), Input("second")]
    context = MaltegoContext(MaltegoGraph(entities=entities), request, v3_request=True)
    mux = MultiplexedTransformExecutionContext("mux", make_transform(transform), entities, {}, context, 12, 60, 60)
    running = asyncio.create_task(mux.start())
    try:
        await asyncio.wait_for(started.wait(), 2)
        mux.cancel()
        await asyncio.wait_for(running, 2)
        assert visited == ["first"]
        assert all(child.result.state == ExecutionState.CANCELED for child in mux.contexts)
        assert mux.result.state == ExecutionState.CANCELED
    finally:
        await finish_task(running, release)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before", "transform", "after"])
async def test_orchestration_cancellation_waits_for_timed_out_phase_cleanup(phase):
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def held_cleanup(context):
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            context.log.inform("phase cleanup finished")

    async def transform(input_entity: Input, context: MaltegoContext) -> list[Input]:
        if phase == "transform":
            await held_cleanup(context)
        return []

    async def before(transform, entity, properties, context, soft_limit, hard_limit):
        if phase == "before":
            await held_cleanup(context)

    async def after(transform, entity, output, context, state, exceptions=None):
        if phase == "after":
            await held_cleanup(context)

    execution = make_context(transform, [Hook(before=before, after=after)], timeout=0.01)
    running = asyncio.create_task(execution.start())
    try:
        await asyncio.wait_for(cleaning.wait(), 2)
        running.cancel()
        finished, _ = await asyncio.wait({running}, timeout=0.05)
        assert not finished, "orchestration ended while its phase was still cleaning up"
        assert not execution.done(), "terminal state escaped while a phase was still cleaning up"
        running.cancel()
        finished, _ = await asyncio.wait({running}, timeout=0.05)
        assert not finished
        release.set()
        await asyncio.wait_for(asyncio.gather(running, return_exceptions=True), 2)
        assert "phase cleanup finished" in messages(execution.result)
        assert execution.done()
    finally:
        await finish_task(running, release)
