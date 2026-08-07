# Copyright (c) Maltego Technologies GmbH.
import datetime
import logging
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import local, Event
from typing import Any, Dict, List, Optional, Union, Iterable

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.exception import MaltegoException, MaltegoTransformTimeoutError
from maltego.model.graph import MaltegoGraph
from maltego.model.prompt import TransformPromptResponse
from maltego.model.transform import MaltegoTransform, TransformRunExecutionInput
from maltego.model.types import ExecutionState, MaltegoSettingTypes
from maltego.protocol.v3.execution.transform_run import TransformRunExecutionContext
from maltego.runner.transform_execution_context import (
    MultiplexedTransformResultSet,
    TransformExecutionContext,
    MultiplexedTransformExecutionContext
)
from maltego.runner.transform_result_set import TransformResultSet

log = logging.getLogger(__name__)
RETENTION_TIME = 60


class TransformRunner:
    middlewares: List[TransformMiddleware]
    __transform_queue: Dict[
        str,
        Union[TransformExecutionContext, MultiplexedTransformExecutionContext]
    ]

    retention_time: int

    def __init__(
        self,
        middlewares: List[TransformMiddleware],
        transform_execution_timeout: int,
        middleware_execution_timeout: int,
        retention_time: Optional[int] = RETENTION_TIME,
    ) -> None:
        self.middlewares = middlewares
        self.transform_execution_timeout = transform_execution_timeout
        self.middleware_execution_timeout = middleware_execution_timeout
        self.__transform_queue = {}
        self.started = False
        self.retention_time = retention_time

    def __add(
        self,
        context: Union[TransformExecutionContext,
                       MultiplexedTransformExecutionContext]
    ) -> str:
        run_id = context.run_id
        if run_id in self.__transform_queue:
            raise RuntimeError(f"Transform with id {run_id} already exists")
        self.__transform_queue[run_id] = context
        return run_id

    def __get(self, run_id: str) -> Union[TransformExecutionContext, MultiplexedTransformExecutionContext]:
        return self.__transform_queue[run_id]

    def __delete(self, run_id: str) -> Union[TransformExecutionContext, MultiplexedTransformExecutionContext]:
        if run_id not in self.__transform_queue:
            raise KeyError(f"Cannot find transform execution with id {run_id}")
        return self.__transform_queue.pop(run_id)

    def __try_delete(self, run_id: str) -> None:
        self.__transform_queue.pop(run_id, None)

    def schedule_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        transform_settings: Dict[str, MaltegoSettingTypes],
        limit: int,
        context: MaltegoContext
    ) -> str:
        """Schedules a transform to run and returns the transforms run_id as a reference

        :param transform: Transform function to run
        :type transform: MaltegoTransform
        :param transform_input: Input entity for the transform
        :type transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph]
        :param transform_settings: Transforms input settings
        :type transform_settings: Dict[str, TransformSetting]
        :param limit: Returned entities limit
        :type limit: int
        :return: uuid4 used to reference the transform
        :rtype: str
        """
        run_id = str(uuid.uuid4())
        execution_context = TransformExecutionContext(
            run_id,
            transform,
            transform_input,
            transform_settings,
            context,
            limit,
            self.transform_execution_timeout,
            self.middleware_execution_timeout,
            self.middlewares
        )
        return self.__add(execution_context)

    def schedule_transform_list_in(
        self,
        transform: MaltegoTransform,
        transform_inputs: Iterable[Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]]],
        transform_settings: Dict[str, MaltegoSettingTypes],
        limit: int,
        context: MaltegoContext
    ) -> str:
        run_id = str(uuid.uuid4())
        execution_context = MultiplexedTransformExecutionContext(
            run_id,
            transform,
            transform_inputs,
            transform_settings,
            context,
            limit,
            self.transform_execution_timeout,
            self.middleware_execution_timeout,
            self.middlewares
        )
        return self.__add(execution_context)

    def get_execution_context(
        self,
        run_id: str
    ) -> Union[TransformExecutionContext, MultiplexedTransformExecutionContext]:
        return self.__get(run_id)

    def cleanup(self) -> None:
        run_ids = list(self.__transform_queue.keys())
        if len(run_ids) > 0:
            log.info(
                f"{len(run_ids)} executions in queue. Cleanup runs older than {self.retention_time}s"
            )
        else:
            log.debug("No pending Runs in queue. Nothing to clean up")

        now = datetime.datetime.now()
        delta = now - datetime.timedelta(seconds=self.retention_time)

        for run_id in run_ids:
            execution_context = self.__transform_queue.get(run_id)
            if execution_context is not None:
                if not execution_context.v3_request():
                    continue

                update_time = execution_context.result.update_time
                last_fetch_time = execution_context.result.last_fetch_time

                # Skip inactivity timeout if waiting for prompt response
                if execution_context.result.is_waiting_for_prompt():
                    log.debug(
                        f"Execution context {run_id} is waiting for prompt response, skipping inactivity check."
                    )
                    continue

                if update_time < delta and last_fetch_time < delta:
                    if execution_context.result.state == ExecutionState.TIMED_OUT:
                        log.info(
                            f"Execution context with id {run_id} has been timed out previously. Removing..."
                        )
                        self.__try_delete(run_id)
                    else:
                        log.info(
                            f"Execution context with id {run_id} is older than {self.retention_time}s. "
                            f"Marking as timed out."
                        )
                        execution_context.result.state = ExecutionState.TIMED_OUT
                        execution_context.result.push_exception(
                            MaltegoTransformTimeoutError(
                                f"Transform execution timed out after being inactive for {self.retention_time}s.",
                                code=410
                            )
                        )
                        execution_context.result.update_time = now

    def done(self, run_id: str) -> bool:
        """Indicates whether a transform execution is finished

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: True if transform has finished executing. False else
        :rtype: bool
        """
        execution_context = self.__get(run_id)
        return execution_context.done()

    def cancel(self, run_id: str) -> None:
        """Cancel a transform run

        :param run_id: UUID of the transform run
        :type run_id: str
        """
        execution_context = self.__get(run_id)
        execution_context.cancel()

    def delete(self, run_id: str) -> None:
        """Delete a transform run context

        :param run_id: UUID of the transform run
        :type run_id: str
        """
        self.__delete(run_id)

    def result(
        self,
        run_id: str
    ) -> Union[TransformResultSet, MultiplexedTransformResultSet]:
        """Returns TransformResultSet object for a given execution ID
        that includes all relevant results, codes and exceptions

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Returns a object containing transform results, exceptions and status code
        :rtype: TransformResultSet
        """
        execution_context = self.__get(run_id)
        return execution_context.result

    def output_entities(self, run_id: str) -> List[MaltegoEntity]:
        """Returns the results entities of a transform execution
        or an empty list if not results are available yet

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: List of returned entities
        :rtype: int
        """
        execution_context = self.__get(run_id)
        return execution_context.result.get_added_entities()

    def transform_run_execution_context(self, run_id: str) -> TransformRunExecutionContext:
        """Returns the transform run execution context of a transform execution

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Transform run execution context
        :rtype: TransformRunExecutionContext
        """
        execution_context = self.__get(run_id)
        if isinstance(execution_context, MultiplexedTransformExecutionContext):
            if len(execution_context.contexts) == 0:
                transform_run_execution_context = None
            else:
                # all multiplexed contexts should have the same transform run execution
                # context as they are all the same graph and transform
                transform_run_execution_context = execution_context.contexts[
                    0].result.context.transform_run_execution_context
        else:
            transform_run_execution_context = execution_context.result.context.transform_run_execution_context
        return transform_run_execution_context

    def exceptions(self, run_id: str) -> List[MaltegoException]:
        """Returns a chronologically ordered list of all exception
        that where raised by the transform or middlewares

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: List of chronologically ordered exceptions. (Raise order)
        :rtype: int
        """
        execution_context = self.__get(run_id)
        return execution_context.result.exceptions

    def status_code(self, run_id: str) -> int:
        """Returns the status code of the transforms execution

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Transform execution last status code
        :rtype: int
        """
        execution_context = self.__get(run_id)
        return execution_context.result.code

    async def prompt_response(
            self,
            run_id: str,
            prompt_id: str,
            transform_prompt_response: TransformPromptResponse
    ) -> None:
        """Handle transform input

        :param run_id: UUID of the transform run
        :type run_id: str
        :param transform_prompt_response: User selected results for the displayed prompt
        :type transform_prompt_response: TransformPromptResponse
        """
        execution_context = self.__get(run_id)
        await execution_context.receive_input(TransformRunExecutionInput(prompt_id, transform_prompt_response))

    def response_headers(self, run_id: str) -> dict[str, str]:
        """Get the response headers set in the transform

        :param run_id: UUID of the transform run
        :type run_id: str
        :raises ValueError: If any of the header values are not of string type
        """
        execution_context = self.__get(run_id)
        response_headers = execution_context.get_response_headers()
        for key, value in response_headers.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Response header '{key}' has a value of type {type(value).__name__}, "
                    f"expected type 'str' for value {value}"
                )
        return response_headers

    async def run(
        self,
        run_id: str
    ) -> TransformResultSet:
        """Runs a transform until it is completed.

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Returns a list of result entities,
        :rtype: Tuple[List[MaltegoEntity], List[MaltegoException], int]
        """
        raise NotImplementedError()

    def start_transform(self, run_id: str) -> None:
        raise NotImplementedError()

    def startup(self) -> None:
        raise NotImplementedError()

    def shutdown(self) -> None:
        raise NotImplementedError()


