# Copyright (c) Maltego Technologies GmbH.
from datetime import date, datetime
from typing import Any, Dict

import pytest

from maltego.server import MaltegoLink
from maltego.model.types import LinkColor, LinkStyle, LinkThickness, daterange
from maltego._helper import create_maltego_id

pytestmark = pytest.mark.unit


def test_create_simple_link():
    link = MaltegoLink(create_maltego_id(), create_maltego_id())
    assert len(link.get_properties()) == 0
    assert link.maltego_link_id is not None
    assert link.color is LinkColor.NONE.value
    assert link.style is LinkStyle.NORMAL.value
    assert link.thickness is LinkThickness.THICKNESS_DEFAULT.value


def test_create_customized_link():
    link_color = LinkColor.RED
    link_style = LinkStyle.DASHED
    link_thickness = LinkThickness.THICKNESS_2
    link_label = 'foo'
    link = MaltegoLink(
        source_id=create_maltego_id(),
        target_id=create_maltego_id(),
        is_reversed=True,
        color=link_color,
        style=link_style,
        thickness=link_thickness,
        label=link_label
    )
    assert link.is_reversed is True
    assert link.source_id is not None
    assert link.target_id is not None
    assert link.maltego_link_id is not None
    assert link.color is link_color.hex_color()
    assert link.style is link_style.value
    assert link.thickness is link_thickness.value
    assert link.label is link_label
    properties = link.get_properties()
    assert link.REVERSED_PROPERTY_ID in properties and properties[link.REVERSED_PROPERTY_ID]
    assert link.STYLE_PROPERTY_ID in properties
    assert properties[link.STYLE_PROPERTY_ID].value == link_style.value
    assert link.COLOR_PROPERTY_ID in properties
    assert properties[link.COLOR_PROPERTY_ID].value == link_color.hex_color()
    assert link.THICKNESS_PROPERTY_ID in properties
    assert properties[link.THICKNESS_PROPERTY_ID].value == link_thickness.value
    assert link.LABEL_PROPERTY_ID in properties
    assert properties[link.LABEL_PROPERTY_ID].value == link_label


def test_set_properties_on_link():
    link = MaltegoLink(
        source_id=create_maltego_id(),
        target_id=create_maltego_id(),
    )
    assert len(link.get_properties()) == 0
    link.is_reversed = False
    link.color = LinkColor.BLUE
    link.thickness = LinkThickness.THICKNESS_1
    link.label = 'foo'
    link.style = LinkStyle.NORMAL
    assert len(link.get_properties()) == 5
    assert link.is_reversed is False
    assert link.color is LinkColor.BLUE.hex_color()
    assert link.style is LinkStyle.NORMAL.value
    assert link.thickness is LinkThickness.THICKNESS_1.value
    assert link.label == 'foo'
    properties = link.get_properties()
    assert link.REVERSED_PROPERTY_ID in properties and properties[link.REVERSED_PROPERTY_ID].value is False
    assert link.STYLE_PROPERTY_ID in properties
    assert properties[link.STYLE_PROPERTY_ID].value == LinkStyle.NORMAL.value
    assert link.COLOR_PROPERTY_ID in properties
    assert properties[link.COLOR_PROPERTY_ID].value == LinkColor.BLUE.hex_color()
    assert link.THICKNESS_PROPERTY_ID in properties
    assert properties[link.THICKNESS_PROPERTY_ID].value == LinkThickness.THICKNESS_1.value
    assert link.LABEL_PROPERTY_ID in properties
    assert properties[link.LABEL_PROPERTY_ID].value == 'foo'


def test_dynamic_link_properties() -> None:
    link = MaltegoLink(
        source_id=create_maltego_id(),
        target_id=create_maltego_id(),
    )
    test_property_map: Dict[str, Any] = {
        'int_property': 1,
        'float_property': 1.0,
        'str_property': 'test',
        'bool_property': False,
        'date_property': date.today(),
        'datetime_property': datetime.now(),
        'daterange_property': daterange.Ranges.last_7_days,
        'list_str_property': ['a', 'b', 'c'],
        'list_int_property': [1, 2, 3],
        'list_float_property': [1.1, 2.2, 3.3],
        'list_bool_property': [True, False, True]
    }
    for key, value in test_property_map.items():
        link.set_property(key, value, key)
    for key, value in test_property_map.items():
        assert link.get_property(key) is value


def test_enum_link_color():
    link = MaltegoLink(create_maltego_id(), create_maltego_id())

    # Test set using an enum value
    link.color = LinkColor.GREEN
    assert link.color == LinkColor.GREEN.hex_color()

    link.color = "#800080"
    assert link.color == LinkColor.PURPLE.hex_color()

    # Test set using a None value
    link.color = LinkColor.NONE
    assert link.color == LinkColor.NONE.hex_color()


def test_enum_link_style():
    link = MaltegoLink(create_maltego_id(), create_maltego_id())

    # Test set using an enum value
    link.style = LinkStyle.DASHED
    assert link.style is LinkStyle.DASHED.value


def test_enum_link_thickness():

    link = MaltegoLink(create_maltego_id(), create_maltego_id())

    # Test set using an enum value
    link.thickness = LinkThickness.THICKNESS_2
    assert link.thickness is LinkThickness.THICKNESS_2.value
