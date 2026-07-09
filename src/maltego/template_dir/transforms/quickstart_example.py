import asyncio
from typing import Any, Dict, List, Optional

from maltego.entities import Person, Phrase
from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity, MaltegoEntityConfig
from maltego.model.entity.property import MaltegoEntityProperty as MEF
from maltego.server import (
    MaltegoGraph,
    MaltegoServerSettings,
    TransformSetting,
    daterange,
    register_entity,
    register_transform,
    run_server,
)


@register_entity
class Number(MaltegoEntity):
    """A simple numeric entity for demonstration."""

    TYPE_NAME = "maltego.Number"

    Config = MaltegoEntityConfig(
        value_property="number",
        display_property="number",
        display_name="Number",
        display_name_plural="Numbers",
        description="An integer number",
        icon_resource="hashtag",
    )

    number: int = MEF(name="number", display_name="Number", value=42)


@register_entity
class StaffMember(Person):
    """
    Demonstrates entity inheritance with custom configuration.
    Extends Person with an employee ID and custom display settings.
    """

    TYPE_NAME = "maltego.StaffMember"

    Config = MaltegoEntityConfig(
        value_property="person.fullname",
        display_property="person.fullname",
        display_name="Acme Staff Member",
        display_name_plural="Acme Staff Members",
        description="A person who works at Acme corp.",
        icon_resource="License",
    )

    employee_id: str = MEF(
        name="employee_id",
        display_name="Employee ID",
        value="-1",
        sample_value="1234",
        description="A unique ID for each employee",
    )


TRANSFORM_SET = "New Maltego Integration"


@register_transform(
    display_name="Single Entity Demo [New Maltego Integration]",
    description="Demonstrates single entity input and output",
    transform_set=TRANSFORM_SET,
)
async def single_entity_demo(
    input_entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Simplest transform: takes one entity, returns one entity.

    If multiple entities are selected, the transform runs concurrently on each.
    """
    value = input_entity.value
    if not value:
        return None

    return Phrase(f"Processed: {value}")


@register_transform(
    display_name="Sum Numbers [New Maltego Integration]",
    description="Takes multiple Number entities and returns their sum",
    transform_set=TRANSFORM_SET,
)
async def sum_demo_numbers(
    entities: List[Number], context: MaltegoContext
) -> Optional[Number]:
    """
    Demonstrates list input - transform receives multiple entities at once.
    """
    if not entities:
        return None

    total = sum(int(entity.number or 0) for entity in entities)
    context.log.inform(f"Sum of {len(entities)} numbers: {total}")

    return Number(total)


@register_transform(
    display_name="Graph Info [New Maltego Integration]",
    description="Shows information about the selected graph",
    transform_set=TRANSFORM_SET,
)
async def graph_info(graph: MaltegoGraph, context: MaltegoContext) -> Phrase:
    """
    Demonstrates graph input - access to entities AND links.
    """
    entity_count = len(graph.entities)
    link_count = len(graph.links)

    context.log.inform(f"Graph has {entity_count} entities and {link_count} links")

    result = Phrase(f"Graph: {entity_count} entities, {link_count} links")
    result.set_property("entity_count", entity_count, display_name="Entities")
    result.set_property("link_count", link_count, display_name="Links")

    return result


@register_transform(
    display_name="Graph Numbers Only [New Maltego Integration]",
    description="Only accepts graphs containing Number entities",
    transform_set=TRANSFORM_SET,
)
async def graph_demo_numbers_only(
    graph: MaltegoGraph[Number], context: MaltegoContext
) -> Phrase:
    """
    Demonstrates typed graph input - only accepts graphs of specific entity type.
    """
    total = sum(int(entity.number or 0) for entity in graph.entities)
    return Phrase(f"Sum from graph: {total}")


@register_transform(
    display_name="All Setting Types Demo [New Maltego Integration]",
    description="Demonstrates all available transform setting types",
    transform_set=TRANSFORM_SET,
    settings=[
        # String
        TransformSetting(
            name="str_setting",
            display_name="Text Input",
            type="string",
            default_value="default text",
            popup=True,
        ),
        # Integer
        TransformSetting(
            name="int_setting",
            display_name="Number Input",
            type="int",
            default_value=10,
            popup=True,
        ),
        # Float
        TransformSetting(
            name="double_setting",
            display_name="Decimal Input",
            type="double",
            default_value=3.14,
            popup=True,
        ),
        # Boolean
        TransformSetting(
            name="bool_setting",
            display_name="Enable Feature",
            type="boolean",
            default_value=True,
            popup=True,
        ),
        # Date
        TransformSetting(
            name="date_setting",
            display_name="Select Date",
            type="date",
            popup=True,
        ),
        # Auth setting (global, shared across transforms)
        TransformSetting(
            name="api_key",
            display_name="API Key",
            auth=True,
            is_global=True,
            optional=True,
            popup=True,
        ),
    ],
)
async def all_settings_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    Shows how to access different setting types.
    """
    text = settings.get("str_setting", "")
    number = settings.get("int_setting", 0)
    decimal = settings.get("double_setting", 0.0)
    enabled = settings.get("bool_setting", False)
    date = settings.get("date_setting")
    api_key = settings.get("api_key", "")

    result = Phrase(f"Settings received for: {input_entity.value}")
    result.set_property("text", text, display_name="Text")
    result.set_property("number", number, display_name="Number")
    result.set_property("decimal", decimal, display_name="Decimal")
    result.set_property("enabled", str(enabled), display_name="Enabled")
    result.set_property("date", str(date) if date else "Not set", display_name="Date")
    result.set_property(
        "has_api_key", "Yes" if api_key else "No", display_name="Has API Key"
    )

    return result


@register_transform(
    display_name="List Settings Demo [New Maltego Integration]",
    description="Demonstrates list-type settings",
    transform_set=TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="tags",
            display_name="Tags",
            type=TransformSetting.Types.str_list,
            default_value=["tag1", "tag2"],
            popup=True,
        ),
        TransformSetting(
            name="ports",
            display_name="Ports",
            type=TransformSetting.Types.int_list,
            default_value=[80, 443, 8080],
            popup=True,
        ),
    ],
)
async def list_settings_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> List[Phrase]:
    """
    Demonstrates list-type settings.
    """
    tags = settings.get("tags", [])
    ports = settings.get("ports", [])

    results = []
    for tag in tags:
        results.append(Phrase(f"Tag: {tag}"))
    for port in ports:
        results.append(Phrase(f"Port: {port}"))

    return results


