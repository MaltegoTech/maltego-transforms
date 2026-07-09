# Copyright (c) Maltego Technologies GmbH.
import datetime
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Literal, Tuple, Optional, Union, Any, List, TypeGuard

from maltego.model.entity import MaltegoEntity
from maltego.model.link import MaltegoLink
from maltego.model.prompt import (
    InputPromptItem, PromptItem, DropdownControl,
    RadioControl, CheckboxControl, ButtonControl
)
from maltego.model.types import ExecutionState
from maltego.protocol.v3.execution.transform_run import (
    ChoicePrompt, InputPrompt, StatusMessage,
    StatusTypes, TransformRunChoicePromptEvent, TransformRunEntityEvent, TransformRunEvent,
    TransformRunInputPromptEvent, TransformRunLinkEvent, TransformRunStatusMessageEvent,
    TransformRunMultiChoicePromptEvent
)

INVALID_TIMEOUT_ERROR = "Invalid timeout value. If a timeout is provided, the value must be greater than 0"
INVALID_MESSAGE_ERROR = "Message Missing: Please provide a prompt message"
INVALID_CHOICE_OPTIONS_ERROR = (
    "Validation Error: Please make sure the list of prompt items is not empty and contains at least one value"
)


def is_input_prompt_item_list(val: List[Any]) -> TypeGuard[List[InputPromptItem]]:
    """Determines whether all objects in the list are strings"""
    return all(isinstance(x, InputPromptItem) for x in val)


class TransformEventOperationType(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class TransformEvent(ABC):

    def __init__(self, operation_type: TransformEventOperationType):
        self.operation_type = operation_type

    @abstractmethod
    def get_id(self) -> Union[str, Tuple[str, str]]:
        pass

    def is_update(self) -> bool:
        return isinstance(self,
                          (TransformEntityEvent, TransformLinkEvent)
                          ) and self.operation_type == TransformEventOperationType.UPDATE

    def to_v3_event(self) -> TransformRunEvent:
        raise TypeError(
            f'{self.__class__.__name__} is not a valid transform run event type'
        )


CONTEXT_LOG_LEVEL_TO_V3_STATUS_TYPE: Dict[str, Literal["INFO", "WARNING", "ERROR", "DEBUG"]] = {
    "Debug": "DEBUG",
    "Inform": "INFO",
    "FatalError": "ERROR",
    "PartialError": "WARNING"
}


class TransformMessageEvent(TransformEvent):

    def __init__(
        self,
        log_tuple: Tuple[str, str],
        operation_type: TransformEventOperationType = TransformEventOperationType.ADD,
        state: Optional[StatusTypes] = ExecutionState.INITIALIZED.value,
    ):
        super().__init__(operation_type)
        self.level = log_tuple[0]
        self.message = log_tuple[1]
        self.event_id = str(uuid.uuid4())
        self.state = state or ExecutionState.INITIALIZED.value

    def get_id(self) -> Union[str, Tuple[str, str]]:
        return self.event_id

    def to_v3_event(self) -> TransformRunEvent:
        return TransformRunEvent(
            timestamp=str(datetime.datetime.now()),
            data=TransformRunStatusMessageEvent(
                event_type="ADD",
                status_message=StatusMessage(
                    type=CONTEXT_LOG_LEVEL_TO_V3_STATUS_TYPE[self.level],
                    state=self.state,
                    text=self.message,
                    code=0,
                    progress=0
                )
            )
        )


class TransformEntityEvent(TransformEvent):

    def __init__(
            self,
            entity: MaltegoEntity,
            updates: Optional[dict[str, Any]] = None,
            operation_type: TransformEventOperationType = TransformEventOperationType.ADD,
    ):
        super().__init__(operation_type)
        self.entity = entity
        self.updates = updates

    def get_id(self) -> Union[str, Tuple[str, str]]:
        return self.entity.maltego_entity_id, self.operation_type.name

    def to_v3_event(self, composed_graph: Optional[bool] = False) -> TransformRunEvent:
        if self.operation_type == TransformEventOperationType.ADD:
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunEntityEvent(
                    event_type="ADD",
                    entity=self.entity.to_v3_run_entity(composed_graph),
                )
            )

        if self.operation_type == TransformEventOperationType.DELETE:
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunEntityEvent(
                    event_type="DELETE",
                    entity=self.entity.to_v3_run_entity_from_id(),
                )
            )

        if self.operation_type == TransformEventOperationType.UPDATE:
            assert self.updates is not None
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunEntityEvent(
                    event_type="UPDATE",
                    entity=self.entity.to_v3_run_entity_update(
                        updates=self.updates or {}, composed_graph=composed_graph),
                )
            )
        raise ValueError(
            f"Cannot convert Link with operation {self.operation_type} to TransformLinkEvent. Unknown operation type"
        )


