# Copyright (c) Maltego Technologies GmbH.

from typing import List
import datetime

from tests.conftest import Person
from maltego.model.entity import (
    MaltegoEntity,
    MaltegoEntityConfig,
    MaltegoEntityProperty,
    Overlay,
    OverlayPositions,
    OverlayTypes
)
from maltego.model.types import daterange, Url, Color
from maltego.server import register_entity


TEST_RUN = False

__all__ = [
    "SimpleEntity",
    "ComplexEntity",
    "EntityNonRoot",
    "EntityOverlays",
    "IconGenEntity",
    "PersonChild",
    "PersonChildChild",
    "Number"
]


@register_entity
class IconUrlEntity(MaltegoEntity):
    TYPE_NAME = "maltego.IconUrlEntity"
    Config = MaltegoEntityConfig(
        value_property="custom_value",
        icon_resource="Phrase",
        display_name="IconUrlEntity",
    )
    custom_value: str = MaltegoEntityProperty()


@register_entity
class SimpleEntity(MaltegoEntity):
    TYPE_NAME = "maltego.simpleEntity"
    Config = MaltegoEntityConfig(
        value_property="custom_value",
        icon_resource="Phrase",
        display_name="SimpleEntity"
    )
    custom_value: str = MaltegoEntityProperty()


@register_entity
class ComplexEntity(MaltegoEntity):
    TYPE_NAME = "maltego.complexEntity"
    Config = MaltegoEntityConfig(
        value_property="str_property",
        display_name="complexEntity",
        icon_resource=("maltego_transforms_test_image_resampling", "resources/icons/maltego_logo.png"),
        description="A custom entity",
        display_property="str_property",
        category="Custom",
        allowed_root=True,
        display_name_plural="complexEntities",
    )

    str_property: str = MaltegoEntityProperty(
        readonly=True,
        nullable=False,
        display_name="String",
        description="String Test Property",
        sample_value="Foo"
    )
    float_property: float = MaltegoEntityProperty(
        display_name="Float",
        name="float",
        description="Float Test Property",
        sample_value=42.23
    )
    int_property: int = MaltegoEntityProperty(
        display_name="Integer",
        name="int",
        description="Integer Test Property",
        sample_value=42
    )
    bool_property: bool = MaltegoEntityProperty(
        display_name="Boolean",
        name="bool",
        description="Boolean Test Property",
        sample_value=True
    )
    date_property: datetime.date = MaltegoEntityProperty(
        display_name="Date",
        name="date",
        description="Date Test Property",
        sample_value=datetime.date.fromtimestamp(0)
    )
    datetime_property: datetime.datetime = MaltegoEntityProperty(
        display_name="Datetime",
        name="datetime",
        description="Datetime Test Property",
        sample_value=datetime.datetime.fromtimestamp(0)
    )
    daterange_property: daterange = MaltegoEntityProperty(
        display_name="Daterange",
        name="daterange",
        description="Daterange Test Property",
        sample_value=daterange(
            start=datetime.datetime.fromtimestamp(0),
            end=datetime.datetime.fromtimestamp(100000)
        )
    )
    daterange2_property: daterange = MaltegoEntityProperty(
        display_name="Daterange2",
        name="daterange2",
        description="Daterange2 Test Property",
        sample_value=daterange(date_range=daterange.Ranges.last_10_years)
    )
    str_list_property: List[str] = MaltegoEntityProperty(
        display_name="String List",
        name="string_list",
        description="String List Test Property",
        sample_value=["Foo", "Bar", "Baz"]
    )
    float_list_property: List[float] = MaltegoEntityProperty(
        display_name="Float List",
        name="float_list",
        description="Float List Test Property",
        sample_value=[42.23, 23.42]
    )
    int_list_property: List[int] = MaltegoEntityProperty(
        display_name="Integer List",
        name="int_list",
        description="Integer List Test Property",
        sample_value=[42, 23]
    )
    bool_list_property: List[bool] = MaltegoEntityProperty(
        display_name="Boolean List",
        name="bool_list",
        description="Boolean List Test Property",
        sample_value=[True, False]
    )
    url: Url = MaltegoEntityProperty(
        display_name="Url",
        name="url",
        description="URL Test Property",
        sample_value="https://www.exmaple.com"
    )
    color: Color = MaltegoEntityProperty(
        display_name="Color",
        name="color",
        description="Color Test Property",
        sample_value="#ffff00"
    )


@register_entity
class EntityNonRoot(MaltegoEntity):
    TYPE_NAME = "maltego.nonRootEntity"
    Config = MaltegoEntityConfig(
        value_property="text",
        icon_resource="Phrase",
        display_name="EntityNonRoot",
        allowed_root=False
    )
    text: str = MaltegoEntityProperty()


