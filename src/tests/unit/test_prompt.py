# Copyright (c) Maltego Technologies GmbH.
from typing import Any

import pytest
import asyncio

from queue import Queue
from maltego.model.context import Prompt
from maltego.model.event import INVALID_CHOICE_OPTIONS_ERROR, INVALID_MESSAGE_ERROR, INVALID_TIMEOUT_ERROR, TransformChoicePromptEvent
from maltego.model.prompt import INVALID_INPUT_OPTIONS_SUB_TYPE_ERROR, INVALID_PROMPT_ITEM_ERROR, InputTypes, TransformPromptResponse, PromptItem, InputPromptItem
from maltego.runner import TransformRunExecutionInput

pytestmark = pytest.mark.unit


def get_test_prompt():
    prompt = Prompt()
    prompt.EXTRA_WAIT_TIME_FOR_CLIENT_RESPONSE = 0
    input_queue: asyncio.Queue[Any] = asyncio.Queue()
    output_queue: Queue = Queue()
    prompt.set_output_queue(output_queue)
    prompt.set_input_queue(input_queue)
    return prompt


@pytest.mark.asyncio
async def test_invalid_choice_prompt():

    prompt = get_test_prompt()

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.choice(
            message="",
            options=[
                PromptItem("One"),
                PromptItem("Two"),
                PromptItem("Three"),
            ]
        )
    assert INVALID_MESSAGE_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.choice(
            message="message",
            options=[]
        )
    assert INVALID_CHOICE_OPTIONS_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.choice(
            message="message",
            options=[PromptItem("")]
        )
    assert INVALID_PROMPT_ITEM_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.choice(
            message="message",
            options=[PromptItem("one")],
            timeout=-1
        )
    assert INVALID_TIMEOUT_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.choice(
            message="message",
            options=[PromptItem("one")],
            timeout=0
        )
    assert INVALID_TIMEOUT_ERROR in str(prompt_ex.value)


@pytest.mark.asyncio
async def test_invalid_inputs_prompt():

    prompt = get_test_prompt()

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.input(
            message="",
            items=[
                InputPromptItem("One", InputTypes.str)
            ]
        )
    assert INVALID_MESSAGE_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.input(
            message="message",
            items=[],
        )
    assert INVALID_CHOICE_OPTIONS_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        # noinspection PyTypeChecker
        await prompt.input(
            message="message",
            items=[InputPromptItem("id", None)]
        )
    assert INVALID_INPUT_OPTIONS_SUB_TYPE_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.input(
            message="message",
            items=[InputPromptItem("id", InputTypes.str)],
            timeout=-5
        )
    assert INVALID_TIMEOUT_ERROR in str(prompt_ex.value)

    with pytest.raises(ValueError) as prompt_ex:
        await prompt.input(
            message="message",
            items=[InputPromptItem("id", InputTypes.str)],
            timeout=0
        )
    assert INVALID_TIMEOUT_ERROR in str(prompt_ex.value)


@pytest.mark.asyncio
async def test_fetch_transform_prompt_response_from_input_queue():

    prompt = get_test_prompt()

    transform_prompt_response = TransformPromptResponse()
    transform_prompt_response.result = {"one", "one"}
    prompt.input_queue.put_nowait(TransformRunExecutionInput("id", transform_prompt_response))
    choice_prompt = TransformChoicePromptEvent(
        prompt_id="id",
        message="test",
        options=[PromptItem("one")],
        default_option_id="one",
        timeout=5
    )
    prompt.output_queue.put_nowait(choice_prompt)
    # noinspection PyUnresolvedReferences
    response = await prompt._Prompt__get_prompt_response("id", prompt.input_queue)

    assert "one" in response.result


@pytest.mark.asyncio
async def test_fetch_with_unknown_message_in_input_queue():

    class UnknownInputMessage:
        foo = "bar"

    prompt = get_test_prompt()

    transform_prompt_response = TransformPromptResponse()
    transform_prompt_response.result = {"one", "one"}
    prompt.input_queue.put_nowait(TransformRunExecutionInput("id", transform_prompt_response))
    for i in range(10):
        prompt.input_queue.put_nowait(TransformRunExecutionInput(f"id_{i}", UnknownInputMessage()))
    choice_prompt = TransformChoicePromptEvent(
        prompt_id="id",
        message="test",
        options=[
            PromptItem("one"),
            PromptItem("two")
        ],
        default_option_id="one",
        timeout=5
    )
    prompt.output_queue.put_nowait(choice_prompt)
    # noinspection PyUnresolvedReferences
    response = await prompt._Prompt__get_prompt_response("id", prompt.input_queue)

    assert "one" in response.result
