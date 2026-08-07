# Copyright (c) Maltego Technologies GmbH.
import asyncio
import datetime
import uuid
from threading import Event, Thread
from unittest.mock import MagicMock

import pytest

from maltego.model.context import MaltegoContext
from maltego.model.entity import (
    MEF,
    Bookmark,
    MaltegoEntity,
    MaltegoEntityConfig,
    MaltegoEntityProperty,
)
from maltego.model.event import (
    TransformEntityEvent,
    TransformEventOperationType,
    TransformLinkEvent,
    TransformMessageEvent,
)
from maltego.model.exception import MaltegoTransformTimeoutError
from maltego.model.graph import MaltegoGraph
from maltego.model.link import MaltegoLink
from maltego.model.types import ExecutionState
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.runner import ThreadedTransformRunner, TransformRunner
from maltego.runner.transform_execution_context import (
    MultiplexedTransformResultSet,
    TransformExecutionContext,
    TransformGraphObserver,
)
from maltego.runner.transform_result_set import TransformResultSet

pytestmark = pytest.mark.unit


class MockEntity(MaltegoEntity):
    TYPE_NAME = "maltego.MockEntity"
    Config = MaltegoEntityConfig(
        value_property="value",
        display_name="Mock",
    )
    value: str = MEF()


def create_test_runner(retention_time=1) -> TransformRunner:
    return TransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
        retention_time=retention_time,
    )


def create_v3_execution_context(run_id="test-run-id") -> TransformExecutionContext:
    transform = MagicMock()
    transform.name = "test_transform"
    mock_request = MagicMock()
    mock_request.headers = {}
    context = MaltegoContext(MaltegoGraph(), mock_request, v3_request=True)
    return TransformExecutionContext(
        run_id=run_id,
        transform=transform,
        transform_input=MagicMock(),
        transform_settings={},
        limit=100,
        context=context,
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )


def make_result_stale(result_set, seconds=2) -> None:
    old_time = datetime.datetime.now() - datetime.timedelta(seconds=seconds)
    result_set.update_time = old_time
    result_set.last_fetch_time = old_time


class DeletingOnGetDict(dict):
    def __init__(self, run_id_to_delete, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_id_to_delete = run_id_to_delete
        self.deleted = False

    def get(self, key, default=None):
        if not self.deleted:
            self.deleted = True
            value = super().get(key, default)
            self.pop(self.run_id_to_delete, None)
            return value
        return super().get(key, default)


def create_mock_entity_add_event(entity=None) -> TransformEntityEvent:
    if entity is None:
        entity = MockEntity(str(uuid.uuid4()))
    return TransformEntityEvent(
        entity=entity,
        operation_type=TransformEventOperationType.ADD
    )


def create_mock_entity_update_event(entity, updates=None) -> TransformEntityEvent:
    if updates is None:
        updates = {"value": "bar"}
    return TransformEntityEvent(
        entity=entity,
        updates=updates,
        operation_type=TransformEventOperationType.UPDATE
    )


def create_mock_delete_entity_event(entity):
    return TransformEntityEvent(
        entity=entity,
        operation_type=TransformEventOperationType.DELETE
    )


@pytest.mark.parametrize(
    "method_name",
    [
        "done",
        "cancel",
        "result",
        "output_entities",
        "transform_run_execution_context",
        "exceptions",
        "status_code",
        "response_headers",
        "delete",
    ],
)
def test_runner_missing_run_id_methods_raise_key_error(method_name):
    runner = create_test_runner()

    with pytest.raises(KeyError):
        getattr(runner, method_name)("missing-run-id")


def test_threaded_runner_shutdown_closes_loop_with_pending_tasks():
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    startup_event = Event()
    thread = Thread(
        target=runner._ThreadedTransformRunner__thread,
        args=(startup_event,),
        daemon=True,
    )

    thread.start()
    assert startup_event.wait(timeout=1)

    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(asyncio.sleep(60), loop)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=1)

    try:
        assert not thread.is_alive()
        assert loop.is_closed()
    finally:
        if not loop.is_closed():
            for task in asyncio.all_tasks(loop=loop):
                task.cancel()
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


