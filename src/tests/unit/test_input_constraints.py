from datetime import date, datetime, timezone

import httpx
import pytest
from starlette.requests import Request

from maltego.model.context import MaltegoContext
from maltego.model.entity import _MaltegoEntityProperty
from maltego.model.graph import MaltegoGraph
from maltego.model.input_constraints import EntityTypeConstraint, PropertyValueEquals
from maltego.model.input_constraints.property.regex import PropertyValueMatchesRegex
from maltego.model.types import daterange
from tests.conftest import (Alias, ComplexEntity2 as ComplexEntity, Domain, Person, RichEntity,
                            RichEntityChild, TEST_INPUT_CONSTRAINT_ALIAS,
                            TEST_INPUT_CONSTRAINT_ALIAS_NOT, TEST_INPUT_CONSTRAINT_REGEX, UA_4_10_0)

pytestmark = pytest.mark.unit

CONTEXT = MaltegoContext(
    graph=MaltegoGraph(),
    request=Request(
        {"type": "http", "headers": {}},
    ),
)


@pytest.fixture(autouse=True)
def setup_teardown_function():
    # SETUP

    yield "running_test"
    # TEARDOWN

    # Refresh the context after each test to clear log messages
    global CONTEXT
    CONTEXT = MaltegoContext(
        graph=MaltegoGraph(),
        request=Request(
            {"type": "http", "headers": {}},
        ),
    )


