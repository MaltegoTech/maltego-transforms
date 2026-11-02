# Copyright (c) Maltego Technologies GmbH.
import queue

import asyncio
import logging
from datetime import datetime
from threading import Lock
from typing import Union, List, Any, Dict, Optional, Iterable

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.context import MaltegoCapability, MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.event import (
    TransformEvent,
    TransformEntityEvent,
    TransformLinkEvent,
    TransformEventOperationType,
)
from maltego.model.exception import (
    MaltegoException,
    MaltegoHTTPClientError,
    MaltegoHTTPInputEntityMalformed,
    MaltegoHTTPServerError,
    MaltegoTransformTimeoutError,
    MaltegoUnsupportedCapabilityError,
    MaltegoVersionNotSupported,
    MaltegoWarning,
)
from maltego.model.graph import MaltegoGraph
from maltego.model.link import MaltegoLink
from maltego.model.observer import Observer, Observable
from maltego.model.transform import MaltegoTransform, TransformRunExecutionInput
from maltego.model.types import MaltegoSettingTypes, ExecutionState
from maltego.runner.transform_result_set import TERMINAL_STATES, TransformResultSet
from maltego.util.collections_utils import flatten

log = logging.getLogger(__name__)
OUTCOME_PRECEDENCE = {
    ExecutionState.FINISHED: 0,
    ExecutionState.COMPLETED: 0,
    ExecutionState.CANCELED: 1,
    ExecutionState.FAILED: 2,
    ExecutionState.TIMED_OUT: 3,
}



class MultiplexedTransformResultSet:
    results: tuple[TransformResultSet, ...]

    def __init__(self, results: Iterable[TransformResultSet]):
        self.results = tuple(results)
        self.output: List[TransformEvent] = []
        self._taken = [0] * len(self.results)

    def __gather(self) -> List[TransformEvent]:
        # Only advance past events we copied.
        for index, result in enumerate(self.results):
            if result.event_count > self._taken[index]:
                new_events = result.output[self._taken[index]:]
                self.output.extend(new_events)
                self._taken[index] += len(new_events)
        return self.output

    def get_added_entities(self) -> List[MaltegoEntity]:
        return [
            event.entity
            for event in self.__gather()
            if isinstance(event, TransformEntityEvent) and event.operation_type == TransformEventOperationType.ADD
        ]

    def get_results(self) -> List[TransformEvent]:
        now = datetime.now()
        for result in self.results:
            result.last_fetch_time = now
        return self.__gather()

    def get_response_headers(self) -> dict[str, str]:
        response_headers: dict[str, str] = {}
        for result in self.results:
            response_headers.update(result.context.response_headers)
        return response_headers

    @property
    def exceptions(self) -> List[MaltegoException]:
        return list(flatten(r.exceptions for r in self.results))

    @property
    def exception_stack(self) -> List[MaltegoException]:
        return list(flatten(r.exception_stack for r in self.results))

    @property
    def event_count(self) -> int:
        return len(self.__gather())

    @property
    def atomic_entity_count(self) -> int:
        return sum(r.atomic_entity_count for r in self.results)

    @property
    def composite_entity_count(self) -> int:
        return sum(r.composite_entity_count for r in self.results)

    def ends_mid_composite(self, boundary_index: int) -> bool:
        """Same forward rule as ``TransformResultSet.ends_mid_composite``, applied to the merged output."""
        output = self.__gather()
        if boundary_index <= 0 or boundary_index >= len(output):
            return False
        return TransformResultSet._continues_composite(output[boundary_index])  # pylint: disable=protected-access

    @property
    def state(self) -> ExecutionState:
        states = [result.state for result in self.results]
        active = [state for state in states if state not in TERMINAL_STATES]
        if active:
            return min(active, key=list(ExecutionState).index)
        return max(states, key=OUTCOME_PRECEDENCE.__getitem__)

    @property
    def start_time(self) -> datetime:
        return min(r.start_time for r in self.results)

    @property
    def update_time(self) -> datetime:
        return max(r.update_time for r in self.results)

    @property
    def last_fetch_time(self) -> datetime:
        return max(r.last_fetch_time for r in self.results)

    @property
    def code(self) -> int:
        return max(r.code for r in self.results)

    @state.setter
    def state(self, value):
        for r in self.results:
            r.state = value

    def push_exception(self, exception: MaltegoException, state: Optional[ExecutionState] = None) -> None:
        for r in self.results:
            r.push_exception(exception, state=state)

    @update_time.setter
    def update_time(self, value):
        for r in self.results:
            r.update_time = value

    def get_duration(self) -> int:
        """
        Returns the maximum (i.e. slowest) transform-duration among
        all child result‐sets, in milliseconds.
        """
        return max(r.get_duration() for r in self.results)

    def get_current_duration(self) -> int:
        """
        Returns the maximum “live” duration (from start_time until now
        or end_time) among all child result‐sets, in milliseconds.
        """
        return max(r.get_current_duration() for r in self.results)
    def is_waiting_for_prompt(self) -> bool:
        """Check if any child result is waiting for user prompt response"""
        return any(r.is_waiting_for_prompt() for r in self.results)