class AsyncTransformRunner(TransformRunner):

    async def run(
        self,
        run_id: str
    ) -> TransformResultSet:
        """Runs a transform until it is completed.

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Returns a list of result entities,
        :rtype: Tuple[List[MaltegoEntity], List[MaltegoException], int]
        """
        execution_context = self.get_execution_context(run_id)
        if isinstance(execution_context, MultiplexedTransformExecutionContext):
            raise RuntimeError(
                "Calls to run only supported for non multiplexed v2 transforms"
            )
        await execution_context.run()
        assert execution_context.result is not None
        return execution_context.result

    def start_transform(self, run_id: str) -> None:
        execution_context = self.get_execution_context(run_id)
        execution_context.set_event_loop(asyncio.get_running_loop())
        execution_context.start_sync()

    def startup(self) -> None:
        return

    def shutdown(self) -> None:
        return


class ThreadedTransformRunner(TransformRunner):

    _CANCELLATION_DRAIN_TIMEOUT_SECONDS = 2.0
    _CANCELLATION_RETRY_AFTER_SECONDS = 1.0
    _CANCELLATION_DRAIN_POLL_SECONDS = 0.1

    def __init__(
        self,
        middlewares: List[TransformMiddleware],
        transform_execution_timeout: int,
        middleware_execution_timeout: int,
    ) -> None:
        super().__init__(middlewares, transform_execution_timeout, middleware_execution_timeout)
        self.worker = 1
        self.data = local()
        self.data.loop = None
        self.loops: List[asyncio.AbstractEventLoop] = []
        self.executor: Optional[ThreadPoolExecutor] = None
        self.current_loop = 0

    def get_next_loop(self) -> asyncio.AbstractEventLoop:
        if not self.executor:
            raise RuntimeError(
                "ThreadPoolExecutor not started. Cannot run transforms")
        loop = self.loops[self.current_loop]
        self.current_loop += 1
        if self.current_loop >= len(self.loops):
            self.current_loop = 0
        return loop

    @staticmethod
    def _consume_task_outcomes(tasks: set[asyncio.Task]) -> None:
        """Mark completed task failures as observed during loop teardown."""
        for task in tasks:
            if task.done() and not task.cancelled():
                task.exception()

    @staticmethod
    def _pending_worker_tasks(
        loop: asyncio.AbstractEventLoop,
        current_task: Optional[asyncio.Task],
    ) -> set[asyncio.Task]:
        return {
            task for task in asyncio.all_tasks(loop=loop) if task is not current_task
        }

    async def _drain_cancelled_tasks(self, loop: asyncio.AbstractEventLoop) -> None:
        """Cancel worker tasks until the loop is quiet or a deadline expires.

        The coroutine running this cleanup is deliberately excluded: cancelling
        it would interrupt the very shutdown process responsible for closing the
        worker loop.
        """
        current_task = asyncio.current_task()
        started_at = loop.time()
        deadline = started_at + self._CANCELLATION_DRAIN_TIMEOUT_SECONDS
        retry_at = started_at + self._CANCELLATION_RETRY_AFTER_SECONDS
        cancellation_requested: set[asyncio.Task] = set()
        retry_requested = False

        while True:
            pending_tasks = self._pending_worker_tasks(loop, current_task)
            if not pending_tasks:
                return

            remaining_time = deadline - loop.time()
            if remaining_time <= 0:
                break

            retry_tasks = pending_tasks & cancellation_requested
            newly_pending_tasks = pending_tasks - cancellation_requested
            for task in newly_pending_tasks:
                task.cancel()
            cancellation_requested.update(newly_pending_tasks)

            if not retry_requested and loop.time() >= retry_at:
                for task in retry_tasks:
                    task.cancel()
                retry_requested = True

            completed_tasks, _ = await asyncio.wait(
                pending_tasks,
                timeout=min(
                    self._CANCELLATION_DRAIN_POLL_SECONDS,
                    remaining_time,
                ),
            )
            self._consume_task_outcomes(completed_tasks)

        pending_tasks = self._pending_worker_tasks(loop, current_task)
        if pending_tasks:
            log.error(
                "Closing transform runner loop with %d task(s) still pending after cancellation deadline.",
                len(pending_tasks),
            )

    def __thread(self, startup_event: Event) -> None:
        loop = asyncio.new_event_loop()
        self.data.loop = loop
        self.loops.append(loop)
        asyncio.set_event_loop(loop)
        try:
            startup_event.set()
            loop.run_forever()
        except asyncio.CancelledError as e:
            log.error(f'Event Loop canceled {e}')
        finally:
            loop.run_until_complete(self._drain_cancelled_tasks(loop))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def run(
        self,
        run_id: str
    ) -> TransformResultSet:
        """Runs a transform until it is completed.

        :param run_id: UUID of the transform run
        :type run_id: str
        :return: Returns a list of result entities,
        :rtype: Tuple[List[MaltegoEntity], List[MaltegoException], int]
        """
        execution_context = self.get_execution_context(run_id)
        if isinstance(execution_context, MultiplexedTransformExecutionContext):
            raise RuntimeError(
                "Calls to run only supported for non multiplexed v2 transforms"
            )
        executor_loop = self.get_next_loop()
        future = asyncio.run_coroutine_threadsafe(
            execution_context.run(), executor_loop)
        # asyncio.run_coroutine_threadsafe Returns a non-async future object that needs to be wrapped to be awaitable
        # The wrapped loop param needs to be the awaiting loop, while the upper loops is the executing threads loop
        await asyncio.wrap_future(future, loop=asyncio.get_running_loop())
        assert execution_context.result is not None
        return execution_context.result

    def start_transform(self, run_id: str) -> None:
        execution_context = self.get_execution_context(run_id)
        loop = self.get_next_loop()
        execution_context.set_event_loop(loop)
        loop.call_soon_threadsafe(
            asyncio.ensure_future, execution_context.start())

    def set_worker(self, worker: int) -> None:
        self.worker = worker

    def startup(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=self.worker)
        assert self.executor is not None
        for _ in range(self.worker):
            startup_event = Event()
            res = self.executor.submit(self.__thread, startup_event)
            if startup_event.wait():
                log.info(f"Executor Thread started {res}")
            else:
                raise RuntimeError("Executor Thread could not be started")

        self.started = True

    def _close(self) -> None:
        loop: asyncio.AbstractEventLoop = self.data.loop
        loop.call_soon(loop.stop)

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        for loop in self.loops:
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._close)
        if self.executor is not None:
            self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            self.executor = None
        self.loops = []
        self.started = False