def test_threaded_runner_shutdown_awaits_cancelled_task_finalizers():
    """Stopping a worker loop must give cancelled transform tasks a chance to
    finish their cleanup before closing the loop."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    startup_event = Event()
    task_started = Event()
    task_finalized = Event()
    thread = Thread(
        target=runner._ThreadedTransformRunner__thread,
        args=(startup_event,),
        daemon=True,
    )

    async def waits_until_cancelled() -> None:
        try:
            task_started.set()
            await asyncio.Event().wait()
        finally:
            task_finalized.set()

    thread.start()
    assert startup_event.wait(timeout=1)

    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(waits_until_cancelled(), loop)
    assert task_started.wait(timeout=1)
    runner.shutdown()
    thread.join(timeout=1)

    assert task_finalized.is_set()
    assert not thread.is_alive()
    assert loop.is_closed()


def test_threaded_runner_shutdown_retries_cancellation_after_grace_period():
    """A task that absorbs one cancellation must not make shutdown wait
    forever; the runner retries cancellation after its grace period."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    task_started = Event()
    first_cancellation = Event()
    task_finalized = Event()
    shutdown_finished = Event()
    async def absorbs_one_cancellation() -> None:
        try:
            task_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                first_cancellation.set()
                await asyncio.Event().wait()
        finally:
            task_finalized.set()

    runner.startup()
    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(absorbs_one_cancellation(), loop)
    assert task_started.wait(timeout=1)

    def shutdown_runner() -> None:
        runner.shutdown()
        shutdown_finished.set()

    shutdown_thread = Thread(target=shutdown_runner, daemon=True)
    shutdown_thread.start()
    try:
        assert first_cancellation.wait(timeout=1)
        assert shutdown_finished.wait(timeout=3)
    finally:
        if not shutdown_finished.is_set():
            loop.call_soon_threadsafe(
                lambda: [pending.cancel() for pending in asyncio.all_tasks(loop)]
            )
        shutdown_thread.join(timeout=1)

    assert task_finalized.is_set()
    assert not shutdown_thread.is_alive()


def test_threaded_runner_shutdown_observes_task_finalizer_exceptions():
    """A cancellation finalizer may fail, but shutdown must consume that
    exception instead of producing a late 'exception was never retrieved'
    warning."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    task_started = Event()
    tasks = []

    async def raises_during_cancellation() -> None:
        try:
            task_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise RuntimeError("finalizer failure") from exc

    runner.startup()
    loop = runner.loops[0]
    loop.call_soon_threadsafe(
        lambda: tasks.append(asyncio.create_task(raises_during_cancellation()))
    )
    assert task_started.wait(timeout=1)

    runner.shutdown()

    assert tasks[0].done()
    assert not tasks[0]._log_traceback  # pylint: disable=protected-access


def test_threaded_runner_shutdown_cancels_tasks_started_by_finalizers():
    """A cancellation finalizer can schedule follow-up work; shutdown must
    discover and cancel it before closing the worker loop."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    parent_started = Event()
    child_started = Event()
    child_finalized = Event()

    async def child_task() -> None:
        try:
            child_started.set()
            await asyncio.Event().wait()
        finally:
            child_finalized.set()

    async def starts_child_during_cancellation() -> None:
        try:
            parent_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            asyncio.create_task(child_task())

    runner.startup()
    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(starts_child_during_cancellation(), loop)
    assert parent_started.wait(timeout=1)

    runner.shutdown()

    assert child_started.is_set()
    assert child_finalized.is_set()


def test_threaded_runner_shutdown_drains_nested_finalizer_tasks():
    """Shutdown continues draining when cancellation cleanup creates more than
    one generation of follow-up tasks."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    parent_started = Event()
    grandchild_finalized = Event()

    async def grandchild_task() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            grandchild_finalized.set()

    async def child_task() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            asyncio.create_task(grandchild_task())

    async def starts_child_during_cancellation() -> None:
        try:
            parent_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            asyncio.create_task(child_task())

    runner.startup()
    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(starts_child_during_cancellation(), loop)
    assert parent_started.wait(timeout=1)

    runner.shutdown()

    assert grandchild_finalized.is_set()


def test_threaded_runner_shutdown_allows_cooperative_cleanup_to_finish():
    """A task that handles cancellation needs an uninterrupted grace period
    for async cleanup rather than another cancellation on every poll."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    task_started = Event()
    cleanup_completed = Event()
    cleanup_interrupted = Event()

    async def completes_cleanup_after_cancellation() -> None:
        try:
            task_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            try:
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                cleanup_interrupted.set()
                raise
            cleanup_completed.set()

    runner.startup()
    loop = runner.loops[0]
    asyncio.run_coroutine_threadsafe(completes_cleanup_after_cancellation(), loop)
    assert task_started.wait(timeout=1)

    runner.shutdown()

    assert cleanup_completed.is_set()
    assert not cleanup_interrupted.is_set()


