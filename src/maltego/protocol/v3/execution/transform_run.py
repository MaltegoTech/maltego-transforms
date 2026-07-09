# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List, Literal, Union, Any, Optional
from pydantic import Field as PydanticField
from fastapi_restful.api_model import APIModel

from maltego.protocol.v3.execution.ui_message import UiMessage
from maltego.protocol.v3.execution.link import TransformRunLink
from maltego.protocol.v3.execution.graph import TransformRunInputGraph
from maltego.protocol.v3.execution.metadata import Metadata
from maltego.protocol.v3.execution.entity import TransformRunEntity

StatusTypes = Literal[
    "INITIALIZED",
    "RUNNING",
    "COMPLETED",
    "FINISHED",
    "FAILED",
    "CANCELED",
    "PAUSED",
    "TIMED_OUT"
]


RunSourceTypes = Literal["SET", "MACHINE", "DIRECT"]


class TransformEventType(APIModel):
    event_type: Literal["ADD", "UPDATE", "DELETE"] = "ADD"

class TransformRunEntityEvent(TransformEventType):
    entity: TransformRunEntity
    input_type: Literal["ENTITY"] = "ENTITY"


class TransformRunLinkEvent(TransformEventType):
    link: TransformRunLink
    input_type: Literal["LINK"] = "LINK"


class StatusMessage(APIModel):
    type: Literal["INFO", "WARNING", "ERROR", "DEBUG"] = "INFO"
    state: StatusTypes
    text: str
    code: int
    progress: float


class ChoicePrompt(APIModel):
    id: str
    display_name: str


class DropdownChoicePromptControl(APIModel):
    control_type: Literal["DROPDOWN"] = "DROPDOWN"
    control_id: str
    label: Optional[str]
    options: list[ChoicePrompt]
    default_option_id: Optional[str]


class RadioChoicePromptControl(APIModel):
    control_type: Literal["RADIO"] = "RADIO"
    control_id: str
    label: Optional[str]
    options: list[ChoicePrompt]
    default_option_id: Optional[str]


class CheckboxChoicePromptControl(APIModel):
    control_type: Literal["CHECKBOX"] = "CHECKBOX"
    control_id: str
    label: Optional[str]
    options: list[ChoicePrompt]
    default_option_ids: Optional[list[str]]


class ButtonChoicePromptControl(APIModel):
    control_type: Literal["BUTTON"] = "BUTTON"
    control_id: str
    options: list[ChoicePrompt]
    default_option_id: Optional[str]


class TransformRunChoicePromptEvent(TransformEventType):
    input_type: Literal["CHOICE_PROMPT"] = "CHOICE_PROMPT"
    id: str
    message: str
    options: list[ChoicePrompt]
    default_option_id: Optional[str]
    timeout: Optional[int]
    control: Optional[Union[
        DropdownChoicePromptControl,
        RadioChoicePromptControl,
        CheckboxChoicePromptControl,
        ButtonChoicePromptControl
    ]]


class TransformRunMultiChoicePromptEvent(TransformEventType):
    input_type: Literal["MULTI_CHOICE_PROMPT"] = "MULTI_CHOICE_PROMPT"
    id: str
    message: str
    controls: list[Union[
        DropdownChoicePromptControl,
        RadioChoicePromptControl,
        CheckboxChoicePromptControl,
    ]]
    timeout: Optional[int]


class InputPrompt(APIModel):
    id: str
    type: Any
    default_value: Optional[Any]
    display_name: str


class TransformRunInputPromptEvent(TransformEventType):
    input_type: Literal["INPUT_PROMPT"] = "INPUT_PROMPT"
    id: str
    message: str
    inputs: list[InputPrompt]
    timeout: Optional[int]


class TransformRunStatusMessageEvent(TransformEventType):
    status_message: StatusMessage
    input_type: Literal["STATUS_MESSAGE"] = "STATUS_MESSAGE"


class TransformRunEvent(APIModel):
    timestamp: str
    data: Union[
        TransformRunEntityEvent,
        TransformRunLinkEvent,
        TransformRunStatusMessageEvent,
        TransformRunInputPromptEvent,
        TransformRunChoicePromptEvent,
        TransformRunMultiChoicePromptEvent
    ] = PydanticField(
        discriminator='input_type'
    )


class TransformRunStatus(APIModel):
    ui_messages: List[UiMessage]
    code: int = 200


class TransformRunResult(APIModel):
    event_pointer: int = 0
    event_count: int = 0
    atomic_entity_count: int = 0
    composite_entity_count: int = 0
    incomplete_composite_entity: bool = False
    events: List[TransformRunEvent]
    run_id: str
    state: StatusTypes
    start_time: str
    update_time: str


class TransformRunResponse(APIModel):
    result: TransformRunResult
    status: TransformRunStatus


class TransformSetting(APIModel):
    name: str
    value: Any


class TransformRunExecutionContext(APIModel):
    graph_id: Optional[str]
    run_source: Optional[RunSourceTypes]
    source_name: Optional[str]


class TransformRunInput(APIModel):
    metadata: Metadata
    graph: TransformRunInputGraph


class TransformRunRequest(APIModel):
    input: TransformRunInput
    transformSettings: List[TransformSetting]
    limit: int = 12
    transformRunExecutionContext: Optional[TransformRunExecutionContext] = None


class SummaryItem(APIModel):
    added: dict[str, int]


class TransformRunResultSummary(APIModel):
    entities: SummaryItem
    run_id: str
    state: StatusTypes
    duration: int
    atomic_entity_count: int = 0
    composite_entity_count: int = 0


class TransformRunPromptResponse(APIModel):
    reason: Literal["TIMED_OUT", "CANCELLED", "COMPLETED"]
    result: dict[str, Any]
