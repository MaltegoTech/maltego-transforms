# Copyright (c) Maltego Technologies GmbH.
import functools
import uuid
from enum import Enum

import asyncio
import logging
from queue import Queue
from typing import Literal, Optional, Dict, Any, Tuple, List, Union, cast
from fastapi import Request

from maltego.model.event import (
    TransformMessageEvent, TransformChoicePromptEvent, TransformInputPromptEvent,
    TransformMultiChoicePromptEvent
)
from maltego.model.exception import (MaltegoPromptNotSupportedError, MaltegoTransformTimeoutError,
                                     MaltegoVersionNotSupported)
from maltego.model.graph import MaltegoGraph
from maltego.auth.identity import AuthContext, Identity
from maltego.model.prompt import (
    TransformPromptResponse, InputPromptItem, PromptItem,
    DropdownControl, RadioControl, CheckboxControl,
    ButtonControl
)
from maltego._helper import parse_ua
from maltego.protocol.v3.execution.transform_run import TransformRunExecutionContext

log = logging.getLogger(__name__)

# New User agent was introduced in Maltego 4.5.0 so we assume 4.5.0 for everything missing a parsable ua.
# This also means we cannot check for lower then 4.5.0
CLIENT_MINIMAL_VERSION = (4, 5, 0)
DEFAULT_PROMPT_TIMEOUT_SECONDS = 300
PROMPT_TIMEOUT_ERROR_BUFFER = 5


class MaltegoCapability(str, Enum):
    """All SDK capabilities. Used for capability toggling."""

    INPUT_CONSTRAINTS = ("inputConstraints", "Structured input-constraint transforms")
    COMPOSITE_ENTITIES = ("compositeEntities", "Full entity-typed structures")
    PROMPT_BASE = ("promptBase", "Enable using prompts in transforms")
    CHOICE_CONTROL_TYPE = ("choiceControlType", "Specify control types in prompts")
    MULTI_CHOICE_CONTROLS = ("multiChoiceControls", "Multiple controls per prompt")
    FLATTENED_COMPOSITE_ENTITIES = ("flattenedCompositeEntities", "Flattened composite entities")
    INPUT_CONSTRAINTS_UNKNOWN_SAFE = ("inputConstraintsUnknownSafe", "Client tolerates unknown input constraint types")

    def __new__(cls, value, description):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        return obj

    @property
    def id(self) -> str:
        return cast(str, self.value)


class MaltegoClientCapabilities:
    """Parsed and structured set of server capabilities a Maltego client supports, per request."""
    def __init__(self, capabilities: set[str], present: bool):
        self.capabilities = capabilities
        self.present = present

    def has(self, capability: MaltegoCapability) -> bool:
        return capability.id in self.capabilities


class ResolvedCapabilitiesSet:
    """
    A set of capabilities that have been resolved for a specific client.
    """
    def __init__(self, enabled: set[MaltegoCapability]):
        self._enabled = enabled

    def has(self, cap: MaltegoCapability) -> bool:
        return cap in self._enabled

    @functools.cached_property
    def ids(self) -> set[str]:
        return {f.id for f in self._enabled}

    @property
    def prompt_base(self) -> bool:
        return self.has(MaltegoCapability.PROMPT_BASE)

    @property
    def multi_choice_controls(self) -> bool:
        return self.has(MaltegoCapability.MULTI_CHOICE_CONTROLS)

    @property
    def choice_control_type(self) -> bool:
        return self.has(MaltegoCapability.CHOICE_CONTROL_TYPE)

    @property
    def composite_entities(self) -> bool:
        return self.has(MaltegoCapability.COMPOSITE_ENTITIES)

    @property
    def flattened_composite_entities(self) -> bool:
        return self.has(MaltegoCapability.FLATTENED_COMPOSITE_ENTITIES)


class NoInputQueueError(ValueError):
    def __init__(self, where: str, message: str = "Prompt input queue has not been set"):
        super().__init__(f"{message} in {where} prompt")


class NoOutputQueueError(ValueError):
    def __init__(self, where: str, message: str = "Prompt output queue has not been set"):
        super().__init__(f"{message} in {where} prompt")