def test_threaded_runner_shutdown_cancels_real_after_transform_hook():
    """A real TransformExecutionContext blocked in its after-transform hook
    is drained cleanly when its threaded worker is shut down."""
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )
    after_transform_started = Event()
    after_transform_finalized = Event()

    class BlockingAfterTransformMiddleware(TransformMiddleware):
        async def before_transform(self, *args, **kwargs) -> None:
            del args, kwargs

        async def after_transform(self, *args, **kwargs) -> None:
            del args, kwargs
            try:
                after_transform_started.set()
                await asyncio.Event().wait()
            finally:
                after_transform_finalized.set()

    class SuccessfulTransform:
        name = "after_transform_shutdown"
        display_name = "After transform shutdown"
        composite_entities = False
        client_filter = None
        input_constraint = None
        annotation = MagicMock()

        async def __call__(self, *args, **kwargs) -> None:
            del args, kwargs

    transform = SuccessfulTransform()
    transform.annotation.uses_graph_payload.return_value = False
    request = MagicMock()
    request.headers = {}
    context = MaltegoContext(MaltegoGraph(), request, v3_request=True)
    execution_context = TransformExecutionContext(
        run_id="after-transform-shutdown",
        transform=transform,
        transform_input=MockEntity("input"),
        transform_settings={},
        limit=10,
        context=context,
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
        middlewares=[BlockingAfterTransformMiddleware()],
    )

    runner.startup()
    loop = runner.loops[0]
    execution_context.set_event_loop(loop)
    asyncio.run_coroutine_threadsafe(execution_context.start(), loop)
    assert after_transform_started.wait(timeout=1)

    runner.shutdown()

    assert execution_context.after_transform_task is not None
    assert execution_context.after_transform_task.cancelled()
    assert after_transform_finalized.is_set()


def test_threaded_runner_shutdown_is_idempotent():
    runner = ThreadedTransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
    )

    runner.startup()
    runner.shutdown()
    runner.shutdown()


def test_single_entity_update_event(transform_result_set):
    mock_entity = MockEntity("foo")
    transform_result_set.output_queue.put(
        create_mock_entity_add_event(mock_entity)
    )
    for i in range(10):
        transform_result_set.output_queue.put(
            create_mock_entity_update_event(
                entity=mock_entity,
                updates={
                    "value": i
                }
            )
        )
        transform_result_set.output_queue.put(
            create_mock_entity_update_event(
                entity=mock_entity,
                updates={
                    "bookmark": Bookmark.GREEN
                }
            )
        )

    results = transform_result_set.get_results()
    assert len(results) == 2
    entity_update_event = results[1]
    assert isinstance(entity_update_event, TransformEntityEvent)
    assert entity_update_event.updates == {"value": 9, "bookmark": Bookmark.GREEN}


def test_multiple_entity_update_events(transform_result_set):
    entity_add_count = 2
    entity_update_count = 10
    for i in range(entity_add_count):
        mock_entity = MockEntity(f"{i}")
        transform_result_set.output_queue.put(
            create_mock_entity_add_event(mock_entity)
        )
        for j in range(entity_update_count):
            transform_result_set.output_queue.put(
                create_mock_entity_update_event(entity=mock_entity, updates={"value": j})
            )
    results = transform_result_set.get_results()
    assert len(results) == 4
    for index, result in enumerate(results):
        if index % 2 == 0:
            assert isinstance(results[index], TransformEntityEvent)
            assert results[index].operation_type == TransformEventOperationType.ADD
            assert isinstance(results[index+1], TransformEntityEvent)
            assert results[index+1].operation_type == TransformEventOperationType.UPDATE
            assert results[index+1].updates == {"value": entity_update_count - 1}