class MultiplexedTransformExecutionContext:
    contexts: tuple["TransformExecutionContext", ...]
    __result: MultiplexedTransformResultSet

    def __init__(
        self,
        run_id: str,
        transform: MaltegoTransform,
        transform_inputs: Iterable[
            Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]]
        ],
        transform_settings: Dict[str, MaltegoSettingTypes],
        context: MaltegoContext,
        limit: int,
        transform_execution_timeout: int,
        middleware_execution_timeout: int,
        middlewares: Optional[List[TransformMiddleware]] = None,
    ):
        self.run_id = run_id
        self.contexts = tuple(
            TransformExecutionContext(
                run_id,
                transform,
                transform_input,
                transform_settings,
                context.for_input(),
                limit,
                transform_execution_timeout,
                middleware_execution_timeout,
                middlewares,
            )
            for transform_input in transform_inputs
        )
        if not self.contexts:
            raise ValueError("MultiplexedTransformExecutionContext requires at least one transform input")
        self.__result = MultiplexedTransformResultSet(c.result for c in self.contexts)

    def v3_request(self) -> bool:
        return True

    def start_sync(self) -> None:
        for ctx in self.contexts:
            ctx.start_sync()

    async def start(self) -> None:
        for ctx in self.contexts:
            await ctx.start()

    def done(self) -> bool:
        return all(ctx.done() for ctx in self.contexts)

    def cancel(self) -> None:
        for ctx in self.contexts:
            ctx.cancel()

    def expire(self, exception: MaltegoTransformTimeoutError) -> None:
        for ctx in self.contexts:
            ctx.expire(exception)

    async def receive_input(self, transform_input: TransformRunExecutionInput) -> None:
        for ctx in self.contexts:
            await ctx.receive_input(transform_input)

    def get_response_headers(self) -> dict[str, str]:
        response_headers_all: dict[str, str] = {}
        for ctx in self.contexts:
            response_headers = ctx.get_response_headers()
            for key, value in response_headers.items():
                if not isinstance(value, str):
                    raise ValueError(
                        f"Response header '{key}' has a value of type {type(value).__name__}, "
                        f"expected type 'str' for value {value}"
                    )
            response_headers_all.update(response_headers)
        return response_headers_all

    @property
    def result(self) -> MultiplexedTransformResultSet:
        return self.__result

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        for ctx in self.contexts:
            ctx.set_event_loop(loop)