def track_prompt_waiting(func):
    """Decorator to track when a prompt is waiting for user response.

    Marks the result set as waiting before the prompt and clears the flag
    after response is received or timeout occurs.
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        # Mark that we're waiting for prompt response
        if hasattr(self, "result_set") and self.result_set is not None:
            self.result_set.mark_waiting_for_prompt()

        try:
            return await func(self, *args, **kwargs)
        finally:
            # Clear waiting flag when response received or timeout
            if hasattr(self, "result_set") and self.result_set is not None:
                self.result_set.clear_waiting_for_prompt()

    return wrapper


class LogCollector:
    def __init__(self) -> None:
        self.log_queue: Optional[Queue[Any]] = None
        self.log_messages: List[Tuple[str, str]] = []

    def __emit(
        self,
        level: Literal["Inform", "FatalError", "Debug", "PartialError"],
        message: str
    ) -> None:
        try:
            message = str(message)
        except ValueError:
            raise ValueError(
                f"Cannot convert log input type {type(message)} to string")
        data = (level, message)
        self.log_messages.append(data)
        if self.log_queue is not None:
            self.log_queue.put(TransformMessageEvent(data))

    def set_log_queue(self, log_queue: Queue[Any]) -> None:
        self.log_queue = log_queue

    def inform(self, message: str) -> None:
        self.__emit("Inform", message)

    def fatal(self, message: str) -> None:
        self.__emit("FatalError", message)

    def debug(self, message: str) -> None:
        self.__emit("Debug", message)

    def partial(self, message: str) -> None:
        self.__emit("PartialError", message)


class Prompt:

    def __init__(self) -> None:
        self.output_queue: Optional[Queue[Any]] = None
        self.input_queue: Optional[asyncio.Queue[Any]] = None
        self.result_set: Optional[Any] = None

    def set_output_queue(self, output_queue: Queue[Any]) -> None:
        self.output_queue = output_queue

    def set_input_queue(self, input_queue: asyncio.Queue[Any]) -> None:
        self.input_queue = input_queue

    def set_result_set(self, result_set: Any) -> None:
        """Set reference to result set for prompt tracking"""
        self.result_set = result_set

    @track_prompt_waiting
    async def choice(
            self,
            message: str,
            options: list[PromptItem],
            default_option_id: Optional[str] = None,
            timeout: Optional[int] = None,
            control: Optional[
                Union[DropdownControl, RadioControl,
                      CheckboxControl, ButtonControl]
            ] = None,
    ) -> TransformPromptResponse:
        option_ids = [opt.item_id for opt in options]
        if control is not None and control.validate_default_options(option_ids) is False:
            raise ValueError(
                'One or more invalid default options have been specified in the prompt controls. '
                'Make sure that the default options defined in the control is present in the prompt item.'
            )
        choice_prompt = TransformChoicePromptEvent(
            prompt_id=str(uuid.uuid4()),
            message=message,
            options=options,
            default_option_id=default_option_id,
            timeout=timeout,
            control=control
        )
        if self.output_queue is None:
            raise NoOutputQueueError("choice")
        self.output_queue.put(choice_prompt)

        if self.input_queue is None:
            raise NoInputQueueError("choice")

        return await self.__get_prompt_response(
            choice_prompt.prompt_id,
            self.input_queue,
            timeout,
        )

    @track_prompt_waiting
    async def multi_choice(
            self,
            message: str,
            controls: list[
                Union[DropdownControl, RadioControl, CheckboxControl]
            ],
            timeout: Optional[int] = None,
    ) -> TransformPromptResponse:

        if controls is None or len(controls) < 1:
            raise ValueError(
                'At least one control must be provided for the multi choice control')

        multi_choice_prompt = TransformMultiChoicePromptEvent(
            prompt_id=str(uuid.uuid4()),
            message=message,
            timeout=timeout,
            controls=controls
        )

        if self.output_queue is None:
            raise NoOutputQueueError("multi_choice")
        self.output_queue.put(multi_choice_prompt)

        if self.input_queue is None:
            raise NoInputQueueError("multi_choice")

        return await self.__get_prompt_response(
            multi_choice_prompt.prompt_id,
            self.input_queue,
            timeout,
        )

    @track_prompt_waiting
    async def input(
            self,
            message: str,
            items: list[InputPromptItem],
            timeout: Optional[int] = None
    ) -> TransformPromptResponse:
        for item in items:
            if not isinstance(item, InputPromptItem):
                raise ValueError(
                    'The prompt items must be of type InputPromptItem'
                )
        input_prompt = TransformInputPromptEvent(
            prompt_id=str(uuid.uuid4()),
            message=message,
            items=items,
            timeout=timeout
        )
        if self.output_queue is None:
            raise NoOutputQueueError("input")
        self.output_queue.put(input_prompt)

        if self.input_queue is None:
            raise NoInputQueueError("input")

        return await self.__get_prompt_response(
            input_prompt.prompt_id,
            self.input_queue,
            timeout,
        )

    async def __get_prompt_response(
            self,
            prompt_id: str,
            input_queue: asyncio.Queue[Any],
            timeout: Optional[int] = None,
    ) -> TransformPromptResponse:
        """Retrieve a TransformPromptResponse from the input queue

        Waits for a TransformRunExecutionInput item to be placed on the input_queue. Once a
        input is retrieved from the queue checks if it is a type of TransformPromptResponse and
        if the id corresponds to the original prompt sent to the client. If not places the item
        back on the queue and continues to wait.
        If the timeout is reached, TimeoutError is raised.
        """
        try:
            # Even if the prompt doesn't have a timeout, we use the default timeout as max to avoid waiting indefinitely
            if timeout is None:
                timeout = DEFAULT_PROMPT_TIMEOUT_SECONDS
            else:
                timeout += PROMPT_TIMEOUT_ERROR_BUFFER
            while True:
                input_entry = await asyncio.wait_for(input_queue.get(), timeout=timeout)
                prompt_response_id = input_entry.input_id
                prompt_response = input_entry.data
                if isinstance(prompt_response, TransformPromptResponse) and prompt_id == prompt_response_id:
                    return prompt_response
                input_queue.put_nowait(input_entry)
        except TimeoutError:
            log.exception("Timeout while executing transform.", exc_info=True)
            raise MaltegoTransformTimeoutError(
                f"Timeout after {timeout}s "
                f"reached while awaiting prompt response."
            )


class MaltegoUserAgent:

    def __init__(self, user_agent: Optional[str]):
        self.user_agent = user_agent
        self.major_version: Optional[int] = None
        self.minor_version: Optional[int] = None
        self.patch_version: Optional[int] = None
        self.prerelease: Optional[str] = None
        self.build_metadata: Optional[str] = None
        self.product_name: Optional[str] = None
        self.os_name: Optional[str] = None
        self.os_version: Optional[str] = None
        self.__parse()

    def __parse(self) -> None:
        (
            self.major_version,
            self.minor_version,
            self.patch_version,
            self.prerelease,
            self.build_metadata,
            self.extra
        ) = parse_ua(self.user_agent)

    def __str__(self) -> str:
        agent = f"Maltego Desktop/{self.major_version}.{self.minor_version}.{self.patch_version}"
        if self.prerelease:
            agent += f"-{self.prerelease}"
        if self.build_metadata:
            agent += f"+{self.build_metadata}"
        return f"{agent} ({self.product_name}; {self.os_name}; {self.os_version})"

    def __repr__(self) -> str:
        return self.__str__()

    def _get_min_version(self, major: int, minor: int, patch: int) -> tuple[int, int, int]:
        if (major, minor, patch) <= CLIENT_MINIMAL_VERSION:
            log.warning(
                "Cannot check for version older then 4.5.0 assuming 4.5.0")
        return CLIENT_MINIMAL_VERSION

    def version_tuple(self) -> Optional[Tuple[int, int, int]]:
        version_tuple_ = (self.major_version,
                          self.minor_version, self.patch_version)
        if version_tuple_[0] is None:
            return None
        if version_tuple_[1] is None:
            return None
        if version_tuple_[2] is None:
            return None
        return (version_tuple_[0], version_tuple_[1], version_tuple_[2])

    def version_lte(self, major: int, minor: int, patch: int) -> bool:
        version = self.version_tuple()
        if version is None:
            version = self._get_min_version(major, minor, patch)
        return version <= (major, minor, patch)

    def version_lt(self, major: int, minor: int, patch: int) -> bool:
        version = self.version_tuple()
        if version is None:
            version = self._get_min_version(major, minor, patch)
        return version < (major, minor, patch)

    def version_gte(self, major: int, minor: int, patch: int) -> bool:
        version = self.version_tuple()
        if version is None:
            version = self._get_min_version(major, minor, patch)
        return version >= (major, minor, patch)

    def version_gt(self, major: int, minor: int, patch: int) -> bool:
        version = self.version_tuple()
        if version is None:
            version = self._get_min_version(major, minor, patch)
        return version > (major, minor, patch)

class TraceContext:
    def __init__(self, traceparent: Optional[str]):
        self.traceparent = traceparent
        self.trace_id = None
        self.span_id = None
        self._parse_traceparent()

    def _parse_traceparent(self):
        if self.traceparent:
            parts = self.traceparent.split("-")
            if len(parts) >= 3:
                self.trace_id = parts[1]
                self.span_id = parts[2]

    def __str__(self):
        return self.traceparent if self.traceparent else "No Trace Context"

class MaltegoContext:
    def __init__(
        self,
        graph: MaltegoGraph[Any],
        request: Request,
        api_key: Optional[str] = None,
        remote_ip: Optional[str] = None,
        content: Optional[bytes] = None,
        v3_request: bool = False,
        transform_run_execution_context: Optional[TransformRunExecutionContext] = None,
        capabilities: Optional[ResolvedCapabilitiesSet] = None,
        identity: Optional[Identity] = None,
        rate_limit_key: Optional[str] = None,
        auth_claims: Optional[Dict[str, Any]] = None,
        auth_payload: Any = None,
        unverified_auth_claims: Optional[Dict[str, Any]] = None,
        auth_context: Optional[AuthContext] = None,
    ) -> None:
        self.graph = graph
        self.api_key = api_key
        self.remote_ip = remote_ip
        self.log = LogCollector()
        self._request = request
        self._request_content = content
        self.response_headers: Dict[str, str] = {}
        self.middleware_extra: Dict[str, Any] = {}
        self.v3_request = v3_request
        # Safeguard for request being None
        traceparent = None
        if request is not None and hasattr(request, "headers"):
            traceparent = request.headers.get("traceparent")
        self.trace_context = TraceContext(traceparent)
        self._prompt = Prompt()
        self.ua = MaltegoUserAgent(self.user_agent)
        self.transform_run_execution_context = transform_run_execution_context
        self.capabilities = capabilities or ResolvedCapabilitiesSet(set())
        # Auth data from validated provider claims/assertions.
        self.auth_context = auth_context or AuthContext(
            identity=identity,
            rate_limit_key=rate_limit_key,
            auth_claims=auth_claims,
            auth_payload=auth_payload,
            unverified_auth_claims=unverified_auth_claims,
        )
        self.identity = self.auth_context.identity
        self.rate_limit_key = self.auth_context.rate_limit_key
        self.auth_claims = self.auth_context.auth_claims
        self.auth_payload = self.auth_context.auth_payload
        self.unverified_auth_claims = self.auth_context.unverified_auth_claims
        self.auth_token_origin = self.auth_context.token_origin
        self.auth_credential_header = self.auth_context.credential_header
        self.auth_upstream_identity_method = self.auth_context.upstream_identity_method
        self.upstream_exceptions: List[Exception] = []

    def set_log_queue(self, log_queue: Queue[Any]) -> None:
        self.log.set_log_queue(log_queue)
        self._prompt.set_output_queue(log_queue)

    def set_result_set(self, result_set: Any) -> None:
        """Set reference to result set for prompt tracking"""
        self._prompt.set_result_set(result_set)

    def set_input_queue(self, input_queue: asyncio.Queue[Any]) -> None:
        self._prompt.set_input_queue(input_queue)

    @property
    def request(self) -> Request:
        """Returns FastAPI's request object

        :return: fastapi.Request object
        :rtype: fastapi.Request
        """
        return self._request

    @property
    def user_agent(self) -> Optional[str]:
        """Returns the transform run requests user agent header if present

        :return: Returns the transform run requests user agent header if present
        :rtype: str, optional
        """
        try:
            return self.request.headers.get("user-agent") if self.request is not None else None
        except KeyError:
            return None

    def get_request_headers(self) -> Dict[str, Any]:
        """Returns the request headers as a dictionary.

        :return: Dictionary containing request headers.
        :rtype: dict
        """
        return dict(self._request.headers)

    async def choice_prompt(
        self,
        message: str,
        options: list[PromptItem],
        default_option_id: Optional[str] = None,
        timeout: Optional[int] = DEFAULT_PROMPT_TIMEOUT_SECONDS,
        control: Optional[
            Union[
                DropdownControl,
                RadioControl,
                CheckboxControl,
                ButtonControl
            ]
        ] = None,
    ) -> TransformPromptResponse:
        """
        Displays a popup dialog to the users with a list of available options to choose from.

        :param message: Message to display on the dialog
        :type message: str
        :param options: A list of options to display to the user
        :type options: List[str]
        :param default_option_id:
            The id of the option that will be selected by default if the user
            either cancel the prompt or the timeout value is exceeded

            .. deprecated:: 3.3.0
                The ``default_option_id`` parameter has been deprecated and should no
                longer be used. If you would like define a default option use one of the controls and
                define the default_option_id (for single select control) or default_option_ids (for
                multi-select controls).
        :type default_option_id: Optional[str]
        :param timeout:
            An optional timeout, in seconds, that will close the prompt
            and return either the default option (if specified) or an empty response
            if the user does not respond within the specified time.
        :type timeout: int, Optional
        :param control:
            The type of control to use to display the available options. The control options are:

            DropdownControl:
            Use this type to display multiple available options in a dropdown
            control from which the user can select a single option.

            RadioControl:
            Use this type to display multiple available options in a radio control
            from which the user can activate a single option.

            CheckboxControl:
            Use this type to display the available options in a checkbox control. The
            user has the ability to select one or more options from the control.

            ButtonControl:
            Use this type when you would like to display the available options as buttons.
            The user will make their choice by clicking one of the available buttons.
        :type control:
            Optional[Union[DropdownControl, RadioControl, CheckboxControl, ButtonControl]]
        :return: Returns the value selected by the user
        :rtype: str

        """
        if not self.capabilities.has(MaltegoCapability.PROMPT_BASE):
            raise MaltegoVersionNotSupported(
                "This client does not support the 'prompt-base' capability required for this operation."
            )

        if control is not None and not self.capabilities.has(MaltegoCapability.CHOICE_CONTROL_TYPE):
            raise MaltegoVersionNotSupported(
                "This client does not support the 'choice-control-type' capability required for this operation."
            )
        return await self._prompt.choice(
            message,
            options,
            default_option_id,
            timeout,
            control
        )

    async def multi_choice_prompt(
        self,
        message: str,
        controls: list[
            Union[
                DropdownControl,
                RadioControl,
                CheckboxControl
            ]
        ],
        timeout: Optional[int] = DEFAULT_PROMPT_TIMEOUT_SECONDS,
    ) -> TransformPromptResponse:
        """
        Displays a popup dialog to the users with multiple controls, allowing the user to provide
        values for each control.

        :param message: Message to display on the dialog.
        :type message: str
        :param controls: A list of controls to display to the user. Each control can be one of the following types:

            DropdownControl:
            Use this type to display multiple available options in a dropdown control
            from which the user can select a single option.

            RadioControl:
            Use this type to display multiple available options in a radio control
            from which the user can activate a single option.

            CheckboxControl:
            Use this type to display the available options in a checkbox control. The user has the
            ability to select one or more options from the control.

        :type controls: list[Union[DropdownControl, RadioControl, CheckboxControl]]
        :param timeout:
            An optional timeout, in seconds, that will close the prompt and return either the default options
            (if specified) or an empty response if the user does not respond within the specified time.
        :type timeout: Optional[int]
        :return: Returns the values selected by the user for each control.
        :rtype: TransformPromptResponse

        :raises MaltegoVersionNotSupported:
            If the Maltego version is less than 4.7.2, the capability to define multiple controls on a
            single choice prompt is not supported. Please consider updating your Maltego installation.
        """
        if not self.capabilities.has(MaltegoCapability.MULTI_CHOICE_CONTROLS):
            raise MaltegoVersionNotSupported(
                "This client does not support the 'multi-choice-controls' capability required for this operation."
            )

        if not self.v3_request:
            raise MaltegoPromptNotSupportedError()

        return await self._prompt.multi_choice(
            message,
            controls,
            timeout
        )

    async def input_prompt(
            self,
            message: str,
            items: list[InputPromptItem],
            timeout: Optional[int] = DEFAULT_PROMPT_TIMEOUT_SECONDS
    ) -> TransformPromptResponse:
        """
        Displays a popup dialog to the users with a list of input values to be completed by the user.

        :param message: Message to display on the dialog
        :type message: str
        :param items: The input items which the user will need to complete
        :type items: list[InputPromptItem]
        :param timeout:
            An optional timeout, in seconds, that will close the prompt
            and return either the default values (where specified)
        :type timeout: Optional[int]
        """
        if not self.capabilities.has(MaltegoCapability.PROMPT_BASE):
            raise MaltegoVersionNotSupported(
                "This client does not support the 'prompt-base' capability required for this operation."
            )

        if not self.v3_request:
            raise MaltegoPromptNotSupportedError()

        return await self._prompt.input(message, items, timeout)
