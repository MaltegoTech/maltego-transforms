# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=unused-argument
import datetime
from typing import List, Union

from tests.example.transforms.entities.entities import ComplexEntity
from tests.example.transforms.constraint_fixtures import PropertyValueUnknownTest
from maltego.model.graph import MaltegoGraph
from maltego.model.input_constraints import (
    ConstraintStringMatchType,
    EntityHasPropertySatisfying,
    EntitySatisfiesAll,
    EntitySatisfiesAny,
    EntitySatisfiesNone,
    EntityTypeConstraint,
    PropertyNameEquals,
    PropertySatisfiesAll,
    PropertySatisfiesAny,
    PropertyValueEquals,
    PropertyValueMatchesRegex,
    PropertyValueStringMatch,
    PropertyTypeEquals,
)
from maltego.model.types import daterange
from maltego.server import MaltegoEntity, register_transform
from maltego.model.context import MaltegoContext
from tests.conftest import Domain, Person, Phrase

TEST_RUN = False

__all__ = [
    "entity_property_constraints1",
    "entity_property_constraints2",
    "entity_property_constraints3",
    "entity_property_constraints4",
    "entity_property_constraints5",
    "entity_property_constraints6",
    "entity_property_constraints7",
    "build_complex_entity_example",
    "test_has_properties1",
    "test_has_properties2",
    "test_has_properties3",
    "test_has_properties4",
    "test_has_properties5",
    "test_has_properties6",
    "test_has_properties7",
]

ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS = "Entity Property Constraint Test Transforms"
HAS_PROPERTY_TRANSFORM_SET = "Has Property Test Transforms"


@register_transform(
    display_name="Entity Property Constraints Transform 1",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match Alias entities with alias property value 'username11'",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Alias"),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[
                        PropertyValueStringMatch(
                            value="username11",
                            ignore_case=True,
                            match_type=ConstraintStringMatchType.STARTSWITH,
                        ),
                        PropertyNameEquals(value="alias"),
                    ]
                )
            ),
        ]
    ),
)
def entity_property_constraints1(input_entity: MaltegoEntity):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 2",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="In the input graph, match either a Person or Alias entity with either alias or text property value 'my_alias'",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntitySatisfiesAny(
                constraints=[
                    EntityTypeConstraint(entity_type="maltego.Phrase"),
                    EntityTypeConstraint(entity_type="maltego.Alias"),
                ]
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAny(
                    constraints=[
                        PropertySatisfiesAll(
                            constraints=[
                                PropertyNameEquals(value="text"),
                                PropertyValueEquals(value="myalias11"),
                            ]
                        ),
                        PropertySatisfiesAll(
                            constraints=[
                                PropertyNameEquals(value="alias"),
                                PropertyValueEquals(value="myalias11"),
                            ]
                        ),
                    ]
                )
            ),
        ]
    ),
)
def entity_property_constraints2(input_graph: MaltegoGraph):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 3",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match entities that have a property named 'alias'",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[PropertyNameEquals(value="alias")]
                )
            )
        ]
    ),
)
def entity_property_constraints3(input_entity: MaltegoEntity):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 4",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match Domain entities that have an 'fqdn' property value matching given regex",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[
                        PropertyValueMatchesRegex(
                            regex=r"^(?!-)[A-Za-z0-9-]{1,63}\.[A-Za-z]{2,6}$"
                        )
                    ]
                )
            )
        ]
    ),
)
def entity_property_constraints4(input_entity: Domain):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 5",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match entities that do NOT have alias='username11'",
    input_constraint=EntitySatisfiesNone(
        constraints=[
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[PropertyValueEquals(value="username11")]
                )
            )
        ]
    ),
)
def entity_property_constraints5(
    input_entity: MaltegoEntity, settings: dict, limit: int, context: MaltegoContext
):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 6",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match entities that have property with type DATE",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[PropertyTypeEquals(value="DATE")]
                )
            )
        ]
    ),
)
def entity_property_constraints6(input_entity: MaltegoEntity):
    return Phrase("whatevs")