def test_multiple_property_update_events(transform_result_set):

    entity_one = MockEntity("entity one")
    entity_two = MockEntity("entity two")

    # add the first entity event
    transform_result_set.output_queue.put(
        create_mock_entity_add_event(entity_one)
    )

    # update 1 to the first entity
    transform_result_set.output_queue.put(
        create_mock_entity_update_event(entity=entity_one)
    )

    # add the second entity
    transform_result_set.output_queue.put(
        create_mock_entity_add_event(entity_two)
    )

    # second update to the first entity
    transform_result_set.output_queue.put(
        create_mock_entity_update_event(entity=entity_one, updates={"update_value": "foo"})
    )

    # perform 5 property updates on the first added entity
    for i in range(5):
        updates = {"_properties": [
            MaltegoEntityProperty(name="updated_1", value=i),
            MaltegoEntityProperty(name="updated_2", value=i),
            MaltegoEntityProperty(name="updated_3", value=i),
        ]
        }
        transform_result_set.output_queue.put(
            create_mock_entity_update_event(entity=entity_one, updates=updates)
        )

    # third update to the first added entity (should be the final value of value)
    transform_result_set.output_queue.put(
        create_mock_entity_update_event(entity=entity_one, updates={"update_value": "bar"})
    )

    added_entities = transform_result_set.get_added_entities()
    assert len(added_entities) == 2
    results = transform_result_set.get_results()

    for result in results:
        print(result.get_id())

    event_zero = results[0]
    assert isinstance(event_zero, TransformEntityEvent)
    assert event_zero.operation_type == TransformEventOperationType.ADD

    event_one = results[1]
    assert event_one.operation_type == TransformEventOperationType.UPDATE
    assert isinstance(event_one, TransformEntityEvent)
    assert event_one.entity is not None
    assert event_one.updates['value'] == "bar"

    event_two = results[2]
    assert isinstance(event_two, TransformEntityEvent)
    assert event_two.operation_type == TransformEventOperationType.ADD

    event_three = results[3]
    assert isinstance(event_three, TransformEntityEvent)
    assert len(event_three.updates['_properties']) == 3
    assert event_three.updates['_properties'][0].value == 4


def test_event_order(transform_result_set):

    entity_add_count = 500
    entity_update_count = 10

    for i in range(entity_add_count):

        mock_entity = MockEntity(i)
        transform_result_set.output_queue.put(
            create_mock_entity_add_event(entity=mock_entity)
        )

        for j in range(entity_update_count):
            transform_result_set.output_queue.put(
                create_mock_entity_update_event(entity=mock_entity, updates={"value": j})
            )

        transform_result_set.output_queue.put(
            create_mock_delete_entity_event(entity=mock_entity)
        )

        transform_result_set.output_queue.put(
            create_mock_entity_add_event(entity=mock_entity)
        )

    results = transform_result_set.get_results()

    for index, result in enumerate(results):
        print(result.get_id())

    assert len(results) == entity_add_count * 4

    for index, result in enumerate(results):
        print(result.get_id())
        if index % 4 == 0:
            assert results[index].operation_type == TransformEventOperationType.ADD
            assert results[index + 1].operation_type == TransformEventOperationType.UPDATE
            assert results[index + 2].operation_type == TransformEventOperationType.DELETE
            assert results[index + 3].operation_type == TransformEventOperationType.ADD


@pytest.mark.asyncio
async def test_result_set_waiting_for_prompt_flag(transform_result_set):
    """Test that waiting_for_prompt flag is properly managed"""
    # Initially not waiting
    assert transform_result_set.is_waiting_for_prompt() is False
    assert transform_result_set.waiting_for_prompt_since is None
    
    # Mark as waiting
    transform_result_set.mark_waiting_for_prompt()
    assert transform_result_set.is_waiting_for_prompt() is True
    assert transform_result_set.waiting_for_prompt_since is not None
    assert isinstance(transform_result_set.waiting_for_prompt_since, datetime.datetime)
    
    # Clear waiting flag
    transform_result_set.clear_waiting_for_prompt()
    assert transform_result_set.is_waiting_for_prompt() is False
    assert transform_result_set.waiting_for_prompt_since is None


