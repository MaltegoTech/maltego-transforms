from typing import List, Optional

from maltego.entities import Phrase

from maltego.model.prompt import (
    ButtonControl,
    CheckboxControl,
    DropdownControl,
    InputPromptItem,
    InputTypes,
    PromptItem,
    RadioControl,
)
from maltego.server import MaltegoContext, MaltegoGraph, register_transform

TRANSFORM_SET = "New Maltego Integration"


@register_transform(
    display_name="Choice Prompt Example [New Maltego Integration]",
    description="Demonstrates a yes/no choice prompt",
    transform_set=TRANSFORM_SET,
    interactive=True,  # Recommended: declares this transform uses prompts
)
async def choice_prompt_example(
    entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Shows a choice prompt asking the user to continue or stop.
    """
    response = await context.choice_prompt(
        message="Would you like to continue?",
        options=[
            PromptItem("yes", "Yes, continue"),
            PromptItem("no", "No, stop"),
        ],
        timeout=30,  # Seconds to wait before using default
        default_option_id="yes",  # Used if timeout occurs
    )

    if "no" in response.result:
        context.log.inform(f"User chose to stop. Reason: {response.reason}")
        return None

    return Phrase(f"Continuing with: {entity.value}")


@register_transform(
    display_name="Multi-Choice Prompt Example [New Maltego Integration]",
    description="Demonstrates a multi-select choice prompt",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def multi_choice_prompt_example(
    entity: Phrase, context: MaltegoContext
) -> List[Phrase]:
    """
    Shows a choice prompt with multiple selectable options.
    """
    response = await context.choice_prompt(
        message="Select the data sources to query:",
        options=[
            PromptItem("dns", "DNS Records"),
            PromptItem("whois", "WHOIS Data"),
            PromptItem("ssl", "SSL Certificates"),
            PromptItem("subdomains", "Subdomains"),
        ],
        timeout=60,
        default_option_id="dns",
    )

    results = []
    for source_id in response.result:
        results.append(Phrase(f"Querying {source_id} for {entity.value}"))

    return results


@register_transform(
    display_name="Dropdown Control Example [New Maltego Integration]",
    description="Demonstrates choice prompt with dropdown control",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def dropdown_control_example(
    entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Shows a dropdown control for single selection from many options.
    """
    response = await context.choice_prompt(
        message="Select a data source:",
        options=[
            PromptItem("dns", "DNS Records"),
            PromptItem("whois", "WHOIS Data"),
            PromptItem("ssl", "SSL Certificates"),
            PromptItem("subdomains", "Subdomains"),
        ],
        control=DropdownControl(
            default_option_id="dns",
            label="Data Source",
        ),
        timeout=30,
    )

    if response.reason == "CANCELLED":
        return None

    # Check which option was selected
    if "dns" in response.result:
        return Phrase("Selected: DNS Records")
    elif "whois" in response.result:
        return Phrase("Selected: WHOIS Data")
    elif "ssl" in response.result:
        return Phrase("Selected: SSL Certificates")
    elif "subdomains" in response.result:
        return Phrase("Selected: Subdomains")

    return None


@register_transform(
    display_name="Radio Control Example [New Maltego Integration]",
    description="Demonstrates choice prompt with radio buttons",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def radio_control_example(
    entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Shows radio buttons for single selection with all options visible.
    """
    response = await context.choice_prompt(
        message="Choose scan depth:",
        options=[
            PromptItem("quick", "Quick Scan (faster)"),
            PromptItem("normal", "Normal Scan"),
            PromptItem("deep", "Deep Scan (slower)"),
        ],
        control=RadioControl(
            default_option_id="normal",
            label="Scan Type",
        ),
        timeout=30,
    )

    if response.reason == "CANCELLED":
        return None

    if "quick" in response.result:
        return Phrase(f"Running quick scan on {entity.value}")
    elif "deep" in response.result:
        return Phrase(f"Running deep scan on {entity.value}")
    else:
        return Phrase(f"Running normal scan on {entity.value}")


@register_transform(
    display_name="Checkbox Control Example [New Maltego Integration]",
    description="Demonstrates choice prompt with checkboxes for multi-select",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def checkbox_control_example(
    entity: Phrase, context: MaltegoContext
) -> List[Phrase]:
    """
    Shows checkboxes allowing multiple selections.
    """
    response = await context.choice_prompt(
        message="Select features to enable:",
        options=[
            PromptItem("cache", "Enable Caching"),
            PromptItem("retry", "Auto Retry on Failure"),
            PromptItem("log", "Verbose Logging"),
        ],
        control=CheckboxControl(
            default_option_ids=["cache"],
            label="Features",
        ),
        timeout=30,
    )

    if response.reason == "CANCELLED":
        return []

    # Check which options were selected
    results = []
    if "cache" in response.result:
        results.append(Phrase("Enabled: Caching"))
    if "retry" in response.result:
        results.append(Phrase("Enabled: Auto Retry"))
    if "log" in response.result:
        results.append(Phrase("Enabled: Verbose Logging"))
    return results


@register_transform(
    display_name="Button Control Example [New Maltego Integration]",
    description="Demonstrates choice prompt with button controls",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def button_control_example(
    entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Shows buttons for quick action selection.
    """
    response = await context.choice_prompt(
        message=f"How do you want to process '{entity.value}'?",
        options=[
            PromptItem("process", "Process Now"),
            PromptItem("queue", "Add to Queue"),
            PromptItem("skip", "Skip"),
        ],
        control=ButtonControl(default_option_id="process"),
        timeout=30,
    )

    if response.reason == "CANCELLED" or "skip" in response.result:
        return None

    if "process" in response.result:
        return Phrase(f"Processing: {entity.value}")
    elif "queue" in response.result:
        return Phrase(f"Queued: {entity.value}")

    return None


@register_transform(
    display_name="Multi-Choice Prompt Example [New Maltego Integration]",
    description="Demonstrates multiple controls in a single prompt",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def multi_choice_control_example(
    entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Shows multiple controls in a single dialog using multi_choice_prompt.
    """
    checkbox_options = ["cache", "retry", "parallel"]

    response = await context.multi_choice_prompt(
        message="Configure your search:",
        controls=[
            DropdownControl(
                control_id="source",
                label="Data Source",
                options=[
                    PromptItem("api1", "Primary API"),
                    PromptItem("api2", "Secondary API"),
                    PromptItem("api3", "Tertiary API"),
                ],
                default_option_id="api1",
            ),
            CheckboxControl(
                control_id="options",
                label="Options",
                options=[
                    PromptItem("cache", "Use Cache"),
                    PromptItem("retry", "Auto Retry"),
                    PromptItem("parallel", "Parallel Requests"),
                ],
                default_option_ids=["cache"],
            ),
        ],
        timeout=60,
    )

    result = Phrase(f"Search configured for: {entity.value}")

    source_selections = response.result.get("source", {})
    if source_selections:
        selected_source = list(source_selections.keys())[0]
        result.set_property("source", selected_source, display_name="API Source")

    options_selections = response.result.get("options", {})
    for option in checkbox_options:
        is_selected = option in options_selections
        result.set_property(option, is_selected, display_name=option.title())

    return result


@register_transform(
    display_name="Input Prompt Example [New Maltego Integration]",
    description="Demonstrates collecting various input types from users",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def input_prompt_example(
    graph: MaltegoGraph, context: MaltegoContext
) -> MaltegoGraph:
    """
    Shows an input prompt collecting various types of data.
    """
    inputs: List[InputPromptItem] = [
        # String input with default value
        InputPromptItem("search_term", InputTypes.str, "default search"),
        # Integer input
        InputPromptItem("max_results", InputTypes.int, 10),
        # Boolean input (checkbox)
        InputPromptItem("include_historical", InputTypes.boolean, False),
        # Date input
        InputPromptItem("start_date", InputTypes.date),
        # Multiple strings
        InputPromptItem("tags", InputTypes.str_list, ["tag1", "tag2"]),
    ]

    response = await context.input_prompt(
        message="Configure search parameters:", items=inputs, timeout=120
    )

    # Create entity with collected inputs as properties
    result_entity = Phrase("Search Configuration")
    for key, value in response.result.items():
        result_entity.set_property(
            key, value, display_name=key.replace("_", " ").title()
        )

    # Add to graph
    if graph.entities:
        graph.add_child(graph.entities[0], result_entity)
    else:
        graph.add_entity(result_entity)

    return graph


@register_transform(
    display_name="Date Range Prompt Example [New Maltego Integration]",
    description="Demonstrates date and datetime range input prompts",
    transform_set=TRANSFORM_SET,
    interactive=True,
)
async def date_range_prompt_example(entity: Phrase, context: MaltegoContext) -> Phrase:
    """
    Shows how to collect date range inputs for time-bounded searches.
    """
    inputs: List[InputPromptItem] = [
        InputPromptItem("date_range", InputTypes.datetime_range),
    ]

    response = await context.input_prompt(
        message="Select the time range for your search:", items=inputs, timeout=60
    )

    date_range = response.result.get("date_range")
    result = Phrase(f"Searching {entity.value}")

    if date_range:
        result.set_property("date_range", str(date_range), display_name="Date Range")

    return result


if __name__ == "__main__":
    from maltego.server import MaltegoServerSettings, run_server

    server_settings = MaltegoServerSettings(
        server_name="Maltego Transform Server", ns="acme", author="Acme"
    )
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=False,
        settings=server_settings,
        log_level="INFO",
    )