CONSTRAINT_FAILURE_MESSAGE_1 = """ListEvaluation passed: Evaluated 2 entities ✓ EntitySatisfiesAll passed | ✓ EntityTypeConstraint passed: Entity type 'maltego.Alias' matches expected 'maltego.Alias' | ✓ EntityHasPropertySatisfying passed: Looking for property satisfying: PropertySatisfiesAll | | ✓ PropertySatisfiesAll passed | | | ✓ PropertyValueStringMatch passed: Property value 'username11' starts with 'username11' | | | ✓ PropertyNameEquals passed: Property name 'alias' matches 'alias' ✓ EntitySatisfiesAll passed | ✓ EntityTypeConstraint passed: Entity type 'maltego.Alias' matches expected 'maltego.Alias' | ✓ EntityHasPropertySatisfying passed: Looking for property satisfying: PropertySatisfiesAll | | ✓ PropertySatisfiesAll passed | | | ✓ PropertyValueStringMatch passed: Property value 'USERNAME11' starts with 'username11' | | | ✓ PropertyNameEquals passed: Property name 'alias' matches 'alias'"""
CONSTRAINT_FAILURE_MESSAGE_5 = """GraphEvaluation failed: Evaluated 2 entities in graph ✓ EntitySatisfiesAll passed | ✓ EntityTypeConstraint passed: Entity type 'maltego.Alias' matches expected 'maltego.Alias' | ✓ EntityHasPropertySatisfying passed: Looking for property satisfying: PropertySatisfiesAll | | ✓ PropertySatisfiesAll passed | | | ✓ PropertyValueStringMatch passed: Property value 'username11' starts with 'username11' | | | ✓ PropertyNameEquals passed: Property name 'alias' matches 'alias' ✗ EntitySatisfiesAll failed | ✗ EntityTypeConstraint failed: Expected entity type 'maltego.Alias', got 'maltego.Person' | ✗ EntityHasPropertySatisfying failed: Looking for property satisfying: PropertySatisfiesAll | | ✗ PropertySatisfiesAll failed: No specific property passed the constraint."""


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.contract
async def test_property_constraints(
        async_client_example_server: httpx.AsyncClient,
) -> None:
    """
    Gets the following transforms from the example server,
    - entity_property_constraints1
    - entity_property_constraints2
    - entity_property_constraints3
    - entity_property_constraints4
    Asserts the input constraints are serialized as expected
    """
    desktop_client_including_headers = UA_4_10_0
    response = await async_client_example_server.get(
        "/api/v3/transforms", headers=desktop_client_including_headers
    )
    transforms = response.json().get("transforms")
    prop_constraint_transforms = [
        t
        for t in transforms
        if isinstance(t.get("input"), dict) and "inputConstraint" in t["input"]
    ]

    assert all(
        [
            transform.get("sets")[0]
            == "Pytest Entity Property Constraint Test Transforms"
            for transform in prop_constraint_transforms
        ]
    )
    assert isinstance(transforms, list)
    assert "entity_property_constraints1" in prop_constraint_transforms[0].get("name")
    assert prop_constraint_transforms[0].get("input") == {
        "type": "ENTITY",
        "typeIds": ["maltego.Unknown"],
        "inputConstraint": {
            "constraints": [
                {"type": "entity_type_constraint", "entity_type": "maltego.Alias"},
                {
                    "constraints": [
                        {
                            "type": "property_value_string_match",
                            "match_type": "startswith",
                            "value": "username11",
                            "ignore_case": True,
                        },
                        {
                            "type": "property_name_equals",
                            "value": "alias",
                            "ignore_case": False,
                        },
                    ],
                    "operation": "all",
                    "type": "property_satisfies_all",
                },
            ],
            "operation": "all",
            "type": "entity_satisfies_all",
        },
    }

    assert "entity_property_constraints2" in prop_constraint_transforms[1].get("name")
    assert prop_constraint_transforms[1].get("input") == {
        "type": "GRAPH",
        "typeIds": ["maltego.Unknown"],
        "inputConstraint": {
            "constraints": [
                {
                    "constraints": [
                        {
                            "type": "entity_type_constraint",
                            "entity_type": "maltego.Phrase",
                        },
                        {
                            "type": "entity_type_constraint",
                            "entity_type": "maltego.Alias",
                        },
                    ],
                    "operation": "any",
                    "type": "entity_satisfies_any",
                },
                {
                    "constraints": [
                        {
                            "constraints": [
                                {
                                    "type": "property_name_equals",
                                    "value": "text",
                                    "ignore_case": False,
                                },
                                {
                                    "type": "property_value_equals",
                                    "value": "myalias11",
                                    "ignore_case": False,
                                },
                            ],
                            "operation": "all",
                            "type": "property_satisfies_all",
                        },
                        {
                            "constraints": [
                                {
                                    "type": "property_name_equals",
                                    "value": "alias",
                                    "ignore_case": False,
                                },
                                {
                                    "type": "property_value_equals",
                                    "value": "myalias11",
                                    "ignore_case": False,
                                },
                            ],
                            "operation": "all",
                            "type": "property_satisfies_all",
                        },
                    ],
                    "operation": "any",
                    "type": "property_satisfies_any",
                },
            ],
            "operation": "all",
            "type": "entity_satisfies_all",
        },
    }

    assert "entity_property_constraints3" in prop_constraint_transforms[2].get("name")
    assert prop_constraint_transforms[2].get("input") == {
        "type": "ENTITY",
        "typeIds": ["maltego.Unknown"],
        "inputConstraint": {
            "constraints": [
                {
                    "constraints": [
                        {
                            "type": "property_name_equals",
                            "value": "alias",
                            "ignore_case": False,
                        }
                    ],
                    "operation": "all",
                    "type": "property_satisfies_all",
                }
            ],
            "operation": "all",
            "type": "entity_satisfies_all",
        },
    }

    assert "entity_property_constraints4" in prop_constraint_transforms[3].get("name")
    assert prop_constraint_transforms[3].get("input") == {
        "type": "ENTITY",
        "typeIds": ["maltego.Domain"],
        "inputConstraint": {
            "constraints": [
                {
                    "constraints": [
                        {
                            "type": "property_value_matches_regex",
                            "regex": "^(?!-)[A-Za-z0-9-]{1,63}\\.[A-Za-z]{2,6}$",
                        }
                    ],
                    "operation": "all",
                    "type": "property_satisfies_all",
                }
            ],
            "operation": "all",
            "type": "entity_satisfies_all",
        },
    }


@pytest.mark.parametrize(
    "input_value, constraint, expected_outcome",
    [
        # Test with a single entity
        (
                Alias("username11"),  # transform input
                TEST_INPUT_CONSTRAINT_ALIAS,  # input constraint
                True,  # Expected outcome
        ),
        # Test with a list of entities
        ([Alias("username11"), Alias("USERNAME11")], TEST_INPUT_CONSTRAINT_ALIAS, True),
        # Test with a graph
        (
                MaltegoGraph(entities=[Alias("username11"), Alias("USERNAME11")]),
                TEST_INPUT_CONSTRAINT_ALIAS,
                True,
        ),
        # Test with a single entity, not meeting constraints
        (Alias("othername"), TEST_INPUT_CONSTRAINT_ALIAS, False),
        # Test with a list of entities, not meeting the criteria
        (
                [Alias("username11"), Person("USERNAME11")],
                TEST_INPUT_CONSTRAINT_ALIAS,
                False,
        ),
        # Test with a graph, not meeting the criteria
        (
                MaltegoGraph(entities=[Alias("username11"), Person("USERNAME11")]),
                TEST_INPUT_CONSTRAINT_ALIAS,
                False,
        ),
        # Test NOT with an entity, meeting the criteria
        (Alias("username44"), TEST_INPUT_CONSTRAINT_ALIAS_NOT, True),
        # Test NOT with an entity, not meeting the criteria
        (Alias("username11"), TEST_INPUT_CONSTRAINT_ALIAS_NOT, False),
        # Test regex with an entity, meeting the criteria
        (Domain("maltego.com"), TEST_INPUT_CONSTRAINT_REGEX, True),
    ],
)
def test_eval(input_value, constraint, expected_outcome):
    assert (
            constraint.eval(input_value) == expected_outcome
    ), f"Expected {expected_outcome} but got {not expected_outcome}"