@pytest.mark.asyncio
async def test_cleanup_skips_transform_waiting_for_prompt():
    """Test that cleanup logic skips transforms waiting for prompt responses"""
    # Create a runner with very short retention time (1 second)
    runner = TransformRunner(
        middlewares=[],
        transform_execution_timeout=60,
        middleware_execution_timeout=60,
        retention_time=1  # Very short for testing
    )
    
    # Create a mock transform
    transform = MagicMock()
    transform.name = "test_prompt_transform"
    
    # Create execution context
    mock_request = MagicMock()
    mock_request.headers = {}
    context = MaltegoContext(MaltegoGraph(), mock_request, v3_request=True)
    
    execution_context = TransformExecutionContext(
        run_id="test-run-id",
        transform=transform,
        transform_input=MagicMock(),  # Mock entity
        transform_settings={},
        limit=100,
        context=context,
        transform_execution_timeout=60,
        middleware_execution_timeout=60
    )

    result_set = execution_context.result
    context.set_result_set(result_set)
    
    # Add to runner
    run_id = runner._TransformRunner__add(execution_context)
    
    # Mark as waiting for prompt
    result_set.mark_waiting_for_prompt()
    
    # Set times to be old enough to trigger cleanup (2 seconds ago)
    old_time = datetime.datetime.now() - datetime.timedelta(seconds=2)
    result_set.update_time = old_time
    result_set.last_fetch_time = old_time
    
    # Run cleanup
    runner.cleanup()
    
    # Should still exist in queue (not cleaned up)
    assert run_id in runner._TransformRunner__transform_queue
    
    # Cleanup
    runner._TransformRunner__delete(run_id)


def test_cleanup_marks_stale_v3_run_timed_out():
    runner = create_test_runner(retention_time=1)
    execution_context = create_v3_execution_context()
    run_id = runner._TransformRunner__add(execution_context)
    result_set = execution_context.result
    make_result_stale(result_set)

    runner.cleanup()

    assert run_id in runner._TransformRunner__transform_queue
    assert result_set.state == ExecutionState.TIMED_OUT
    assert len(result_set.exceptions) == 1
    timeout_exception = result_set.exceptions[0]
    assert isinstance(timeout_exception, MaltegoTransformTimeoutError)
    assert timeout_exception.message == (
        "Transform execution timed out after being inactive for 1s."
    )
    assert timeout_exception.code == 410

    runner._TransformRunner__delete(run_id)


def test_cleanup_deletes_stale_previously_timed_out_v3_run():
    runner = create_test_runner(retention_time=1)
    execution_context = create_v3_execution_context()
    run_id = runner._TransformRunner__add(execution_context)
    result_set = execution_context.result
    result_set.state = ExecutionState.TIMED_OUT
    make_result_stale(result_set)

    runner.cleanup()

    assert run_id not in runner._TransformRunner__transform_queue


def test_cleanup_tolerates_run_deleted_during_cleanup_iteration():
    runner = create_test_runner(retention_time=1)
    execution_context = create_v3_execution_context()
    run_id = runner._TransformRunner__add(execution_context)
    result_set = execution_context.result
    result_set.state = ExecutionState.TIMED_OUT
    make_result_stale(result_set)
    runner._TransformRunner__transform_queue = DeletingOnGetDict(
        run_id,
        runner._TransformRunner__transform_queue,
    )

    runner.cleanup()

    assert run_id not in runner._TransformRunner__transform_queue


# ---------------------------------------------------------------------------
# Top-level entity counts + incomplete-composite detection
# ---------------------------------------------------------------------------


class CompositeChild(MaltegoEntity):
    TYPE_NAME = "maltego.CompositeChild"
    Config = MaltegoEntityConfig(
        value_property="child_value",
        display_name="CompositeChild",
    )
    child_value: str = MEF(name="child_value")


class CompositeParent(MaltegoEntity):
    TYPE_NAME = "maltego.CompositeParent"
    Config = MaltegoEntityConfig(
        value_property="parent_value",
        display_name="CompositeParent",
    )
    parent_value: str = MEF(name="parent_value")
    # Two entity-typed properties -> a real composite has MULTIPLE children,
    # not a single one.
    primary_child: CompositeChild = MEF(name="primary_child")
    secondary_child: CompositeChild = MEF(name="secondary_child")


class AtomicInput(MaltegoEntity):
    TYPE_NAME = "maltego.AtomicInput"
    Config = MaltegoEntityConfig(
        value_property="input_value",
        display_name="AtomicInput",
    )
    input_value: str = MEF(name="input_value")


def _new_result_set() -> TransformResultSet:
    mock_request = MagicMock()
    mock_request.headers = {}
    context = MaltegoContext(MaltegoGraph(), mock_request)
    return TransformResultSet(context)