@register_entity
class EntityOverlays(MaltegoEntity):
    TYPE_NAME = "maltego.overlayEntity"
    Config = MaltegoEntityConfig(
        value_property="text",
        icon_resource="Phrase",
        display_name="EntityOverlays",
        overlays=[
            Overlay(
                overlay_type=OverlayTypes.TEXT.value,
                position=OverlayPositions.NORTH.value,
                property_name="text"
            ),
            Overlay(
                overlay_type=OverlayTypes.IMAGE.value,
                position=OverlayPositions.WEST.value,
                property_name="image"
            ),
            Overlay(
                overlay_type=OverlayTypes.COLOR.value,
                position=OverlayPositions.SOUTH.value,
                property_name="color"
            ),
        ],
        overlay_image_property="image"

    )
    text: str = MaltegoEntityProperty(
        name="text",
        display_name="Text",
        sample_value="Foo"
    )
    image: str = MaltegoEntityProperty(
        name="image",
        display_name="Image",
        sample_value="https://www.google.com/favicon.ico"
    )
    color: str = MaltegoEntityProperty(
        name="color",
        display_name="Color",
        sample_value="#ffffff"
    )


@register_entity
class IconGenEntity(MaltegoEntity):
    TYPE_NAME = "maltego.testIconGenEntity"
    Config = MaltegoEntityConfig(
        value_property="custom_value",
        display_name="IconGenEntity",
        icon_resource=("maltego_transforms_test_image_resampling", "resources/icons/maltego_logo.png"),
    )
    custom_value: str = MaltegoEntityProperty()


@register_entity
class PersonChild(Person):  # type: ignore
    TYPE_NAME = "maltego.PersonChild"
    Config = MaltegoEntityConfig(
        value_property=Person.Config.value_property,
        display_name="PersonChild",
        icon_resource=Person.Config.large_icon_resource
    )
    custom_value_child: str = MaltegoEntityProperty()


@register_entity
class PersonChildChild(PersonChild):
    TYPE_NAME = "maltego.PersonChildChild"
    Config = MaltegoEntityConfig(
        value_property=Person.Config.value_property,
        display_name="PersonChildChild",
        icon_resource=Person.Config.large_icon_resource
    )
    custom_value_child_child: str = MaltegoEntityProperty()


@register_entity
class Parent1Entity(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="parent1_text",
        display_name="Parent1Entity",
        icon_resource="Phrase"
    )
    parent1_text: str = MaltegoEntityProperty(
        sample_value="parent1"
    )
    parent1_text2: str = MaltegoEntityProperty(
        sample_value="parent1_2"
    )


@register_entity
class Number(MaltegoEntity):
    TYPE_NAME = "maltego.Number"
    Config = MaltegoEntityConfig(
        value_property="number",
        display_name="Number",
        description="A number",
        display_property="number",
        category="Personal",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="Hashtag",
        _visible=True
    )
    number: int = MaltegoEntityProperty(name="number", display_name="Number", sample_value=22)


@register_entity
class Parent2Entity(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="parent2_text",
        display_name="Parent2Entity",
        icon_resource="Phrase"
    )
    parent2_text: str = MaltegoEntityProperty(
        sample_value="parent2"
    )


@register_entity
class Child1Entity(Parent1Entity):
    child1_text: str = MaltegoEntityProperty()
    parent1_text: str = MaltegoEntityProperty(
        sample_value="child1"
    )


@register_entity
class GrandChild1Entity(Child1Entity):
    grandchild1_text: str = MaltegoEntityProperty()
    parent1_text: str = MaltegoEntityProperty(
        sample_value="grandchild1"
    )


@register_entity
class Child2Entity(Parent2Entity):
    child2_text: str = MaltegoEntityProperty()
    parent2_text: str = MaltegoEntityProperty(
        sample_value="child2"
    )


@register_entity
class Child3Entity(Child1Entity, Child2Entity):
    child3_text: str = MaltegoEntityProperty()
    parent1_text: str = MaltegoEntityProperty(
        sample_value="child3"
    )


@register_entity
class PersonComposite(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="name",
        display_name="PersonComposite",
        icon_resource="Person"
    )
    name: str = MaltegoEntityProperty(
        sample_value="Jane Doe"
    )


@register_entity
class LocationComposite(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="location",
        display_name="LocationComposite",
        icon_resource="Location"
    )
    location: str = MaltegoEntityProperty(
        sample_value="Munich"
    )


@register_entity
class PersonWithLocation(PersonComposite, LocationComposite):
    Config = MaltegoEntityConfig(
        value_property="name",
        display_name="PersonWithLocation",
        icon_resource="Person"
    )


@register_entity
class DateTimeComposite(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="datetime_",
        display_name="DateTimeComposite",
        icon_resource="Alarm"
    )
    datetime_: datetime.datetime = MaltegoEntityProperty(
        sample_value=datetime.datetime.fromtimestamp(1000)
    )


@register_entity
class PersonWithLocationAndDateTime(PersonComposite, LocationComposite, DateTimeComposite):
    Config = MaltegoEntityConfig(
        value_property="name",
        display_name="PersonWithLocationAndDateTime",
        icon_resource="Person"
    )


