# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=unused-argument
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
import asyncio
import datetime
import json
import uuid
import random

from maltego.model.transform import MaltegoClient, MaltegoClientFilter
from tests.conftest import ExtendedPhraseListStr, Person, Phrase, Document, Domain
from maltego.model.context import MaltegoContext
from maltego.model.link import MaltegoLinkProperty
from maltego.model.transform.setting import TransformSetting
from maltego.model.entity import MaltegoEntity, OverlayPositions, OverlayTypes, Bookmark
from maltego.model.graph import MaltegoGraph
from maltego.model.types import daterange, LinkColor, LinkThickness, LinkStyle
from maltego.server import register_transform
from maltego.model.exception import (
    MaltegoHTTPDataProviderAPIKeyInvalid,
    MaltegoHTTPDataProviderInvalidResponse,
    MaltegoHTTPDataProviderUnavailable
)
from tests.example import OAUTH, OAUTH_2_0
from tests.example.transforms.entities.entities import (
    ComplexEntity, DateTimeComposite, GrandChild1Entity, IconUrlEntity, PersonWithLocationAndDateTime, SimpleEntity,
    Parent1Entity, Parent2Entity,
    Child1Entity, Child2Entity, Child3Entity,
    PersonComposite, LocationComposite, PersonWithLocation,
    Number
)
from maltego.util import IntegrationClient

TEST_RUN = False

__all__ = [
    "transform",
    "transform_list",
    "transform_union",
    "transform_list_union",
    "transform_custom_entity",
    "transform_rich",
    "transform_all_settings",
    "transform_str_annotations",
    "transform_oauth",
    "transform_oauth_2_0",
    "display_field_test",
    "exception_test",
    "exception_test_2",
    "exception_test_3",
    "exception_test_4",
    "transform_sync",
    "transform_async_gen",
    "test_client_version_filtering_for_desktop",
    "test_client_version_filtering_for_browser",
    "test_client_version_filtering",
    "extended_phrase_list_str_input_test",
    "transform_identity_info",
]

