# Copyright (c) Maltego Technologies GmbH.
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from maltego.protocol.v3.execution.transform_run import (
    DropdownChoicePromptControl, RadioChoicePromptControl, CheckboxChoicePromptControl,
    ButtonChoicePromptControl, ChoicePrompt
)

INVALID_PROMPT_ITEM_ERROR = "Item Error: A valid item_id is necessary for the prompt item"
INVALID_INPUT_OPTIONS_SUB_TYPE_ERROR = "Input Error: An input type is mandatory for the input prompt item"


class TransformPromptResponse:
    reason: Literal["TIMED_OUT", "CANCELLED", "COMPLETED"]
    result: dict[str, Any]


class InputTypes(Enum):
    """Input prompt types

    :param Enum: _description_
    :type Enum: _type_
    """
    # pylint: disable=invalid-name
    str = "string"
    float = "double"
    int = "int"
    boolean = "boolean"
    date = "date"
    datetime = "datetime"
    datetime_range = "daterange"
    str_list = "string[]"
    float_list = "double[]"
    int_list = "int[]"
    boolean_list = "boolean[]"
    date_list = "date[]"


class PromptItem:

    def __init__(
            self,
            item_id: str,
            display_name: Optional[str] = None
    ):
        if not item_id:
            raise ValueError(INVALID_PROMPT_ITEM_ERROR)
        self.item_id = item_id
        self.display_name = display_name or self.item_id


class InputPromptItem(PromptItem):
    """Represents a single item in an Input prompt which requires the user to enter
      a specific value of the defined type.

    :param input_id: An ID tha uniquely identifies the input item. This value
                     is later used to identify the input item response received
                     from the desktop client.
    :type input_id: str
    :param input_type: Indicate the input type to use. This affects what control
                       on the input prompt.
    :type input_type: InputTypes
    :param default_value: The value to which the input control will default to
                          if the user does not supply a value.
    :type default_value: Optional[Any]
    :param display_name: The name of the input displayed on the input prompt control. If
                         no value is supplied then the input_id will be used.
    :type display_name: Optional[str]

    """

    def __init__(
            self,
            input_id: str,
            input_type: InputTypes,
            default_value: Optional[Any] = None,
            display_name: Optional[str] = None
    ):
        super().__init__(input_id, display_name)
        if input_type is None:
            raise ValueError(INVALID_INPUT_OPTIONS_SUB_TYPE_ERROR)
        self.input_type = input_type
        self.default_value = default_value


class DropdownControl:
    """
    Displays the available options as a dropdown control on the choice prompt in the client. This
    control restricts the user to select a single value from the available options.

    :param control_id: An optional identifier for the control. This can be used to reference the control
    programmatically when used as part of a multi choice prompt. If no value is provided then a unique ID
    will be generated and assigned.
    :type control_id: Optional[str]

    :param default_option_id: An optional default value to return if the user did not make any selection.
    :type default_option_id: Optional[str]

    :param label: An optional label to display alongside the dropdown control, providing context or
    instructions to the user.
    :type label: Optional[str]

    :param options: A list of objects representing the available options for the dropdown. Each PromptItem
    should contain the necessary attributes to be displayed as an option in the dropdown.
    :type options: list[PromptItem]
    """

    def __init__(
            self,
            control_id: Optional[str] = None,
            default_option_id: Optional[str] = None,
            label: Optional[str] = None,
            options: Optional[list[PromptItem]] = None,
    ):
        self.control_id = control_id or str(uuid.uuid4())
        self.label = label
        self.options = options
        self.default_option_id = default_option_id

        if self.default_option_id is not None and self.options is not None:
            if not any(option.item_id == default_option_id for option in self.options):
                raise ValueError(f"Default option id: {self.default_option_id} is not present in the list of options")

    def validate_default_options(self, prompt_option_ids: list[str]) -> bool:
        if self.default_option_id is None:
            return True
        return self.default_option_id in prompt_option_ids

    def to_v3_event(self) -> DropdownChoicePromptControl:
        return DropdownChoicePromptControl(
            control_id=self.control_id,
            label=self.label,
            options=[
                ChoicePrompt(
                    id=i.item_id,
                    display_name=i.display_name
                ) for i in self.options or []],
            default_option_id=self.default_option_id
        )