@register_transform(
    display_name="Entity Property Constraints Transform 7 (ComplexEntity all props)",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Match ComplexEntity when ALL example properties equal the expected values.",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.complexEntity"),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="str_property"),
                    PropertyValueEquals(value="str property value"),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="int"),
                    PropertyValueEquals(value=321),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="float"),
                    PropertyValueEquals(value=42.23),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="bool"),
                    PropertyValueEquals(value=True),
                ])
            ),
            # EntityHasPropertySatisfying(
            #     constraint=PropertySatisfiesAll(constraints=[
            #         PropertyNameEquals(value="date"),
            #         PropertyValueEquals(value=datetime.date(2025, 9, 5)),
            #     ])
            # ),
            # EntityHasPropertySatisfying(
            #     constraint=PropertySatisfiesAll(constraints=[
            #         PropertyNameEquals(value="datetime"),
            #         PropertyValueEquals(
            #             value=datetime.datetime(2025, 9, 5, 12, 30, 0, tzinfo=datetime.timezone.utc)
            #         ),
            #     ])
            # ),
            # EntityHasPropertySatisfying(
            #     constraint=PropertySatisfiesAll(constraints=[
            #         PropertyNameEquals(value="daterange"),
            #         PropertyValueEquals(
            #             value=daterange(
            #                 start=datetime.datetime(1999, 5, 19, 0, 0, 0, tzinfo=datetime.timezone.utc),
            #                 end=datetime.datetime(2021, 5, 19, 0, 0, 0, tzinfo=datetime.timezone.utc),
            #             )
            #         ),
            #     ])
            # ),
            # EntityHasPropertySatisfying(
            #     constraint=PropertySatisfiesAll(constraints=[
            #         PropertyNameEquals(value="daterange2"),
            #         PropertyValueEquals(
            #             value=daterange(date_range=daterange.Ranges.last_10_years)
            #         ),
            #     ])
            # ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="string_list"),
                    PropertyValueEquals(value="Foo"),
                    PropertyValueEquals(value="Bar"),
                    PropertyValueEquals(value="Baz"),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="float_list"),
                    PropertyValueEquals(value=42.23),
                    PropertyValueEquals(value=23.42),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="int_list"),
                    PropertyValueEquals(value=42),
                    PropertyValueEquals(value=23),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="bool_list"),
                    PropertyValueEquals(value=True),
                    PropertyValueEquals(value=False),
                ])
            ),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(constraints=[
                    PropertyNameEquals(value="url"),
                    PropertyValueEquals(value="https://www.example.com"),
                ])
            ),
            # EntityHasPropertySatisfying(
            #     constraint=PropertySatisfiesAll(constraints=[
            #         PropertyNameEquals(value="color"),
            #         PropertyValueEquals(value="#ffff00"),
            #     ])
            # ),
        ]
    ),
)
def entity_property_constraints7(input_entity: MaltegoEntity):
    # for now we do not support date, datetime, daterange, color property value comparisons
    return Phrase("ComplexEntity matched all property constraints")


@register_transform(
    display_name="Entity Property Constraints Transform 8 (Build ComplexEntity)",
    transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
    description="Emit a ComplexEntity populated with all example property values.",
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Phrase"),
        ]
    ),
)
def build_complex_entity_example(input_entity: MaltegoEntity) -> ComplexEntity:
    e = ComplexEntity("str property value")

    e.int_property = 321
    e.float_property = 42.23
    e.bool_property = True
    e.date_property = datetime.date(2025, 9, 5)
    e.datetime_property = datetime.datetime(2025, 9, 5, 12, 30, 0, tzinfo=datetime.timezone.utc)

    e.daterange_property = daterange(
        start=datetime.datetime(1999, 5, 19, 0, 0, 0, tzinfo=datetime.timezone.utc),
        end=datetime.datetime(2021, 5, 19, 0, 0, 0, tzinfo=datetime.timezone.utc),
    )
    e.daterange2_property = daterange(date_range=daterange.Ranges.last_10_years)

    e.str_list_property = ["Foo", "Bar", "Baz"]
    e.int_list_property = [42, 23]
    e.float_list_property = [42.23, 23.42]
    e.bool_list_property = [True, False]

    e.url = "https://www.example.com"
    e.color = "#ffff00"

    return e

# commenting this out because it breaks discovery when testing 5.0.0 dev locally
# @register_transform(
#     display_name="Entity Property Constraints Transform 9",
#     transform_set=ENTITY_PROPERTY_CONSTRAINT_TRANSFORMS,
#     description="This is copied from Transform 2 to test PropertyValueUnknownTest",
#     input_constraint=EntitySatisfiesAll(
#         constraints=[
#             EntitySatisfiesAny(
#                 constraints=[
#                     EntityTypeConstraint(entity_type="maltego.Phrase"),
#                     EntityTypeConstraint(entity_type="maltego.Alias"),
#                 ]
#             ),
#             EntityHasPropertySatisfying(
#                 constraint=PropertySatisfiesAny(
#                     constraints=[
#                         PropertySatisfiesAll(
#                             constraints=[
#                                 PropertyNameEquals(value="text"),
#                                 PropertyValueUnknownTest(value="test"),
#                             ]
#                         ),
#                         PropertySatisfiesAll(
#                             constraints=[
#                                 PropertyNameEquals(value="alias"),
#                                 PropertyValueEquals(value="myalias11"),
#                             ]
#                         ),
#                     ]
#                 )
#             ),
#         ]
#     ),
# )
# def entity_property_constraints9(input_graph: MaltegoGraph):
#     return Phrase("whatevs")



@register_transform(
    display_name="Has Property Test 1",
    any_properties=["foo", "bar"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties1(
    input_entity: Phrase,
) -> Phrase:
    return input_entity


@register_transform(
    display_name="Has Property Test 2",
    any_properties=["foo"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties2(
    input_entity: Phrase,
) -> Phrase:
    return input_entity


@register_transform(
    display_name="Has Property Test 3",
    any_properties=["foo"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties3(
    input_entities: List[Phrase],
) -> List[Phrase]:
    return input_entities


@register_transform(
    display_name="Has Property Test 4",
    any_properties=["foo"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties4(
    input_entity: MaltegoEntity,
) -> MaltegoEntity:
    return input_entity


@register_transform(
    display_name="Has Property Test 5",
    any_properties=["foo"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties5(
    graph: MaltegoGraph[Phrase],
) -> MaltegoGraph:
    return graph


@register_transform(
    display_name="Has Property Test 6",
    any_properties=["foo"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties6(
    entity: Union[Person, Phrase],
) -> Union[Person, Phrase]:
    return entity


@register_transform(
    display_name="Has Property Test 7",
    all_properties=["foo", "bar"],
    transform_set=HAS_PROPERTY_TRANSFORM_SET,
)
async def test_has_properties7(
    input_entity: MaltegoEntity,
) -> MaltegoEntity:
    return input_entity