@pytest.mark.parametrize(
    "input_value, constraint, expected_outcome, expected_string_representation",
    [
        # Test with a single entity
        (
                Alias("username11"),  # transform input
                TEST_INPUT_CONSTRAINT_ALIAS,  # input constraint
                True,  # Expected outcome
                None
        ),
        # Test with a list of entities
        ([Alias("username11"), Alias("USERNAME11")], TEST_INPUT_CONSTRAINT_ALIAS, True, CONSTRAINT_FAILURE_MESSAGE_1),
        # Test with a graph
        (
                MaltegoGraph(entities=[Alias("username11"), Alias("USERNAME11")]),
                TEST_INPUT_CONSTRAINT_ALIAS,
                True,
                None
        ),
        # Test with a single entity, not meeting constraints
        (Alias("othername"), TEST_INPUT_CONSTRAINT_ALIAS, False, None),
        # Test with a list of entities, not meeting the criteria
        (
                [Alias("username11"), Person("USERNAME11")],
                TEST_INPUT_CONSTRAINT_ALIAS,
                False,
                None
        ),
        # Test with a graph, not meeting the criteria
        (
                MaltegoGraph(entities=[Alias("username11"), Person("USERNAME11")]),
                TEST_INPUT_CONSTRAINT_ALIAS,
                False,
                CONSTRAINT_FAILURE_MESSAGE_5
        ),
        # Test NOT with an entity, meeting the criteria
        (Alias("username44"), TEST_INPUT_CONSTRAINT_ALIAS_NOT, True, None),
        # Test NOT with an entity, not meeting the criteria
        (Alias("username11"), TEST_INPUT_CONSTRAINT_ALIAS_NOT, False, None),
        # Test regex with an entity, meeting the criteria
        (Domain("maltego.com"), TEST_INPUT_CONSTRAINT_REGEX, True, None),
    ],
)
def test_eval_with_hierarchy(input_value, constraint, expected_outcome, expected_string_representation):
    result = constraint.eval_with_hierarchy(input_value)
    assert (
            result.success == expected_outcome
    ), f"Expected {expected_outcome} but got {not expected_outcome}"

    if expected_string_representation:
        assert (
                result.to_string().replace("\n", "").strip() == expected_string_representation
        )


def prop(entity: ComplexEntity, name: str) -> _MaltegoEntityProperty:
    """Grab a property by name (as used in your entity fields)."""
    return entity.get_properties()[name]


@pytest.fixture
def entity() -> ComplexEntity:
    e = ComplexEntity("str property value")

    # Scalars
    e.int_property = 321
    e.float_property = 42.23
    e.bool_property = True
    e.date_property = date(2025, 9, 5)
    e.datetime_property = datetime(2025, 9, 5, 12, 30, 0, tzinfo=timezone.utc)

    # Dateranges
    e.daterange_property = daterange(
        start=datetime(1999, 5, 19, 0, 0, 0, tzinfo=timezone.utc),
        end=datetime(2021, 5, 19, 0, 0, 0, tzinfo=timezone.utc),
    )
    e.daterange2_property = daterange(date_range=daterange.Ranges.last_10_years)

    # Lists
    e.str_list_property = ["Foo", "Bar", "Baz"]
    e.int_list_property = [42, 23]
    e.float_list_property = [42.23, 23.42]
    e.bool_list_property = [True, False]

    # Strings (url/color already strings under the hood)
    e.url = "https://www.example.com"  # type: ignore
    e.color = "#ffff00"
    return e