class TransformExecutionContext:
    """Handles the transform execution from schedule event to cleanup

    The implementation uses a state machine with the following states:

    ExecutionState.INITIALIZED = Before before_transform middlewares finished
    ExecutionState.RUNNING = After before_transform middlewares finished before main task started
    ExecutionState.FINISHED = After main task started before after_transform middlewares are finished
    ExecutionState.COMPLETED = After after_transform middlewares finished
    ExecutionState.FAILED = Transform Run failed due to unexpected error/exception
    ExecutionState.CANCELED = Transform Run canceled before it could finish
    """

    def __init__(
        self,
        run_id: str,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        transform_settings: Dict[str, MaltegoSettingTypes],
        context: MaltegoContext,
        limit: int,
        transform_execution_timeout: int,
        middleware_execution_timeout: int,
        middlewares: Optional[List[TransformMiddleware]] = None,
    ):
        """_summary_

        :param run_id: uuid to identify the transform execution.
        :type run_id: str
        :param transform: Transform that needs to be executed
        :type transform: MaltegoTransform
        :param input: Input entity to transform run
        :type input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph]
        :param transform_settings: Settings sent by the client to execute the transform
        :type transform_settings: Dict[str, TransformSetting]
        :param context: MaltegoContext that gets exposed to the transform.
        :type context: MaltegoContext
        :param limit: Number of entities that should be returned max.
        :type limit: int
        :param middlewares: _description_, List of middlewares used in the before and after transform hooks
        :type middlewares: Optional[List[TransformMiddleware]], optional
        """
        self.run_id = run_id
        self.transform_settings = transform_settings
        self.transform = transform
        self.input = transform_input
        self.limit = limit
        self.transform_execution_timeout = transform_execution_timeout
        self.middleware_execution_timeout = middleware_execution_timeout
        self.result = TransformResultSet(context)
        self.middlewares = middlewares or []
        self.before_transform_task: Optional[asyncio.Task[None]] = None
        self.after_transform_task: Optional[asyncio.Task[None]] = None
        self.task: Optional[asyncio.Task[None]] = None
        self.transform_observer = TransformGraphObserver(
            self.result.output_queue,
            self.run_id,
            context.graph,
            transform.composite_entities,
        )
        self.input_queue: asyncio.Queue[TransformRunExecutionInput] = asyncio.Queue()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = Lock()
        self._outcome = ExecutionState.FINISHED
        self._stop_requested = False
        self._active_task: Optional[asyncio.Task] = None
        self._timeout_exception: Optional[MaltegoTransformTimeoutError] = None
        self._timeout_requested = False
        self.start_time = None
        self.end_time = None
        context.set_input_queue(self.input_queue)

    def __str__(self) -> str:
        return f"TransformExecutionContext[{self.transform.name}: {self.result}]"

    def __repr__(self) -> str:
        return self.__str__()

    def v3_request(self) -> bool:
        return self.result.context.v3_request

    async def start(self) -> None:
        """Starts the transform run by putting the first state into the state machine
        """
        await self.run()

    def start_sync(self) -> None:
        """Starts the transform run by putting the first state into the state machine
        """
        asyncio.create_task(self.run())

    def done(self) -> bool:
        """Checks whether the transform execution has finished

        :return: True if transform is finished or has failed
        :rtype: bool
        """
        if self.result.state in TERMINAL_STATES:
            return True
        return False

    def cancel(self) -> None:
        """Request cancellation without interrupting the orchestration task."""
        self.__request_stop(ExecutionState.CANCELED)

    def expire(self, exception: MaltegoTransformTimeoutError) -> None:
        """Request an inactivity timeout on the owning execution loop."""
        self.__request_stop(ExecutionState.TIMED_OUT, exception)

    def __request_stop(
        self, outcome: ExecutionState, exception: Optional[MaltegoTransformTimeoutError] = None
    ) -> None:
        with self._lock:
            if self.result.state in TERMINAL_STATES:
                return
            if OUTCOME_PRECEDENCE[outcome] > OUTCOME_PRECEDENCE[self._outcome]:
                self._outcome = outcome
            if exception is not None and not self._timeout_requested:
                self._timeout_exception = exception
                self._timeout_requested = True
            first_request = not self._stop_requested
            self._stop_requested = True
            task, loop = self._active_task, self.loop
        if first_request and task is not None and loop is not None:
            loop.call_soon_threadsafe(task.cancel)

    def __record_timeout_locked(self) -> None:
        if self._timeout_exception is not None:
            self.result.push_exception(self._timeout_exception, state=ExecutionState.TIMED_OUT)
            self._timeout_exception = None

    def __record_timeout(self) -> None:
        with self._lock:
            self.__record_timeout_locked()

    @staticmethod
    async def __wait_for_phase(task: asyncio.Task, timeout: float) -> None:
        # Keep wait_for's timeout cleanup alive if its caller is cancelled
        # (notably on Python 3.11). The producer must finish before finality.
        waiter = asyncio.create_task(asyncio.wait_for(task, timeout))
        try:
            await asyncio.shield(waiter)
        except asyncio.CancelledError:
            if not task.cancelling():
                task.cancel()
            while not waiter.done() or not task.done():
                try:
                    await asyncio.wait({waiter, task})
                except asyncio.CancelledError:
                    continue
            if waiter.cancelled() and not task.cancelled():
                error = task.exception()
                if error is not None:
                    raise error
            waiter.result()
            raise

    def __handle_task_exception(self, exception: BaseException, state: ExecutionState = ExecutionState.FAILED) -> None:
        """Record an outcome without publishing a terminal result during cleanup."""
        try:
            raise exception
        except asyncio.InvalidStateError as ex:
            raise ex  # Task not finished yet. Since we are awaiting this shouldn't be possible
        except asyncio.CancelledError:  # Task was manually canceled. Not implemented right now
            state = ExecutionState.CANCELED
        except MaltegoWarning as warning:
            self.result.context.log.partial(warning.message)
            self.result.code = warning.classic_status_code
        except MaltegoException as ex:
            # Client errors (bad input, not found, unauthorized) are expected user-facing outcomes.
            log_fn = log.warning if isinstance(ex, MaltegoHTTPClientError) else log.error
            log_fn(f"Transform threw {type(ex).__name__}: {ex.message}")
            self.result.push_exception(ex, state=state)
            if isinstance(ex, MaltegoHTTPServerError):
                self.result.code = ex.status_code
        except Exception:  # pylint: disable=broad-except # Since Middlewares/Transforms can trow arbitrary exceptions
            log.exception(
                "Caught unknown internal error while running Transform.", exc_info=True)
            trace_id = self.result.context.trace_context.trace_id if self.result.context.trace_context else None
            message = (
                f"Unexpected exception while executing transform {self.transform.display_name} "
                f"for input entity '{self.input}'. "
            )
            if trace_id:
                message += f" Error ID: {trace_id}"
            new_e = MaltegoException(message=message, code=500)
            self.result.push_exception(new_e, state=state)
        with self._lock:
            if OUTCOME_PRECEDENCE[state] > OUTCOME_PRECEDENCE[self._outcome]:
                self._outcome = state

    async def run(self) -> None:
        """Run each phase and publish the outcome only after cleanup finishes."""
        self.loop = asyncio.get_running_loop()
        self.result.set_start_time()
        try:
            with self._lock:
                if not self._stop_requested:
                    self.before_transform_task = asyncio.create_task(self.__before_transform())
                    self._active_task = self.before_transform_task
            if self.before_transform_task is not None:
                await self.before_transform_task
            with self._lock:
                self._active_task = None
                if not self._stop_requested and self.result.state == ExecutionState.RUNNING:
                    self.task = asyncio.create_task(self.__transform())
                    self._active_task = self.task
            if self.task is not None:
                try:
                    await self.__wait_for_phase(self.task, self.transform_execution_timeout)
                except TimeoutError:
                    raise MaltegoTransformTimeoutError(
                        f"Timeout after {self.transform_execution_timeout}s "
                        f"reached while executing {self.transform.name}"
                    )
        except MaltegoTransformTimeoutError as e:
            self.__handle_task_exception(e, ExecutionState.TIMED_OUT)
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as e:  # pylint: disable=broad-except
            self.__handle_task_exception(e)
        finally:
            with self._lock:
                self._active_task = None

        self.__record_timeout()
        self.result.state = ExecutionState.FINISHED
        try:
            self.after_transform_task = asyncio.create_task(self.__after_transform())
            await self.after_transform_task
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as e:  # pylint: disable=broad-except
            self.__handle_task_exception(e)
        finally:
            with self._lock:
                self._active_task = None
                self.__record_timeout_locked()
                self.result.set_end_time()
                self.result.state = (
                    ExecutionState.COMPLETED if self._outcome == ExecutionState.FINISHED else self._outcome
                )
            log.info(
                f"Transform run {self.run_id} completed in {self.result.get_duration()} milliseconds, "
                f"with State {self.result.state}."
            )

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def receive_input(
        self,
        transform_input: TransformRunExecutionInput,
    ) -> None:
        if self.loop is None:
            raise RuntimeError(
                "Cannot parse transform prompt input. "
                f"No event loop associated with transform run {self}"
            )
        asyncio.run_coroutine_threadsafe(
            self.input_queue.put(transform_input), self.loop
        )

    async def __before_transform(self) -> None:
        """Wrapper task to run middlewares before the transform"""
        assert self.result.state == ExecutionState.INITIALIZED
        if self.transform.client_filter:
            state, message = self.transform.client_filter.match(
                user_agent=self.result.context.ua,
                headers=self.result.context.get_request_headers(),
            )
            if not state:
                raise MaltegoVersionNotSupported(
                    f"This transform does not support this version. " f"{message}"
                )
        if self.transform.input_constraint:
            constraint_result = self.transform.input_constraint.eval_with_hierarchy(
                self.input
            )

            if not constraint_result.success:
                # Format the hierarchical failure report
                failure_report = constraint_result.to_string()
                error_message = (
                    f"Transform '{self.transform.display_name}' rejected input. "
                    f"Multiple constraints failed:\n{failure_report}"
                )
                log.error(error_message)

                raise MaltegoHTTPInputEntityMalformed(f"Transform '{self.transform.display_name}' rejected input."
                                                      " Please try refreshing your hub, and contact"
                                                      " Maltego Support if this problem persists.")
        limit = self.limit or 12
        for middleware in self.middlewares:
            try:
                hook_task = asyncio.create_task(middleware.before_transform(
                    self.transform,
                    self.input,
                    self.transform_settings,
                    self.result.context,
                    limit,
                    limit,
                ))
                await self.__wait_for_phase(hook_task, self.middleware_execution_timeout)
            except TimeoutError:
                raise MaltegoException(
                    f"Timeout after {self.middleware_execution_timeout}s "
                    f" in middleware '{middleware.__class__.__name__}' "
                    f"for '{self.transform.name}'"
                )
        self.result.state = ExecutionState.RUNNING

    async def __transform(self) -> None:
        """Wrapper task to run the actual transform"""
        assert self.result.state == ExecutionState.RUNNING
        if self.transform.annotation.uses_graph_payload():
            assert isinstance(self.input, (MaltegoEntity, MaltegoGraph, list))
        else:
            assert isinstance(self.input, MaltegoEntity)
        await self.transform(
            self.input,
            self.result.output_queue,
            self.transform_observer,
            self.transform_settings,
            self.result.context,
            self.limit,
        )
        self.result.state = ExecutionState.FINISHED
        return None

    async def __after_transform(self) -> None:
        """Run every eligible hook, retaining failures and each hook's timeout."""
        for middleware in self.middlewares:
            self.__record_timeout()
            with self._lock:
                outcome = self._outcome
                if outcome != ExecutionState.FINISHED and not middleware.call_on_failure:
                    continue
                hook_task = asyncio.create_task(middleware.after_transform(
                    self.transform,
                    self.input,
                    self.result.get_added_entities(),
                    self.result.context,
                    outcome,
                    exceptions=self.result.exceptions,
                ))
                self._active_task = hook_task
            try:
                await self.__wait_for_phase(hook_task, self.middleware_execution_timeout)
            except TimeoutError:
                self.__handle_task_exception(MaltegoException(
                    f"Timeout after {self.middleware_execution_timeout}s "
                    f"in middleware '{middleware.__class__.__name__}' "
                    f"for '{self.transform.name}'"
                ))
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException as e:  # pylint: disable=broad-except
                if asyncio.current_task().cancelling():
                    raise
                self.__handle_task_exception(e)
            finally:
                with self._lock:
                    if self._active_task is hook_task:
                        self._active_task = None

    def get_response_headers(self) -> dict[str, str]:
        return self.result.context.response_headers