@register_transform(
    display_name="Date Range Demo [New Maltego Integration]",
    description="Demonstrates date range settings",
    transform_set=TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="time_window",
            display_name="Time Window",
            type=TransformSetting.Types.datetime_range,
            default_value=daterange(date_range=daterange.Ranges.last_24_hours),
            popup=True,
        ),
    ],
)
async def daterange_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    Demonstrates date range settings with relative values.
    """
    time_window = settings.get("time_window")
    result = Phrase(f"Date range for: {input_entity.value}")
    result.set_property(
        "time_window",
        str(time_window) if time_window else "Not set",
        display_name="Time Window",
    )
    return result


@register_transform(
    display_name="Get Employee ID [New Maltego Integration]",
    description="Works only on StaffMember entities",
    transform_set=TRANSFORM_SET,
)
async def get_staff_member_id(input_entity: StaffMember) -> Phrase:
    """
    Demonstrates transform on inherited entity type.
    Only available for StaffMember entities.
    """
    return Phrase(f"Employee ID: {input_entity.employee_id}")


@register_transform(
    display_name="Get Person Name [New Maltego Integration]",
    description="Works on Person and any entity inheriting from Person",
    transform_set=TRANSFORM_SET,
)
async def get_person_name(input_entity: Person) -> Phrase:
    """
    Works on Person AND StaffMember (since StaffMember inherits from Person).
    """
    return Phrase(f"Name: {input_entity.fullname}")


@register_transform(
    display_name="Streaming Demo [New Maltego Integration]",
    description="Yields results one at a time",
    transform_set=TRANSFORM_SET,
)
async def streaming_demo(input_entity: Phrase, context: MaltegoContext):
    """
    Demonstrates streaming output using async generator.
    """
    for i in range(5):
        context.log.inform(f"Processing item {i + 1}/5")
        yield Phrase(f"Result {i + 1}: {input_entity.value}")
        await asyncio.sleep(0.5)  # Simulate slow processing


if __name__ == "__main__":
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