class TransformLinkEvent(TransformEvent):

    def __init__(
            self,
            link: MaltegoLink,
            updates: Optional[dict[str, Any]] = None,
            operation_type: TransformEventOperationType = TransformEventOperationType.ADD,
    ):
        super().__init__(operation_type)
        self.link = link
        self.updates = updates

    def get_id(self) -> Union[str, Tuple[str, str]]:
        return self.link.maltego_link_id, self.operation_type.name

    def to_v3_event(self) -> TransformRunEvent:
        if self.operation_type == TransformEventOperationType.ADD:
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunLinkEvent(
                    event_type="ADD",
                    link=self.link.to_v3_run_link(),
                )
            )

        if self.operation_type == TransformEventOperationType.DELETE:
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunLinkEvent(
                    event_type="DELETE",
                    link=self.link.to_v3_run_link_from_id(),
                )
            )

        if self.operation_type == TransformEventOperationType.UPDATE:
            assert self.updates is None
            return TransformRunEvent(
                timestamp=str(datetime.datetime.now()),
                data=TransformRunLinkEvent(
                    event_type="UPDATE",
                    link=self.link.to_v3_run_link_update(self.updates),
                )
            )
        raise ValueError(
            f"Cannot convert Link with operation {self.operation_type} to TransformLinkEvent. Unknown operation type"
        )


class TransformPromptEvent(TransformEvent):

    def __init__(
            self,
            prompt_id: str,
            message: str,
            items: Union[list[PromptItem], list[InputPromptItem]],
            timeout: Optional[int],
    ):
        super().__init__(TransformEventOperationType.ADD)
        self.prompt_id = prompt_id
        if not message:
            raise ValueError(INVALID_MESSAGE_ERROR)
        self.message = message
        if not items:
            raise ValueError(INVALID_CHOICE_OPTIONS_ERROR)
        self.items = items
        if timeout is not None and timeout <= 0:
            raise ValueError(INVALID_TIMEOUT_ERROR)
        self.timeout = timeout

    def get_id(self) -> Union[str, Tuple[str, str]]:
        return self.prompt_id


class TransformChoicePromptEvent(TransformPromptEvent):

    def __init__(
            self,
            prompt_id: str,
            message: str,
            options: list[PromptItem],
            default_option_id: Optional[str],
            timeout: Optional[int],
            control: Optional[
                Union[
                    DropdownControl,
                    RadioControl,
                    CheckboxControl,
                    ButtonControl
                ]
            ] = None,
    ):
        super().__init__(prompt_id, message, options, timeout)
        self.default_option_id = default_option_id
        self.control = control

    def to_v3_event(self) -> TransformRunEvent:
        return TransformRunEvent(
            timestamp=str(datetime.datetime.now()),
            data=TransformRunChoicePromptEvent(
                id=str(self.prompt_id),
                message=self.message,
                options=[
                    ChoicePrompt(
                        id=i.item_id,
                        display_name=i.display_name
                    ) for i in self.items],
                default_option_id=self.default_option_id,
                timeout=self.timeout,
                control=self.control.to_v3_event() if self.control else None
            ),
        )


class TransformMultiChoicePromptEvent(TransformEvent):

    def __init__(
            self,
            prompt_id: str,
            message: str,
            controls: list[
                Union[
                    DropdownControl,
                    RadioControl,
                    CheckboxControl
                ]
            ],
            timeout: Optional[int]
    ):
        super().__init__(TransformEventOperationType.ADD)
        self.prompt_id = prompt_id
        self.message = message
        self.controls = controls
        self.timeout = timeout

    def get_id(self) -> Union[str, Tuple[str, str]]:
        return self.prompt_id

    def to_v3_event(self) -> TransformRunEvent:
        return TransformRunEvent(
            timestamp=str(datetime.datetime.now()),
            data=TransformRunMultiChoicePromptEvent(
                id=str(self.prompt_id),
                message=self.message,
                controls=[
                    control.to_v3_event() for control in self.controls if control is not None
                ],
                timeout=self.timeout
            )
        )


class TransformInputPromptEvent(TransformPromptEvent):

    def __init__(
            self,
            prompt_id: str,
            message: str,
            items: list[InputPromptItem],
            timeout: Optional[int]
    ):
        super().__init__(prompt_id, message, items, timeout)

    def to_v3_event(self) -> TransformRunEvent:
        assert is_input_prompt_item_list(self.items)
        return TransformRunEvent(
            timestamp=str(datetime.datetime.now()),
            data=TransformRunInputPromptEvent(
                id=str(self.prompt_id),
                message=self.message,
                inputs=[
                    InputPrompt(
                        id=item.item_id,
                        type=item.input_type,
                        default_value=item.default_value,
                        display_name=item.display_name
                    ) for item in self.items
                ],
                timeout=self.timeout
            )
        )