class TransformGraphObserver(Observer):

    def __init__(self, output_queue: queue.Queue[TransformEvent], run_id: str, graph: Optional[MaltegoGraph] = None, composite_entities: Optional[bool] = False) -> None:
        self._output_queue = output_queue
        self.run_id = run_id
        self.graph = graph
        self.composite_entities = composite_entities

    def __str__(self) -> str:
        return f"TransformGraphObserver[{self.run_id}]"

    def __repr__(self) -> str:
        return self.__str__()

    def add(self, add_item: Observable) -> None:
        if isinstance(add_item, MaltegoEntity):
            if (add_item.is_composite() or add_item.is_composite_instance) and not self.composite_entities:
                # if the entity is composite but the transform does not declare composition support,
                # raise an exception and fail the transform
                raise MaltegoUnsupportedCapabilityError(capability=MaltegoCapability.COMPOSITE_ENTITIES.id)
            self._output_queue.put(TransformEntityEvent(add_item))
        elif isinstance(add_item, MaltegoLink):
            self._output_queue.put(TransformLinkEvent(add_item))
        else:
            raise TypeError(
                f"Type {type(add_item)} is not supported by the TransformObserver add notifier"
            )

    def update(self, update_item: Observable, updated_property_name: str, updated_property_value: Any) -> None:
        if isinstance(update_item, MaltegoEntity):
            self._output_queue.put(TransformEntityEvent(
                entity=update_item,
                updates={updated_property_name: updated_property_value},
                operation_type=TransformEventOperationType.UPDATE,
            ))

            # if the entity’s properties changed, re-scan entity-typed props
            if updated_property_name == "_properties" and self.graph is not None:
                # add any new children
                self.graph.process_entity_typed_properties(update_item)
        elif isinstance(update_item, MaltegoLink):
            self._output_queue.put(TransformLinkEvent(
                link=update_item,
                updates={updated_property_name: updated_property_value},
                operation_type=TransformEventOperationType.UPDATE,
            ))
        else:
            raise TypeError(
                f"Type {type(update_item)} is not supported by the TransformObserver update notifier"
            )

    def delete(self, delete_item: Observable) -> None:
        if isinstance(delete_item, MaltegoEntity):
            self._output_queue.put(TransformEntityEvent(
                entity=delete_item,
                operation_type=TransformEventOperationType.DELETE
            ))
        elif isinstance(delete_item, MaltegoLink):
            self._output_queue.put(TransformLinkEvent(
                link=delete_item,
                operation_type=TransformEventOperationType.DELETE
            ))
        else:
            raise TypeError(
                f"Type {type(delete_item)} is not supported by the TransformObserver delete notifier"
            )