def _emit_composite_group(result_set: TransformResultSet) -> None:
    """Emit one composite group through the real graph observer.

    This drives the actual emission path so the structure under test matches
    what the SDK produces in production, not a hand-built approximation. A
    composite added via ``add_child`` emits, contiguously:

        composite parent ADD
        composite child entity ADD (x2 here)
        composite property link ADD (x2 here)
        ordinary connecting link ADD (input -> parent; NOT composite-tagged)
    """
    graph = MaltegoGraph()
    observer = TransformGraphObserver(
        result_set.output_queue, "test-run", graph, composite_entities=True
    )
    graph.register(observer)
    input_entity = AtomicInput("input-val")
    input_entity.input_value = "input-val"
    graph.add_entity(input_entity)
    primary = CompositeChild("primary-val")
    primary.child_value = "primary-val"
    secondary = CompositeChild("secondary-val")
    secondary.child_value = "secondary-val"
    parent = CompositeParent("parent-val")
    parent.parent_value = "parent-val"
    parent.primary_child = primary
    parent.secondary_child = secondary
    graph.add_child(input_entity, parent)


def test_atomic_only_adds_counted():
    result_set = _new_result_set()
    for i in range(3):
        result_set.output_queue.put(create_mock_entity_add_event(MockEntity(f"a{i}")))

    assert result_set.atomic_entity_count == 3
    assert result_set.composite_entity_count == 0


def test_emission_ordering_parent_children_links_then_connecting_link():
    """Pin the real composite emission structure the boundary rule depends on.

    A group emitted via ``add_child(input, composite)`` is:
    [input atomic, composite parent, composite child x2, composite link x2,
     ordinary connecting link]. The group ends on a NON-composite link.
    """
    result_set = _new_result_set()
    _emit_composite_group(result_set)
    results = result_set.get_results()

    # input atomic + parent + 2 children + 2 composite links + 1 connecting link
    assert len(results) == 7

    # [0] the input atomic entity
    assert isinstance(results[0], TransformEntityEvent)
    assert not results[0].entity.is_composite_instance
    assert not results[0].entity._is_composite_child()

    # [1] the composite parent
    assert isinstance(results[1], TransformEntityEvent)
    assert results[1].entity.is_composite_instance
    assert not results[1].entity._is_composite_child()

    # [2], [3] composite children (multiple, all tagged as composite children)
    for idx in (2, 3):
        assert isinstance(results[idx], TransformEntityEvent)
        assert results[idx].entity._is_composite_child()

    # [4], [5] composite property links
    for idx in (4, 5):
        assert isinstance(results[idx], TransformLinkEvent)
        assert results[idx].link._is_composite()

    # [6] trailing ordinary connecting link (input -> parent), NOT composite
    assert isinstance(results[6], TransformLinkEvent)
    assert not results[6].link._is_composite()


def test_composite_parent_counted_children_excluded():
    result_set = _new_result_set()
    _emit_composite_group(result_set)

    # one composite parent; its children are excluded; the input is atomic
    assert result_set.composite_entity_count == 1
    assert result_set.atomic_entity_count == 1


def test_composite_child_excluded_explicitly():
    result_set = _new_result_set()
    _emit_composite_group(result_set)
    results = result_set.get_results()

    # the composite children sit at indices 2 and 3
    assert results[2].entity._is_composite_child()
    assert results[3].entity._is_composite_child()
    # counts include exactly the input atomic + the composite parent, never the
    # two composite children
    assert result_set.atomic_entity_count + result_set.composite_entity_count == 2


def test_links_messages_and_non_add_ops_excluded():
    result_set = _new_result_set()
    entity = MockEntity("e0")
    result_set.output_queue.put(create_mock_entity_add_event(entity))
    # a plain (non-composite) link ADD
    result_set.output_queue.put(
        TransformLinkEvent(
            link=MaltegoLink("e0", "e1"),
            operation_type=TransformEventOperationType.ADD,
        )
    )
    # a message event
    result_set.output_queue.put(
        TransformMessageEvent(log_tuple=("Info", "hello"), state="RUNNING")
    )
    # an UPDATE and a DELETE on the entity
    result_set.output_queue.put(create_mock_entity_update_event(entity))
    result_set.output_queue.put(create_mock_delete_entity_event(entity))

    # only the single atomic ADD is counted
    assert result_set.atomic_entity_count == 1
    assert result_set.composite_entity_count == 0