DEFAULT_INTERFACE_TRANSFORM_SET = "Interface Test Transforms [Maltego]"
EXCEPTION_TRANSFORM_SET = "Test Exception Transforms [Maltego]"
MARKDOWN = """
# H1
This
## H2
is
### H3
Markdown

1. Lets
2. Test
3. Lists
- and
- points

---

[Link to example.com!](https://www.example.com)

**bold text**
*italicized text*
> blockquote

```
#!/usr/bin/python
# Code goes here ...
```

# Markdown Table

|          	| Price/Month 	| Requests/s 	| Max Requests/Month 	| Support   	|
|----------	|-------------	|------------	|--------------------	|-----------	|
| Free     	| 0           	| 5          	| inf                	| Community 	|
| Start    	| 9           	| 200        	| 1.000.000          	| Community 	|
| Basic    	| 49          	| 200        	| 5.000.000          	| Community 	|
| Advanced 	| 249         	| 200        	| 25.000.000         	| Standard  	|

"""


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform(input_entity: Phrase) -> Phrase:
    return Phrase(input_entity.value)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_pong(input_entity: Phrase) -> Phrase:
    return Phrase(str(uuid.uuid4()))


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_parent1(input_entity: Parent1Entity) -> Phrase:
    return Phrase(f"transform_parent1: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_parent2(input_entity: Parent2Entity) -> Phrase:
    return Phrase(f"transform_parent2: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_child1(input_entity: Child1Entity) -> Phrase:
    return Phrase(f"transform_child1: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_child2(input_entity: Child2Entity) -> Phrase:
    return Phrase(f"transform_child2: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_child3(input_entity: Child3Entity) -> Phrase:
    return Phrase(f"transform_child3: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_grandchild1(input_entity: GrandChild1Entity) -> Phrase:
    return Phrase(f"transform_child3: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_parent_union(input_entity: Union[Parent1Entity, Parent2Entity]) -> Phrase:
    return Phrase(f"transform_child_union: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_person_composite(input_entity: PersonComposite) -> Phrase:
    return Phrase(f"transform_person_composite: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_location_composite(input_entity: LocationComposite) -> Phrase:
    return Phrase(f"transform_location_composite: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_date_time_composite(input_entity: DateTimeComposite) -> Phrase:
    return Phrase(f"transform_date_time_composite: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_person_with_location(input_entity: PersonWithLocation) -> Phrase:
    return Phrase(f"transform_person_with_location: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_person_with_location_and_date_time(input_entity: PersonWithLocationAndDateTime) -> Phrase:
    return Phrase(f"transform_person_with_location_and_date_time: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_person(input_entity: Person) -> Phrase:
    return Phrase(f"transform_person: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_list(input_entity: Phrase) -> List[Phrase]:
    return [Phrase(input_entity.value + f"_{i}") for i in range(0, 3)]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_union(input_entity: Union[Phrase, Person]) -> Union[Phrase, Person]:
    return Person(input_entity.value)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_list_union(input_entity: Phrase) -> List[Union[Phrase, Person]]:
    res = Phrase(input_entity.value)
    res_p = Person(input_entity.value)
    return [res, res_p]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_custom_entity(input_entity: SimpleEntity) -> ComplexEntity:
    return ComplexEntity(value=input_entity.value)


@register_transform(
    display_name="Rich Transform",
    name="rich_transform",
    description="Baz",
    author="author@example.com",
    location_relevance="local",
    ns="robin",
    owner="Maltego Technologies",
    disclaimer="Disclaimer",
    version="1.0.0",
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="rich_str",
            display_name="Test string Transform Setting",
            type="string",
            optional=False,
            auth=True,
            popup=True,
            default_value="Test",
            is_global=True,
            is_oauth=True
        ),
    ]
)
async def transform_rich(input_entity: Phrase) -> ComplexEntity:
    return_entity = ComplexEntity(value=input_entity.value)
    return_entity.add_overlay(
        OverlayTypes.IMAGE,
        OverlayPositions.WEST,
        "url_property"
    )
    return_entity.add_overlay(
        OverlayTypes.IMAGE,
        OverlayPositions.SOUTH,
        "url_property"
    )
    return_entity.add_overlay(
        OverlayTypes.COLOR,
        OverlayPositions.NORTHWEST,
        "color_property"
    )
    return_entity.add_overlay(
        OverlayTypes.COLOR,
        OverlayPositions.SOUTHWEST,
        "color_property"
    )
    return_entity.add_overlay(
        OverlayTypes.TEXT,
        OverlayPositions.CENTER,
        "str_property"
    )
    return_entity.set_property(
        "url_property", "https://www.maltego.com/favicon.ico")
    return_entity.set_property("color_property", "green")
    return_entity.set_property("str_property", "oof")
    return_entity.set_property("float", 99.66)
    return_entity.set_property("int", 18)
    return_entity.set_property("bool", True)
    return_entity.set_property("date", datetime.date.fromtimestamp(0))
    return_entity.set_property(
        "datetime",
        datetime.datetime.fromtimestamp(0)
    )
    return_entity.set_property("daterange", daterange(
        start=datetime.datetime.fromtimestamp(0),
        end=datetime.datetime.fromtimestamp(100000)
    ))
    return_entity.set_property(
        "daterange2",
        daterange(date_range=daterange.Ranges.last_15_minutes)
    )
    return_entity.set_property("string_list", ["oof", "rab"])
    return_entity.set_property("float_list", [1.1, 2.2])
    return_entity.set_property("int_list", [1, 2, 3])
    return_entity.set_property("bool_list", [True, True, False])

    return return_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="str",
            display_name="Test string Transform Setting",
            type="string",
            default_value="foo"
        ),
        TransformSetting(
            name="double",
            display_name="Test double Transform Setting",
            type="double",
            default_value=42.23
        ),
        TransformSetting(
            name="int", display_name="Test int Transform Setting", type="int",
            default_value=42
        ),
        TransformSetting(
            name="boolean", display_name="Test boolean Transform Setting", type="boolean",
            default_value=False
        ),
        TransformSetting(
            name="date", display_name="Test date Transform Setting", type="date",
            default_value=datetime.date.fromtimestamp(0)
        ),
        TransformSetting(
            name="datetime", display_name="Test datetime Transform Setting", type="datetime",
            default_value=datetime.datetime.fromtimestamp(0)
        ),
        TransformSetting(
            name="daterange",
            display_name="Test daterange Transform Setting",
            type="daterange",
            default_value=daterange(
                start=datetime.datetime.fromtimestamp(0),
                end=datetime.datetime.fromtimestamp(10 * (24 * 60 * 60))
            )
        ),
        TransformSetting(
            name="daterange_relative",
            display_name="Test daterange relative Transform Setting",
            type="daterange",
            default_value=daterange(
                date_range=daterange.Ranges.last_12_hours
            )
        ),
        TransformSetting(
            name="str_list",
            display_name="Test string list Transform Setting",
            type="string[]",
            default_value=["Setting 1", "Setting 2"]
        ),
        TransformSetting(
            name="double_list",
            display_name="Test double list Transform Setting",
            type="double[]",
            default_value=[1.0, 2.0]
        ),
        TransformSetting(
            name="int_list",
            display_name="Test int list Transform Setting",
            type="int[]",
            default_value=[1, 2]
        ),
        TransformSetting(
            name="boolean_list",
            display_name="Test boolean list Transform Setting",
            type="boolean[]",
            default_value=[True, False]
        ),
        TransformSetting(
            name="date_list",
            display_name="Test date list Transform Setting",
            type="date[]",
            default_value=[
                datetime.date(year=2023, month=6, day=28), datetime.date(
                    year=2023, month=6, day=28)
            ]
        ),
        TransformSetting(
            name="setting_global_legacy",
            display_name="Test global transform Setting",
            type="string",
            is_global_setting=True
        ),
        TransformSetting(
            name="setting_global",
            display_name="Test global transform Setting",
            type="string",
            is_global=True
        ),
        # TransformSetting(name="url", display_name="Test url Transform Setting", type="url"),
        # TransformSetting(name="color", display_name="Test color Transform Setting", type="Color"),
    ]
)
async def transform_all_settings(input_entity: Phrase, settings: Dict[str, Any]) -> Phrase:
    output_entity = Phrase(input_entity.value)
    output_entity.add_display_field("settings", str(settings))
    return output_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def transform_str_annotations(
    input_entity: MaltegoEntity["maltego.Phrase"]  # type: ignore
) -> MaltegoEntity["maltego.Phrase"]:  # type: ignore
    return Phrase(input_entity.value)  # type: ignore


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def transform_unknown_input(
    input_entity: MaltegoEntity
) -> Phrase:
    return Phrase(f"transform_unknown_input: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def transform_unknown_input_list(
    input_entities: List[MaltegoEntity]
) -> Phrase:
    return Phrase(str(len(input_entities)))


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    authenticator=OAUTH
)
async def transform_oauth(input_entity: Phrase, settings: Dict[str, Any]) -> Phrase:
    if settings[OAUTH.access_token_input] is None:
        raise ValueError(
            "settings[OAUTH.access_token_input] needs to be not None")
    assert OAUTH.access_token_input in settings
    return Phrase(settings[OAUTH.access_token_input])


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    authenticator=OAUTH_2_0
)
async def transform_oauth_2_0(input_entity: Phrase, settings: Dict[str, Any]) -> Phrase:
    if settings[OAUTH_2_0.access_token_input] is None:
        raise ValueError(
            "settings[OAUTH_2_0.access_token_input] needs to be not None")
    assert OAUTH_2_0.access_token_input in settings
    return Phrase(settings[OAUTH_2_0.access_token_input])


@register_transform(
    display_name="Display Field Test",
    description="Display Field/Label Test",
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def display_field_test(input_entity: Phrase) -> Phrase:
    res = Phrase(input_entity.value)
    res.add_display_field("Test Display Field", "<b>foo</b>")
    res.add_display_label("Test Display Label", "<b>bar</b>")
    res.add_display_field("Test Markdown Display Field",
                          MARKDOWN, content_type="text/markdown")
    res.add_display_label(
        "Test Markdown Display Label",
        "**Test Display <br> Label Value**",
        content_type="text/markdown"
    )

    return res


@register_transform(
    transform_set=EXCEPTION_TRANSFORM_SET
)
async def exception_test(input_entity: Phrase) -> Phrase:
    raise ValueError(input_entity.value)


@register_transform(
    transform_set=EXCEPTION_TRANSFORM_SET
)
async def exception_test_2(input_entity: Phrase) -> Phrase:
    raise MaltegoHTTPDataProviderUnavailable(detail=input_entity.value)


@register_transform(
    transform_set=EXCEPTION_TRANSFORM_SET
)
async def exception_test_3(input_entity: Phrase) -> Phrase:
    raise MaltegoHTTPDataProviderAPIKeyInvalid(detail=input_entity.value)


@register_transform(
    transform_set=EXCEPTION_TRANSFORM_SET
)
async def exception_test_4(input_entity: Phrase) -> Phrase:
    raise MaltegoHTTPDataProviderInvalidResponse(
        detail=input_entity.value
    )


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
def transform_sync(input_entity: Phrase) -> Phrase:
    return Phrase(input_entity.value)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_async(input_entity: Phrase) -> Phrase:
    await asyncio.sleep(1)
    return Phrase(input_entity.value)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_async_gen(input_entity: Phrase) -> AsyncGenerator[Phrase, None]:
    for i in range(0, 5):
        yield Phrase(input_entity.value + f"_{i}")


@register_transform(
    name="Graph"
)
async def transform_graph(graph: MaltegoGraph[Any]) -> MaltegoGraph[Any]:
    previous_entity = graph.add_entity(Phrase("new_entity"))
    for i in range(0, 5):
        entity = graph.add_entity(Phrase(f"new_entity_{i}"))
        graph.add_link(previous_entity, entity)
        previous_entity = entity
    return graph


@register_transform(
    name="GraphPhrase"
)
async def transform_graph_phrase(graph: MaltegoGraph[Phrase]) -> MaltegoGraph[Any]:
    graph.add_entity(Phrase(str(len(graph.entities))))
    return graph


@register_transform(
    name="GraphPhraseAndPerson"
)
async def transform_graph_phrase_person(graph: MaltegoGraph[Union[Phrase, Person]]) -> MaltegoGraph[Any]:
    graph.add_entity(Phrase(str(len(graph.entities))))
    return graph


@register_transform(
    name="List"
)
async def transform_list_in(test_param_name: List[Phrase]) -> List[Phrase]:
    return [Phrase(entity.value + f"_{idx}") for idx, entity in enumerate(test_param_name)]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_async_gen_long(input_entity: Phrase) -> AsyncGenerator[Phrase, None]:
    for _ in range(0, 100):
        yield Phrase(str(uuid.uuid4()))
        await asyncio.sleep(1)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_update_entity(input_entity: Phrase) -> Phrase:
    input_entity.value = "Baz"
    return input_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_logging(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    input_entity.value = "Baz"
    context.log.debug("debug")
    context.log.inform("inform")
    context.log.fatal("fatal")
    context.log.partial("partial")
    return input_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_properties_test(input_entity: ComplexEntity) -> ComplexEntity:
    return_entity = ComplexEntity(value=input_entity.value + "_")
    value: Optional[Union[str, int, float, datetime.date, daterange]] = None
    for _, entity_property in input_entity.get_properties().items():
        if entity_property.name is None:
            continue
        if entity_property.name == "str_property":
            value = str(entity_property.value) + "_"
        else:
            value = entity_property.value
        return_entity.set_property(entity_property.name, value)  # type: ignore
    return return_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_properties_test(graph: MaltegoGraph[Any]) -> MaltegoGraph[Any]:

    available_link_styles = [
        LinkStyle.DASHED,
        LinkStyle.DASHDOT,
        LinkStyle.NORMAL,
        LinkStyle.DOTTED
    ]
    available_link_colors = [
        LinkColor.NONE,
        LinkColor.RED,
        LinkColor.GREEN,
        LinkColor.BLUE,
        LinkColor.PURPLE,
        LinkColor.YELLOW
    ]
    available_link_thicknesses = [
        LinkThickness.THICKNESS_DEFAULT,
        LinkThickness.THICKNESS_1,
        LinkThickness.THICKNESS_2,
        LinkThickness.THICKNESS_3,
        LinkThickness.THICKNESS_4
    ]
    i = 0
    for _, thick in enumerate(available_link_thicknesses):
        for color in available_link_colors:
            for style in available_link_styles:
                entity_a = graph.add_entity(Phrase(f"first entity {i}"))
                entity_b = graph.add_entity(Phrase(f"second entity {i}"))
                graph.add_link(
                    source=entity_a,
                    target=entity_b,
                    color=color,
                    thickness=thick,
                    style=style,
                    label=f'Style {style}, Color {color}, Thickness {thick.value}'
                )
                i = i + 1

    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_entity_bookmark_test(input_entity: Phrase) -> List[Phrase]:
    available_bookmarks = [
        Bookmark.NONE,
        Bookmark.RED,
        Bookmark.BLUE,
        Bookmark.YELLOW,
        Bookmark.PURPLE,
        Bookmark.GREEN,
    ]
    return_entities = []
    for bookmark in available_bookmarks:
        entity = Phrase(value=f"Bookmark: {bookmark.name} ({bookmark.value})")
        entity.bookmark = bookmark
        return_entities.append(entity)
    return return_entities


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_entity_properties_test(input_entity: Phrase) -> Phrase:
    property_types_entity = Phrase(value="All Property Types")
    property_types_entity.set_property("str", "example", "String property")
    property_types_entity.set_property("str_arr", ["example 1", "example 2"])
    property_types_entity.set_property("float", 1.0, "Float property")
    property_types_entity.set_property("float_arr", [1.0, 2.0])
    property_types_entity.set_property("int", 1, "Int property")
    property_types_entity.set_property("int_arr", [1, 2])
    property_types_entity.set_property("bool", True, "Bool property")
    property_types_entity.set_property(
        "bool_arr", [True, False], "Bool properties")
    property_types_entity.set_property(
        "date", datetime.date.today(), "Date property")
    property_types_entity.set_property(
        "date_arr", [datetime.date.today(), datetime.date.today()], "Date properties")
    property_types_entity.set_property(
        "datetime",
        datetime.datetime.fromtimestamp(10000000),
        "Datetime property"
    )
    from_date = datetime.date.fromisoformat('2010-09-07')
    to_date = datetime.date.fromisoformat('2013-02-27')
    daterange_from_to_end_date = daterange(start=from_date, end=to_date)
    property_types_entity.set_property("daterange from start to end date", daterange_from_to_end_date,
                                       "Daterange from start date to end date")
    daterange_from_range = daterange(
        date_range=daterange.Ranges.last_15_minutes)
    property_types_entity.set_property(
        "daterange from range", daterange_from_range, "Daterange from range")
    property_types_entity.set_property(
        "str", None, "None value property (currently not visible in client)")
    return property_types_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_kwargs(input_entity: Phrase, asd: int, **kwargs: Dict[str, Any]) -> Phrase:
    return Phrase(f"{kwargs}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_default(input_entity: Phrase, foo_: int, extra: int = 42) -> Phrase:
    return Phrase(f"{extra}")


class PhraseChild(Phrase):  # type: ignore
    test: str = "foo"


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_phrase_child(input_entity: PhraseChild) -> Phrase:
    entity = PhraseChild("foo")
    return Phrase(f"{entity} {entity.get_properties()}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    name="test.transform.with.period"
)
async def transform_with_period(input_entity: Phrase) -> Phrase:
    return input_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_add_remove_graph_entities(graph: MaltegoGraph[Any]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    parent = Phrase(value="Parent")
    count = 100
    children = []
    for i in range(count):
        child = graph.add_entity(Phrase(value=f"Entity {i}"))
        children.append(graph.add_child(parent, child))
    yield graph
    if not TEST_RUN:
        await asyncio.sleep(3)

    for child in children:
        graph.delete_entity(child)
    yield graph
    if not TEST_RUN:
        await asyncio.sleep(3)

    for child in children:
        graph.add_child(parent, child)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_delete_all_links(graph: MaltegoGraph[Any]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    for entity in graph.entities:
        links_from = graph.get_links_from(entity)
        for link in links_from:
            graph.delete_link(link)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_create_mesh_links(graph: MaltegoGraph[Any]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    for entity in graph.entities:
        links_from = graph.get_links_from(entity)
        for link in links_from:
            graph.delete_link(link)
    yield graph
    if not TEST_RUN:
        await asyncio.sleep(3)

    for entity_1 in graph.entities:
        for entity_2 in graph.entities:
            if entity_1.maltego_entity_id != entity_2.maltego_entity_id:
                graph.add_link(entity_1, entity_2)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_add_remove_graph_links(graph: MaltegoGraph[Any]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    parent = Phrase(value="Parent")
    count = 100
    children = []
    for i in range(count):
        child = graph.add_entity(Phrase(value=f"Entity {i}"))
        children.append(graph.add_child(parent, child))
    yield graph
    if not TEST_RUN:
        await asyncio.sleep(3)

    for entity in graph.entities:
        links_from = graph.get_links_from(entity)
        for link in links_from:
            graph.delete_link(link)
    yield graph
    if not TEST_RUN:
        await asyncio.sleep(3)

    for child in children:
        graph.add_link(parent, child)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_update_graph_entities(graph: MaltegoGraph[Any]) -> MaltegoGraph[Any]:
    all_graph_entities = graph.get_entities_of_type(Phrase.TYPE_NAME)
    for entity in all_graph_entities:
        entity.set_property(
            "text",
            f"{datetime.datetime.fromtimestamp(10000000)}"
        )
        entity.set_property(
            "update-date-time",
            datetime.datetime.fromtimestamp(11000000)
        )
        entity.set_property(
            "all-graph-entity-count",
            len(all_graph_entities)
        )
        entity.set_property(
            "overlay-color-property",
            random.choice(["RED", "BLUE", "GREEN"])
        )
        entity.set_property("status", "updated")
        entity.value = "Entity updated " + str(uuid.uuid4())
        entity.weight = 5
        entity.note = "add a note"
        entity.bookmark = Bookmark.GREEN
        entity.add_display_field("Test Display Field", "<b>foo</b>")
        entity.add_display_label("Test Display Label", "<b>bar</b>")
        entity.add_display_field(
            "Test Markdown Display Field", MARKDOWN, content_type="text/markdown")
        entity.add_display_label(
            "Test Markdown Display Label",
            "**Test Display <br> Label Value**",
            content_type="text/markdown"
        )
        entity.add_overlay(
            overlay_type=OverlayTypes.COLOR,
            position=OverlayPositions.NORTH,
            property_name="overlay-color-property"
        )
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_update_graph_links(graph: MaltegoGraph[Any]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    all_graph_links = graph.links
    for link in all_graph_links:
        link.set_property(
            "maltego.link.label",
            f"{datetime.datetime.fromtimestamp(10000000)}"
        )
        link.set_property(
            "update-date-time",
            datetime.datetime.fromtimestamp(11000000)
        )
        link.set_property("all-graph-link-count", len(all_graph_links))
        link.set_property("status", "updated")
    yield graph


def distance(str_a: str, str_b: str) -> int:
    if not str_a:
        return len(str_b)
    if not str_b:
        return len(str_a)
    if str_a[0] == str_b[0]:
        return distance(str_a[1:], str_b[1:])
    return 1 + min([distance(str_a, str_b[1:]), distance(str_a[1:], str_b), distance(str_a[1:], str_b[1:])])


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_merge_phrases(graph: MaltegoGraph[Phrase]) -> AsyncGenerator[MaltegoGraph[Any], None]:
    all_entities = graph.entities
    for _, entity_x in enumerate(all_entities):
        for _, entity_y in enumerate(all_entities):
            if entity_x == entity_y:
                continue
            dis = distance(entity_x.value, entity_y.value)
            if dis == 1:
                graph.delete_entity(entity_y)
                all_entities.remove(entity_y)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    metadata={
        "foo": "bar",
        "example": "metadata",
    }
)
async def transform_with_metadata(input_entity: Phrase) -> Phrase:
    return input_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def transform_add_entities_to_context_graph(
        input_entity: Phrase,
        context: MaltegoContext) -> AsyncGenerator[MaltegoGraph[Any], None]:
    parent = input_entity
    graph = context.graph
    assert graph is not None
    phrase_1 = Phrase(value="Phrase 1")
    graph.add_entity(phrase_1)
    graph.add_link(parent, phrase_1)
    yield graph
    phrase_2 = Phrase(value="Phrase 2")
    graph.add_link(parent, phrase_2)
    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def transform_icon_url(
    input_entity: Phrase,
    context: MaltegoContext
) -> IconUrlEntity:
    return IconUrlEntity(
        value="foo",
        icon_url="https://maltego.com/favicon.ico"
    )


@register_transform(
    name="list2"
)
async def transform_list_in_2(test_param_name: list[Phrase]) -> list[Phrase]:
    return [Phrase(entity.value + f"_{idx}") for idx, entity in enumerate(test_param_name)]


@register_transform(
    name="link_properties_from_entity"
)
async def transform_link_properties_from_entity(input_entity: Phrase) -> Phrase:  # pylint: disable=unused-argument
    result = Phrase(str(uuid.uuid4()))
    result.link_label = "Label"
    result.link_thickness = LinkThickness.THICKNESS_3
    result.link_color = LinkColor.GREEN
    result.link_style = LinkStyle.DOTTED
    return result


@register_transform(
)
async def transform_union_input_without_set(
        input_entity: Union[Person, Phrase, Document],
        settings: dict,
        limit: int,
        context: MaltegoContext,
) -> List[Phrase]:
    return Phrase(f"transform_union_input_without_set: {input_entity.TYPE_NAME}")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_union_input_with_set(
        input_entity: Union[Person, Phrase, Document],
        settings: dict,
        limit: int,
        context: MaltegoContext,
) -> List[Phrase]:
    return Phrase(f"transform_union_input_with_set: {input_entity.TYPE_NAME}")


@register_transform(
    display_name="Test Log 1",
    description="Test Log 1"
)
async def test_log1(input_entity: Phrase,
                    settings: dict,
                    limit: int,
                    context: MaltegoContext,
                    ) -> list[Phrase]:
    results = []
    for i in range(0, 12):
        results.append(Phrase(f"test {i}"))

    context.log.inform("test log")
    context.log.inform(str(len(results)))

    return results


@register_transform(
    display_name="Test Log 2",
    description="Test Log 2"
)
async def test_log2(input_entity: Phrase,
                    settings: dict,
                    limit: int,
                    context: MaltegoContext,
                    ) -> list[Phrase]:
    results = []
    for i in range(0, 12):
        results.append(Phrase(f"test {i}"))
        context.log.inform(f"test {i}")

    context.log.inform(str(len(results)))

    return results


@register_transform(
    display_name="Test Log 3",
    description="Test Log 3"
)
async def test_log3(input_entity: Phrase,
                    settings: dict,
                    limit: int,
                    context: MaltegoContext,
                    ) -> list[Phrase]:
    results = []
    for i in range(0, 25):
        results.append(Phrase(f"test {i}"))

    context.log.inform("test log")
    context.log.inform(str(len(results)))

    return results


@register_transform(
    display_name="Test Log 4",
    description="Test Log 4"
)
async def test_log4(input_entity: Phrase,
                    settings: dict,
                    limit: int,
                    context: MaltegoContext,
                    ) -> list[Phrase]:
    results = []
    for i in range(0, 25):
        results.append(Phrase(f"test {i}"))
        context.log.inform(f"test {i}")

    context.log.inform(str(len(results)))

    return results


def response_hook(response, context):
    print(f"{response} {context}")


client = IntegrationClient(response_hooks=[response_hook])


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_hook(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    await client.get("http://example.com", context)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_merging(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    graph: MaltegoGraph = context.graph
    num = 5
    for i in range(0, num):
        entity = Phrase(str(i))
        graph.add_entity(entity)
        link_uuid = str(uuid.uuid4())
        for _ in range(0, num):
            graph.add_link(input_entity, entity, properties={
                           "foo": MaltegoLinkProperty(name="foo", value=link_uuid)})


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_merging_2(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    graph: MaltegoGraph = context.graph
    num = 5
    for i in range(0, num):
        entity = Phrase(str(uuid.uuid4()))
        graph.add_entity(entity)
        link_uuid = str(uuid.uuid4())
        for _ in range(0, num):
            graph.add_link(input_entity, entity, label=link_uuid)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_merging_3(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    graph: MaltegoGraph = context.graph
    num = 5
    for i in range(0, num):
        entity = Phrase(str(uuid.uuid4()))
        graph.add_entity(entity)
        for j in range(0, num):
            graph.add_link(input_entity, entity, label=str(j))


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_merging_4(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    graph: MaltegoGraph = context.graph
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    link_uuid1 = str(uuid.uuid4())
    link_uuid2 = str(uuid.uuid4())
    graph.add_link(input_entity, entity, label=link_uuid1, is_reversed=True)
    graph.add_link(input_entity, entity, label=link_uuid2, is_reversed=True)
    graph.add_link(input_entity, entity, label=link_uuid1, is_reversed=False)
    graph.add_link(input_entity, entity, label=link_uuid2, is_reversed=False)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_link_reversed(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    graph: MaltegoGraph = context.graph
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    graph.add_link(input_entity, entity, is_reversed=True)


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_strict_property(input_entity: Phrase, context: MaltegoContext) -> List[Phrase]:
    entity_1 = Phrase("name")
    entity_1.set_property(name="strict", value=1, matching_rule="strict")
    entity_2 = Phrase("name")
    entity_2.set_property(name="strict", value=2, matching_rule="strict")
    return [entity_1, entity_2]


async def transform_output_graph1(graph: MaltegoGraph) -> MaltegoGraph:
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_output_graph2(graph: MaltegoGraph) -> Optional[MaltegoGraph]:
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_output_graph3(graph: MaltegoGraph) -> MaltegoGraph[Union[Phrase, Person]]:
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_output_graph4(graph: MaltegoGraph) -> Optional[MaltegoGraph[Union[Phrase, Person]]]:
    entity = Phrase(str(uuid.uuid4()))
    graph.add_entity(entity)
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_delete_entity(entity: Phrase, context: MaltegoContext) -> MaltegoGraph:
    graph = context.graph
    graph.delete_entity(entity)
    return Phrase(f"FOO {uuid.uuid4()}")
CHOICES = [
    Phrase,
    Domain,
    Person,
    ComplexEntity,
    SimpleEntity
]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_return_random_entities(
    entity: Number,
) -> List[Union[Phrase, Domain, Person, ComplexEntity, SimpleEntity]]:
    count = int(entity.value)
    result_set = []
    for i in range(0, count):
        choice = random.choice(CHOICES)
        result_set.append(choice(str(i) + "_" + str(uuid.uuid4())))
    return result_set


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_delete_graph(graph: MaltegoGraph, context: MaltegoContext) -> MaltegoGraph:
    for entity in graph.entities:
        graph.delete_entity(entity)
    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_child3_inheritance_test(input_entity: Child3Entity) -> List[Child3Entity]:
    input_entity.set_property("child1_text", "a")
    input_entity.set_property("parent1_text", "b")
    input_entity.set_property("parent1_text2", "c")

    input_entity.set_property("child2_text", "d")
    input_entity.set_property("parent2_text", "e")

    input_entity.set_property("child3_text", "f")

    new = Child3Entity(str(uuid.uuid4()))
    new.child1_text = "g"
    new.parent1_text = "h"
    new.parent1_text2 = "i"

    new.child2_text = "j"
    new.parent2_text = "k"

    new.child3_text = "l"
    return [input_entity, new]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_update_bookmark(graph: MaltegoGraph) -> MaltegoGraph:

    available_bookmarks = [
        Bookmark.RED,
        Bookmark.YELLOW,
        Bookmark.PURPLE,
        Bookmark.BLUE,
        Bookmark.GREEN,
        Bookmark.NONE,
    ]

    random.shuffle(available_bookmarks)

    if len(graph.entities) < len(available_bookmarks):
        for i in range(len(available_bookmarks) - len(graph.entities)):
            graph.add_entity(Phrase(str(i)))

    for bookmark in available_bookmarks:
        i = available_bookmarks.index(bookmark)
        entity = graph.entities.pop(i)
        entity.bookmark = bookmark
        entity.value = f"{bookmark.name} {i}"

    return graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_async_edit(
        input_entity: Phrase, context: MaltegoContext
) -> AsyncGenerator[MaltegoGraph[Any], None]:

    graph = context.graph

    input_entity.set_property("text", "edited " + str(uuid.uuid4()))
    yield graph

    if not TEST_RUN:
        await asyncio.sleep(1)

    graph.delete_entity(input_entity)

    if not TEST_RUN:
        await asyncio.sleep(1)

    input_entity.bookmark = Bookmark.RED
    graph.add_entity(input_entity)

    yield graph


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET
)
async def transform_read_display_names(
        input_entity: MaltegoEntity, context: MaltegoContext
) -> List[Phrase]:
    return [Phrase(prop.display_name) for prop in input_entity.get_properties().values()]


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    client_filter=MaltegoClientFilter(
        max_clients=[{"name": "Maltego Desktop", "version": (4, 8, 1)}],
        min_clients=[{"name": "Maltego Desktop", "version": (4, 8, 0)}],
    )
)
async def test_client_version_filtering_for_desktop(
        input_entity: MaltegoEntity, context: MaltegoContext
) -> MaltegoEntity:
    return Phrase(f"{context.user_agent} ({context.ua})")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    client_filter=MaltegoClientFilter(
        max_clients=[MaltegoClient(
            name="Maltego Graph Browser", version=(3, 0, 1))],
        min_clients=[MaltegoClient(
            name="Maltego Graph Browser", version=(3, 0, 0))],
    )
)
async def test_client_version_filtering_for_browser(
        input_entity: MaltegoEntity, context: MaltegoContext
) -> MaltegoEntity:
    return Phrase(f"{context.user_agent} ({context.ua})")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    client_filter=MaltegoClientFilter(
        max_clients=[("Maltego Desktop", (4, 8, 1)),
                     ("Maltego Graph Browser", (3, 0, 1))],
        min_clients=[("Maltego Desktop", (4, 8, 0)),
                     ("Maltego Graph Browser", (3, 0, 0))],
    )
)
async def test_client_version_filtering(
        input_entity: MaltegoEntity, context: MaltegoContext
) -> MaltegoEntity:
    return Phrase(f"{context.user_agent} ({context.ua})")


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
)
async def extended_phrase_list_str_input_test(
        input_entity: ExtendedPhraseListStr,
        context: MaltegoContext,
) -> ExtendedPhraseListStr:
    return input_entity


@register_transform(
    transform_set=DEFAULT_INTERFACE_TRANSFORM_SET,
    display_name="Debug Auth Context",
    description="Returns Phrase entities with auth, identity, org, and request context debug information"
)
async def transform_identity_info(
    input_entity: Phrase,
    context: MaltegoContext
) -> List[Phrase]:
    """
    Example transform demonstrating access to auth debug data on MaltegoContext.

    Returns Phrase entities containing validated identity, auth claims, auth payload,
    unverified JWT claims, and request context useful while developing auth integrations.
    """
    identity = context.identity
    auth_available = any(
        value is not None
        for value in (
            identity,
            context.auth_claims,
            context.auth_payload,
            context.rate_limit_key,
        )
    )

    identity_data = identity.to_dict() if identity is not None else None
    claim_organization = None
    if isinstance(context.auth_claims, dict):
        claim_organization = context.auth_claims.get("organization")

    results = [
        Phrase(f"Auth Available: {str(auth_available).lower()}"),
        Phrase(_debug_json("Input Entity", {
            "type": input_entity.TYPE_NAME,
            "value": input_entity.value,
        })),
        Phrase(_debug_json("Organization", {
            "identity_org_id": identity.org_id if identity else None,
            "claim_organization": claim_organization,
        })),
        Phrase(_debug_json("Identity", identity_data)),
        Phrase(_debug_json("Auth Claims", context.auth_claims)),
        Phrase(_debug_json("Auth Payload", context.auth_payload)),
        Phrase(_debug_json("Unverified Auth Claims", context.unverified_auth_claims)),
        Phrase(f"Rate Limit Key: {context.rate_limit_key or 'N/A'}"),
        Phrase(f"Remote IP: {context.remote_ip or 'N/A'}"),
        Phrase(f"User Agent: {context.user_agent or 'N/A'}"),
    ]

    return results


def _debug_json(label: str, value: Any) -> str:
    return f"{label}: {json.dumps(value, sort_keys=True, default=str)}"
