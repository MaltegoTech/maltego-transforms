# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=unused-argument
from typing import Any, List, Optional

from tests.conftest import Phrase
from maltego.model.context import MaltegoContext
from maltego.model.prompt import (
    InputTypes, InputPromptItem, PromptItem,
    DropdownControl, CheckboxControl,
    RadioControl, ButtonControl
)
from maltego.model.graph import MaltegoGraph
from maltego.server import register_transform

PROMPT_INTERFACE_TRANSFORM_SET = "Prompt Test Transforms [Maltego]"

__all__ = [
    "transform_prompt_single_choice_dropdown_example_legacy",
    "transform_prompt_single_choice_dropdown_example_new",
    "transform_prompt_single_choice_radio_example_legacy",
    "transform_prompt_single_choice_radio_example_new",
    "transform_prompt_single_choice_checkbox_example_legacy",
    "transform_prompt_single_choice_checkbox_example_new",
    "transform_prompt_single_choice_button_example_legacy",
    "transform_prompt_single_choice_button_example_new",
    "transform_prompt_choice_single",
    "transform_prompt_choice_button",
    "transform_prompt_choice_test_graph",
    "transform_prompt_input_test",
    "transform_prompt_multi_choice_single_radio",
    "transform_prompt_multi_choice_multiple_dropdowns",
    "transform_prompt_multi_choice_rich",
    "transform_prompt_multi_choice_radio_dropdowns_with_timeout"
]


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Dropdown Legacy"
)
async def transform_prompt_single_choice_dropdown_example_legacy(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
            PromptItem("D", "Fourth"),
            PromptItem("E", "Fifth"),
            PromptItem("F", "Sixth"),
            PromptItem("G", "Seventh"),
            PromptItem("H", "Eight"),
        ],
        timeout=10,
        control=DropdownControl()
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Dropdown New"
)
async def transform_prompt_single_choice_dropdown_example_new(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        timeout=10,
        control=DropdownControl(
            label="Default option already selected (A)",
            default_option_id="A"
        ),
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
        ]
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Radio Legacy"
)
async def transform_prompt_single_choice_radio_example_legacy(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
            PromptItem("D", "Fourth"),
            PromptItem("E", "Fifth"),
            PromptItem("F", "Sixth"),
            PromptItem("G", "Seventh"),
            PromptItem("H", "Eight"),
        ],
        timeout=10,
        control=RadioControl()
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Radio New"
)
async def transform_prompt_single_choice_radio_example_new(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        timeout=10,
        control=RadioControl(
            label="Default option already selected (A)",
            default_option_id="A"
        ),
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
        ]
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Checkbox Legacy"
)
async def transform_prompt_single_choice_checkbox_example_legacy(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
            PromptItem("D", "Fourth"),
            PromptItem("E", "Fifth"),
            PromptItem("F", "Sixth"),
            PromptItem("G", "Seventh"),
            PromptItem("H", "Eight"),
        ],
        timeout=10,
        control=CheckboxControl()
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Checkbox New"
)
async def transform_prompt_single_choice_checkbox_example_new(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        timeout=10,
        control=CheckboxControl(
            label="Default option already selected (A)",
            default_option_ids=["A", "B"],
        ),
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
        ]
    )
    context.log.inform(response.result)
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Button Legacy"
)
async def transform_prompt_single_choice_button_example_legacy(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
            PromptItem("D", "Fourth"),
            PromptItem("E", "Fifth"),
            PromptItem("F", "Sixth"),
            PromptItem("G", "Seventh"),
            PromptItem("H", "Eight"),
        ],
        timeout=10,
        control=ButtonControl()
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Button New"
)
async def transform_prompt_single_choice_button_example_new(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    response = await context.choice_prompt(
        message="First option is the correct one.",
        timeout=10,
        control=ButtonControl(
            default_option_id="A"
        ),
        options=[
            PromptItem("A", "First"),
            PromptItem("B", "Second"),
            PromptItem("C", "Third"),
        ]
    )
    if response.reason == "CANCELLED":
        return context.graph
    if 'A' in response.result:
        context.log.inform("Correct!")
    else:
        context.log.inform("Incorrect!")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Single Button Legacy"
)
async def transform_prompt_choice_single(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    await context.choice_prompt(
        message="Hello World",
        options=[
            PromptItem("A", "OK"),
        ],
        timeout=10,
    )

    return context.graph


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Buttons Legacy"
)
async def transform_prompt_choice_button(
    entity: Phrase, context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    await context.choice_prompt(
        message="Hello World",
        options=[
            PromptItem("A", "OK"),
            PromptItem("B", "Not OK"),
        ],
        timeout=10,
        control=ButtonControl()
    )

    return context.graph


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Single Prompt: Graph Input"
)
async def transform_prompt_choice_test_graph(
    graph: MaltegoGraph[Phrase], context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:
    response = await context.choice_prompt(
        message="Stop the transform?",
        timeout=5,
        control=ButtonControl(
            default_option_id="y"
        ),
        options=[
            PromptItem("y", "Yes"),
            PromptItem("n", "No"),
        ]
    )
    if "y" in response.result:
        context.log.fatal("Transform stopped by user")
        return None

    return graph


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Prompts: Inputs"

)
async def transform_prompt_input_test(
    graph: MaltegoGraph[Any], context: MaltegoContext
) -> MaltegoGraph[Any]:
    inputs: List[InputPromptItem] = [
        InputPromptItem("int-input", InputTypes.int, 1),
        InputPromptItem("int-list-input", InputTypes.int_list, [1, 2]),
        InputPromptItem("bool-input", InputTypes.boolean),
        InputPromptItem("bool-list-input", InputTypes.boolean_list),
        InputPromptItem("str-input", InputTypes.str),
        InputPromptItem("str-list-input", InputTypes.str_list),
        InputPromptItem("float-input", InputTypes.float),
        InputPromptItem("float-list-input", InputTypes.float_list),
        InputPromptItem("date-input", InputTypes.date),
        InputPromptItem("date-list-input", InputTypes.date_list),
        InputPromptItem("datetime-input", InputTypes.datetime),
        InputPromptItem("datetime-range-input", InputTypes.datetime_range)
    ]
    response = await context.input_prompt(
        message="Complete inputs:",
        items=inputs
    )
    option_entity = Phrase("prompt entity")
    for key, value in response.result.items():
        option_entity.set_property(key, value)
    input_entity = graph.entities[0]
    graph.add_entity(option_entity)
    graph.add_link(input_entity, option_entity)
    return graph


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Multi Prompt: Single Radio Choice Prompts"
)
async def transform_prompt_multi_choice_single_radio(
    graph: MaltegoGraph[Phrase], context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:
    response = await context.multi_choice_prompt(
        message="Simple multi-choice prompt",
        controls=[
            RadioControl(
                label="Pick one",
                options=[
                    PromptItem("1", "One"),
                    PromptItem("2", "Two"),
                    PromptItem("3", "Three"),
                ]
            )
        ]
    )
    context.log.inform(response.result)
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Multi Prompt: Multi Dropdown Choice Prompts"
)
async def transform_prompt_multi_choice_multiple_dropdowns(
    graph: MaltegoGraph[Phrase], context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:
    response = await context.multi_choice_prompt(
        message="Multiple dropdown prompts",
        controls=[
            DropdownControl(
                control_id="one",
                label="Pick one",
                options=[
                    PromptItem("1", "One"),
                    PromptItem("2", "Two"),
                    PromptItem("3", "Three"),
                ]
            ),
            DropdownControl(
                control_id="two",
                label="Pick one",
                options=[
                    PromptItem("1", "One"),
                    PromptItem("2", "Two"),
                    PromptItem("3", "Three"),
                ]
            ),
            DropdownControl(
                control_id="three",
                label="Pick one",
                options=[
                    PromptItem("1", "One"),
                    PromptItem("2", "Two"),
                    PromptItem("3", "Three"),
                ]
            ),
            DropdownControl(
                control_id="four",
                label="Pick one",
                options=[
                    PromptItem("1", "One"),
                    PromptItem("2", "Two"),
                    PromptItem("3", "Three"),
                ]
            )
        ]
    )
    context.log.inform(response.result)
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Multi Prompt: Multi Dropdown Choice Prompts Rich"
)
async def transform_prompt_multi_choice_rich(
    graph: MaltegoGraph[Phrase], context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:
    answers = {
        "eighth": {
            "a": "Detoxification",
            "b": "Protein synthesis",
            "c": "Production of biochemicals necessary for digestion"
        },
        "fifth": {
            "c": "100,000"
        },
        "first": {
            "c": "Feet"
        },
        "fourth": {
            "b": "The human body contains enough fat to make seven bars of soap.",
            "d": "The average person produces enough saliva in their lifetime to fill two swimming pools."
        },
        "ninth": {
            "b": "17"
        },
        "second": {
            "a": "True"
        },
        "seventh": {
            "c": "5-6 liters"
        },
        "sixth": {
            "b": "Skin"
        },
        "tenth": {
            "b": "Medulla oblongata"
        },
        "third": {
            "c": "Brain"
        }
    }
    response = await context.multi_choice_prompt(
        message="Anatomical facts quiz",
        controls=[
            RadioControl(
                control_id="first",
                label="Which part of the human body is most likely to be ticklish?",
                options=[
                    PromptItem("a", "Ears"),
                    PromptItem("b", "Knees"),
                    PromptItem("c", "Feet")
                ],
                default_option_id="c"
            ),
            RadioControl(
                control_id="second",
                label="Humans are born with 300 bones, but by adulthood, the number is reduced to 206 "
                      "because some bones decide to become best friends and fuse together.",
                options=[
                    PromptItem("a", "True"),
                    PromptItem("b", "False")
                ],
                default_option_id="a"
            ),
            DropdownControl(
                control_id="third",
                label="Which organ is so brainy that it named itself?",
                options=[
                    PromptItem("a", "Liver"),
                    PromptItem("b", "Stomach"),
                    PromptItem("c", "Brain")
                ],
                default_option_id="c"
            ),
            CheckboxControl(
                control_id="fourth",
                label="Which of these statements are true?",
                options=[
                    PromptItem("a", "The tongue is the only muscle in the human body attached at just one end."),
                    PromptItem("b", "The human body contains enough fat to make seven bars of soap."),
                    PromptItem("c", "Humans can breathe and swallow at the same time."),
                    PromptItem("d", "The average person produces enough saliva in their "
                                    "lifetime to fill two swimming pools.")
                ],
                default_option_ids=["b", "d"]
            ),
            RadioControl(
                control_id="fifth",
                label="How many times does the average human heart beat per day?",
                options=[
                    PromptItem("a", "10,000"),
                    PromptItem("b", "50,000"),
                    PromptItem("c", "100,000")
                ],
                default_option_id="c"
            ),
            DropdownControl(
                control_id="sixth",
                label="Which is the largest organ in the human body?",
                options=[
                    PromptItem("a", "Liver"),
                    PromptItem("b", "Skin"),
                    PromptItem("c", "Lungs")
                ],
                default_option_id="b"
            ),
            RadioControl(
                control_id="seventh",
                label="How much blood does the average adult human body contain?",
                options=[
                    PromptItem("a", "3-4 liters"),
                    PromptItem("b", "4-5 liters"),
                    PromptItem("c", "5-6 liters")
                ],
                default_option_id="c"
            ),
            CheckboxControl(
                control_id="eighth",
                label="Which of these are functions of the liver?",
                options=[
                    PromptItem("a", "Detoxification"),
                    PromptItem("b", "Protein synthesis"),
                    PromptItem("c", "Production of biochemicals necessary for digestion"),
                    PromptItem("d", "Storing bile")
                ],
                default_option_ids=["a", "b", "c"]
            ),
            RadioControl(
                control_id="ninth",
                label="How many muscles does it take to smile?",
                options=[
                    PromptItem("a", "10"),
                    PromptItem("b", "17"),
                    PromptItem("c", "26")
                ],
                default_option_id="b"
            ),
            DropdownControl(
                control_id="tenth",
                label="Which part of the brain is responsible for regulating heartbeat and breathing?",
                options=[
                    PromptItem("a", "Cerebellum"),
                    PromptItem("b", "Medulla oblongata"),
                    PromptItem("c", "Cerebrum")
                ],
                default_option_id="b"
            )
        ]
    )

    if response.result == answers:
        await context.choice_prompt(
            message="Nice! You got everything right! Have you considered a career in medicine?",
            options=[
                PromptItem("y", "Yes"),
                PromptItem("n", "No"),
            ]
        )
        return graph

    context.log.fatal("Sorry, you got some wrong, try again.")
    return None


@register_transform(
    transform_set=PROMPT_INTERFACE_TRANSFORM_SET,
    display_name="Multi Prompt: Multi Radio Choice Prompts With Timeout"
)
async def transform_prompt_multi_choice_radio_dropdowns_with_timeout(
    graph: MaltegoGraph[Phrase], context: MaltegoContext
) -> Optional[MaltegoGraph[Any]]:

    controls = []
    for i in range(100):
        controls.append(
            RadioControl(
                control_id=f"ID {i}",
                label=f"Radio Control ID {i}",
                options=[PromptItem("1", "One"), PromptItem("2", "Two"), PromptItem("3", "Three")],
                default_option_id="1"
            )
        )

    response = await context.multi_choice_prompt(
        message="Multiple dropdown prompts",
        controls=controls,
        timeout=5
    )
    context.log.inform(response.result)
    return None
