# Copyright (c) Maltego Technologies GmbH.
import datetime
from typing import List, Union, Optional
from queue import Queue, Empty

from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.event import TransformEvent, TransformEventOperationType, TransformEntityEvent, \
    TransformMessageEvent, TransformLinkEvent
from maltego.model.exception import MaltegoException
from maltego.model.types import ExecutionState


TERMINAL_STATES = (ExecutionState.COMPLETED,
                   ExecutionState.CANCELED, ExecutionState.FAILED)


class TransformResultSet:

    """Representation of a transform result.
    Contains returned entities, exceptions and a status code
    """

    def __init__(self, context: MaltegoContext) -> None:
        self.__state = ExecutionState.INITIALIZED
        self.output: List[TransformEvent] = []
        self.output_queue: Queue[TransformEvent] = Queue()
        self.code: int = 200
        self.exception_stack: List[MaltegoException] = []
        self.start_time = datetime.datetime.now()
        self.end_time = None
        self.update_time = datetime.datetime.now()
        self.last_fetch_time = datetime.datetime.now()
        self.waiting_for_prompt_since: Optional[datetime.datetime] = None
        self.context = context
        self.context.set_log_queue(self.output_queue)
        self.context.set_result_set(self)

    def __str__(self) -> str:
        return f"{self.state}: {self.code}"

    def __repr__(self) -> str:
        return self.__str__()

    def __update(self) -> None:
        self.update_time = datetime.datetime.now()

    def get_added_entities(self) -> List[MaltegoEntity]:
        result: List[MaltegoEntity] = []
        self.__gather()
        for elem in self.output:
            if elem.operation_type == TransformEventOperationType.ADD and isinstance(elem, TransformEntityEvent):
                result.append(elem.entity)
        return result

    def __gather(self) -> None:
        while True:
            event = None
            try:
                event = self.output_queue.get_nowait()
            except Empty:
                break
            if event.is_update() and len(self.output) > 0:
                last_event_id = self.output[-1].get_id()
                next_event_id = event.get_id()
                if last_event_id == next_event_id:
                    self._merge_update_event(self.output[-1], event)
                    continue
            self.output.append(event)

    def _merge_update_event(
            self,
            curr_event: TransformEvent,
            next_event: TransformEvent
    ) -> None:
        assert isinstance(
            curr_event, (TransformEntityEvent, TransformLinkEvent))
        assert isinstance(
            next_event, (TransformEntityEvent, TransformLinkEvent))
        if curr_event.updates is not None and '_properties' in curr_event.updates and \
                next_event.updates is not None and '_properties' in next_event.updates:
            self.merge_property_updates(curr_event, next_event)
        elif curr_event.updates is not None and next_event.updates is not None:
            curr_event.updates.update(next_event.updates)

    @staticmethod
    def merge_property_updates(
            curr_event: Union[TransformEntityEvent, TransformLinkEvent],
            next_event: Union[TransformEntityEvent, TransformLinkEvent]
    ) -> None:

        if curr_event.updates is None:
            raise ValueError(
                f'Updated properties are not set for update event {curr_event.get_id()}')

        if next_event.updates is None:
            raise ValueError(
                f'Updated properties are not set for update event {next_event.get_id()}')

        assert len(next_event.updates) == 1
        updated_property = next_event.updates['_properties'][0]
        update_to_existing_property = False
        for existing_property in curr_event.updates['_properties']:
            if existing_property.name == updated_property.name:
                existing_property.value = updated_property.value
                update_to_existing_property = True
                break
        if not update_to_existing_property:
            curr_event.updates['_properties'].extend(
                next_event.updates['_properties'])

    def push_exception(self, exception: MaltegoException) -> None:
        self.__update()
        self.exception_stack.append(exception)
        self.output.append(TransformMessageEvent(log_tuple=(
            "FatalError", str(exception.message)), state=self.state.value))

    def pop_exception(self) -> MaltegoException:
        return self.exception_stack.pop(-1)

    def get_results(self) -> List[TransformEvent]:
        self.last_fetch_time = datetime.datetime.now()
        self.__gather()
        return self.output

    @property
    def exceptions(self) -> List[MaltegoException]:
        return self.exception_stack

    @property
    def event_count(self) -> int:
        self.__gather()
        return len(self.output) if self.output else 0

    @property
    def atomic_entity_count(self) -> int:
        """Number of top-level *atomic* entity ADD events in the output.

        An atomic entity is a ``TransformEntityEvent`` with ``operation_type ==
        ADD`` that is neither a composite child nor a composite instance.
        Composite children, links, messages and UPDATE/DELETE events are
        excluded.
        """
        self.__gather()
        return sum(
            1
            for event in self.output
            if isinstance(event, TransformEntityEvent)
            and event.operation_type == TransformEventOperationType.ADD
            and not event.entity._is_composite_child()  # pylint: disable=protected-access
            and not event.entity.is_composite_instance
        )

    @property
    def composite_entity_count(self) -> int:
        """Number of top-level *composite* entity ADD events in the output.

        A composite entity is a ``TransformEntityEvent`` with ``operation_type
        == ADD`` that is not a composite child but is a composite instance (it
        carries at least one entity-typed property). Composite children, links,
        messages and UPDATE/DELETE events are excluded.
        """
        self.__gather()
        return sum(
            1
            for event in self.output
            if isinstance(event, TransformEntityEvent)
            and event.operation_type == TransformEventOperationType.ADD
            and not event.entity._is_composite_child()  # pylint: disable=protected-access
            and event.entity.is_composite_instance
        )

    def _continues_composite(self, event: TransformEvent) -> bool:
        """Whether ``event`` *continues* an in-progress composite group.

        True iff ``event`` is a composite-child entity ADD or a composite link
        ADD (a link with ``_is_composite()`` True). A composite parent ADD does
        NOT continue a group -- it *starts* one. Atomic entities, ordinary
        (non-composite) links, messages and UPDATE/DELETE events are all False.
        """
        if isinstance(event, TransformEntityEvent):
            return (
                event.operation_type == TransformEventOperationType.ADD
                and event.entity._is_composite_child()  # pylint: disable=protected-access
            )
        if isinstance(event, TransformLinkEvent):
            return (
                event.operation_type == TransformEventOperationType.ADD
                and event.link._is_composite()  # pylint: disable=protected-access
            )
        return False

    def ends_mid_composite(self, boundary_index: int) -> bool:
        """Return True if the output is cut mid-composite at ``boundary_index``.

        ``boundary_index`` is the index of the first event the client has *not*
        yet seen -- ``event_pointer + event_limit`` for a results page, or the
        client's high-water fetch mark for a cancel/DELETE summary.

        Single forward rule: True iff that first un-returned event
        (``output[boundary_index]``) *continues* an in-progress composite group
        -- a composite child or composite link, never a parent (a parent starts
        a new group). At or after the end of the output there is no next event,
        so it returns False (the client has drained everything emitted so far).
        """
        self.__gather()
        if boundary_index <= 0 or boundary_index >= len(self.output):
            return False
        return self._continues_composite(self.output[boundary_index])

    @property
    def state(self) -> ExecutionState:
        return self.__state

    @state.setter
    def state(self, state: ExecutionState) -> None:
        self.__update()
        self.__state = state

    def set_start_time(self):
        if self.start_time is None:
            self.start_time = datetime.datetime.now()

    def set_end_time(self):
        if self.end_time is None:
            self.end_time = datetime.datetime.now()

    def mark_waiting_for_prompt(self) -> None:
        """Mark that this execution is waiting for user prompt response"""
        self.waiting_for_prompt_since = datetime.datetime.now()

    def clear_waiting_for_prompt(self) -> None:
        """Clear the waiting for prompt flag when response is received"""
        self.waiting_for_prompt_since = None

    def is_waiting_for_prompt(self) -> bool:
        """Check if currently waiting for user prompt response"""
        return self.waiting_for_prompt_since is not None

    def get_duration(self) -> int:
        """
        Calculates the duration of the transform execution in milliseconds.
        Returns 0 if start_time or end_time is not set.

        :return: Duration in milliseconds or 0 if not available.
        """
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            return int(duration.total_seconds() * 1000)
        return 0

    def get_current_duration(self) -> int:
        """
        Calculates the duration from start_time to now (or end_time if set) in milliseconds.
        Returns 0 if start_time is not set.
        """
        if self.start_time:
            end = self.end_time or datetime.datetime.now()
            duration = end - self.start_time
            return int(duration.total_seconds() * 1000)
        return 0