def test_event_count_still_counts_everything():
    result_set = _new_result_set()
    result_set.output_queue.put(create_mock_entity_add_event(MockEntity("a0")))
    result_set.output_queue.put(
        TransformLinkEvent(
            link=MaltegoLink("a0", "a1"),
            operation_type=TransformEventOperationType.ADD,
        )
    )
    result_set.output_queue.put(
        TransformMessageEvent(log_tuple=("Info", "hello"), state="RUNNING")
    )

    assert result_set.event_count == 3
    assert result_set.atomic_entity_count == 1


def test_multiplexed_sums_atomic_and_composite():
    rs_a = _new_result_set()
    rs_a.output_queue.put(create_mock_entity_add_event(MockEntity("a0")))
    rs_a.output_queue.put(create_mock_entity_add_event(MockEntity("a1")))

    rs_b = _new_result_set()
    _emit_composite_group(rs_b)  # 1 atomic input + 1 composite parent
    rs_b.output_queue.put(create_mock_entity_add_event(MockEntity("b0")))

    mux = MultiplexedTransformResultSet([rs_a, rs_b])

    assert mux.atomic_entity_count == 4  # a0, a1, input, b0
    assert mux.composite_entity_count == 1  # one composite parent in rs_b


def test_ends_mid_composite_forward_rule_all_event_kinds():
    """The single forward rule: True iff the next un-returned event continues a
    composite group (child or composite link), never on a parent / atomic /
    ordinary link / boundary at-or-past-end."""
    result_set = _new_result_set()
    _emit_composite_group(result_set)
    # append a fresh atomic entity after the completed composite group
    result_set.output_queue.put(create_mock_entity_add_event(MockEntity("atomic")))
    result_set.get_results()
    # output: [0]atomic input [1]composite parent [2]child [3]child
    #         [4]compLink [5]compLink [6]ordinary connecting link [7]atomic
    assert result_set.ends_mid_composite(0) is False  # boundary 0 -> always False
    assert result_set.ends_mid_composite(1) is False  # next is composite PARENT
    assert result_set.ends_mid_composite(2) is True   # next is composite child
    assert result_set.ends_mid_composite(3) is True   # next is composite child
    assert result_set.ends_mid_composite(4) is True   # next is composite link
    assert result_set.ends_mid_composite(5) is True   # next is composite link
    assert result_set.ends_mid_composite(6) is False  # next is ordinary link
    assert result_set.ends_mid_composite(7) is False  # next is atomic entity
    # boundary at / past the end of output -> no next event -> False
    assert result_set.ends_mid_composite(8) is False
    assert result_set.ends_mid_composite(99) is False


def test_continues_composite_helper_classifies_each_kind():
    result_set = _new_result_set()
    _emit_composite_group(result_set)
    events = result_set.get_results()
    # [0]atomic input [1]parent [2]child [3]child [4]compLink [5]compLink
    # [6]ordinary connecting link
    assert result_set._continues_composite(events[0]) is False  # atomic entity
    assert result_set._continues_composite(events[1]) is False  # composite parent
    assert result_set._continues_composite(events[2]) is True   # composite child
    assert result_set._continues_composite(events[4]) is True   # composite link
    assert result_set._continues_composite(events[6]) is False  # ordinary link


def test_multiplexed_ends_mid_composite_delegates_to_child():
    rs_a = _new_result_set()
    rs_a.output_queue.put(create_mock_entity_add_event(MockEntity("a0")))

    rs_b = _new_result_set()
    _emit_composite_group(rs_b)

    mux = MultiplexedTransformResultSet([rs_a, rs_b])
    # flattened output:
    #   [0] a0 (rs_a)
    #   [1] input  [2] parent  [3] child  [4] child  [5] compLink
    #   [6] compLink  [7] connectingLink   (all rs_b)
    # boundary 3 falls inside rs_b right after its parent -> next event is a
    # composite child -> mid-composite within that child set.
    assert mux.ends_mid_composite(3) is True
    # boundary 1 is the clean seam between rs_a and rs_b (next is rs_b's atomic
    # input entity, not a composite continuation).
    assert mux.ends_mid_composite(1) is False