@pytest.mark.parametrize(
    "prop_name, rhs, ignore_case",
    [
        ("str_property", "str property value", False),
        ("int", 321, False),
        ("float", 42.23, False),
        ("bool", True, False),
        ("url", "https://www.example.com", False),
        ("color", "#ffff00", False),
    ],
)
def test_scalar_properties_equal(entity, prop_name, rhs, ignore_case):
    p = prop(entity, prop_name)
    c = PropertyValueEquals(value=rhs, ignore_case=ignore_case)
    assert c.evaluate(p) is True
    assert c.evaluate_with_hierarchy(p).success is True


def test_scalar_case_insensitive(entity):
    p = prop(entity, "str_property")
    c = PropertyValueEquals(value="STR PROPERTY VALUE", ignore_case=True)
    assert c.evaluate(p) is True


def test_property_value_equals_rejects_list():
    with pytest.raises(ValueError):
        PropertyValueEquals(value=[42.23, 23.42])


def test_property_value_equals_rejects_rhs_none():
    with pytest.raises(ValueError):
        PropertyValueEquals(value=None)


def test_property_value_equals_rejects_maltego_entity():
    with pytest.raises(TypeError):
        PropertyValueEquals(value=Alias("something"), ignore_case=False)


def test_date_property_is_rejected(entity):
    with pytest.raises(TypeError):
        PropertyValueEquals(value=date(2025, 9, 5))


def test_datetime_property_is_rejected(entity):
    with pytest.raises(TypeError):
        PropertyValueEquals(value=datetime(2025, 9, 5, 12, 30, 0, tzinfo=timezone.utc))


def test_daterange_property_is_rejected(entity):
    with pytest.raises(TypeError):
        PropertyValueEquals(value=daterange(date_range=daterange.Ranges.last_10_years))


# Following factories create entities with different type/genealogy setups
def make_rich():
    return RichEntity("test rich entity")


def make_child_with_genealogy():
    return RichEntityChild("test rich entity child")


# Test cases: (factory, required_type, expected, description, expected_message)
CASES = [
    (
        make_rich,
        "maltego.RichEntity",
        True,
        "Entity type 'maltego.RichEntity' matches expected 'maltego.RichEntity'",
        "matches self",
    ),
    (
        make_child_with_genealogy,
        "maltego.RichEntity",
        True,
        "Entity type 'maltego.RichEntityChild' matches expected 'maltego.RichEntity'",
        "matches parent",
    ),
    (
        make_child_with_genealogy,
        "maltego.DNSName",
        False,
        "Expected entity type 'maltego.DNSName', got 'maltego.RichEntity, maltego.RichEntityChild'",
        "does not match",
    ),
]


@pytest.mark.parametrize(
    "factory, required_type, expected, expected_message, _",
    CASES,
    ids=[c[4] for c in CASES],
)
def test_entity_type_constraint_evaluate(factory, required_type, expected, expected_message, _):
    entity = factory()
    c = EntityTypeConstraint(entity_type=required_type)
    assert c.evaluate(entity) is expected


@pytest.mark.parametrize(
    "factory, required_type, expected, expected_message, _",
    CASES,
    ids=[c[4] for c in CASES],
)
def test_entity_type_constraint_evaluate_with_hierarchy(factory, required_type, expected, expected_message, _):
    entity = factory()
    c = EntityTypeConstraint(entity_type=required_type)
    result = c.evaluate_with_hierarchy(entity)

    assert result.success is expected
    assert result.message == expected_message


def test_boolean_false_value_in_regex_constraint(entity):
    p = prop(entity, "bool")
    p.value = False

    c = PropertyValueMatchesRegex(regex="^False$")
    assert c.evaluate(p) is True, "Boolean False should be converted to string 'False' for regex matching"

    result = c.evaluate_with_hierarchy(p)
    assert result.success is True
    assert "False" in result.message


def test_boolean_true_value_in_regex_constraint(entity):
    p = prop(entity, "bool")

    c = PropertyValueMatchesRegex(regex="^True$")
    assert c.evaluate(p) is True, "Boolean True should be converted to string 'True' for regex matching"

    result = c.evaluate_with_hierarchy(p)
    assert result.success is True
    assert "True" in result.message


def test_boolean_false_does_not_match_wrong_regex(entity):
    p = prop(entity, "bool")
    p.value = False

    c = PropertyValueMatchesRegex(regex="^True$")
    assert c.evaluate(p) is False, "Boolean False should not match regex for 'True'"

    result = c.evaluate_with_hierarchy(p)
    assert result.success is False