class RadioControl:
    """
    Displays the available options as a radio control on the choice prompt in the client. This
    control restricts the user to select a single value from the available options.

    :param control_id: An optional identifier for the control. This can be used to reference the control
    programmatically when used as part of a multi choice prompt. If no value is provided then a unique ID
    will be generated and assigned.
    :type control_id: Optional[str]

    :param default_option_id: An optional default value to return if the user
    did not make any selection. It should be a list containing a single string value.
    :type default_option_id: Optional[list[str]]

    :param label: An optional label to display alongside the radio control, providing context or
    instructions to the user.
    :type label: Optional[str]

    :param options: A list of PromptItem objects representing the available options for the radio control.
    Each PromptItem should contain the necessary attributes to be displayed as an option.
    :type options: Optional[list[PromptItem]]
    """

    def __init__(
            self,
            control_id: Optional[str] = None,
            default_option_id: Optional[str] = None,
            label: Optional[str] = None,
            options: Optional[list[PromptItem]] = None,
    ):
        self.control_id = control_id or str(uuid.uuid4())
        self.label = label
        self.options = options
        self.default_option_id = default_option_id

        if self.default_option_id is not None and self.options is not None:
            if not any(option.item_id == default_option_id for option in self.options):
                raise ValueError(f"Default option id: {self.default_option_id} is not present in the list of options")

    def validate_default_options(self, prompt_option_ids: list[str]) -> bool:
        if self.default_option_id is None:
            return True
        return self.default_option_id in prompt_option_ids

    def to_v3_event(self) -> RadioChoicePromptControl:
        return RadioChoicePromptControl(
            control_id=self.control_id,
            label=self.label,
            options=[
                ChoicePrompt(
                    id=i.item_id,
                    display_name=i.display_name
                ) for i in self.options or []],
            default_option_id=self.default_option_id
        )


class CheckboxControl:
    """
    Displays the available options as a checkbox control on the choice prompt in the client. This
    control allows the user to select multiple values from the available options.

    :param control_id: An optional identifier for the control. This can be used to reference the control
    programmatically when used as part of a multi choice prompt. If no value is provided then a unique ID
    will be generated and assigned.
    :type control_id: Optional[str]

    :param default_option_ids: An optional list of default values to return if the user did not make any selection.
    :type default_option_ids: Optional[list[str]]

    :param label: An optional label to display alongside the checkbox control,
    providing context or instructions to the user.
    :type label: Optional[str]

    :param options: A list of PromptItem objects representing the available options for the checkbox control. Each
    PromptItem should contain the necessary attributes to be displayed as an option.
    :type options: Optional[list[PromptItem]]
    """

    def __init__(
            self,
            control_id: Optional[str] = None,
            default_option_ids: Optional[list[str]] = None,
            label: Optional[str] = None,
            options: Optional[list[PromptItem]] = None,
    ):
        self.control_id = control_id or str(uuid.uuid4())
        self.default_option_ids = default_option_ids
        self.label = label
        self.options = options

        if self.default_option_ids is not None and self.options is not None:
            option_ids = [option.item_id for option in self.options]
            for default_option_id in self.default_option_ids:
                if default_option_id not in option_ids:
                    raise ValueError(f"Default option id: {default_option_id} is not present in the list of options")

    def validate_default_options(self, prompt_option_ids: list[str]) -> bool:
        if self.default_option_ids is None:
            return True
        return all(opt_id in prompt_option_ids for opt_id in self.default_option_ids)

    def to_v3_event(self) -> CheckboxChoicePromptControl:
        return CheckboxChoicePromptControl(
            control_id=self.control_id,
            label=self.label,
            options=[
                ChoicePrompt(
                    id=i.item_id,
                    display_name=i.display_name
                ) for i in self.options or []],
            default_option_ids=self.default_option_ids
        )


class ButtonControl:
    """
    Displays the available options as buttons on the choice prompt in the client. The
    user makes their selection by clicking on a single button on the prompt control.

    :param control_id: An optional identifier for the control. This can be used to reference the control
    programmatically when used as part of a multi choice prompt. If no value is provided then a unique ID
    will be generated and assigned.
    :type control_id: Optional[str]

    :param default_option_id: An optional default value to return if the user did not make any selection.
    :type default_option_id: Optional[str]

    :param options: A list of PromptItem objects representing the available options for the buttons. Each PromptItem
    should contain the necessary attributes to be displayed as a button.
    :type options: list[PromptItem]
    """

    def __init__(
            self,
            control_id: Optional[str] = None,
            default_option_id: Optional[str] = None,
            options: Optional[list[PromptItem]] = None,
    ):
        self.control_id = control_id or str(uuid.uuid4())
        self.default_option_id = default_option_id
        self.options = options

        if self.default_option_id is not None and self.options is not None:
            if not any(option.item_id == default_option_id for option in self.options):
                raise ValueError(f"Default option id: {self.default_option_id} is not present in the list of options")

    def validate_default_options(self, prompt_option_ids: list[str]) -> bool:
        if self.default_option_id is None:
            return True
        return self.default_option_id in prompt_option_ids

    def to_v3_event(self) -> ButtonChoicePromptControl:
        return ButtonChoicePromptControl(
            control_id=self.control_id,
            default_option_id=self.default_option_id,
            options=[
                ChoicePrompt(
                    id=i.item_id,
                    display_name=i.display_name
                ) for i in self.options or []],
        )
