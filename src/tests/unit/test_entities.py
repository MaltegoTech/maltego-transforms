# Copyright (c) Maltego Technologies GmbH.
import datetime
import pathlib
import sys
from typing import List, Optional, Any

import pytest

from maltego.server import MaltegoEntity, MaltegoEntityProperty, daterange, register_entity
from maltego.model.entity import MEF, MaltegoEntityConfig, MaltegoEntityMeta, _namespace_annotations
from maltego.model.entity.constants import Overlay, OverlayTypes, OverlayPositions
from maltego.model.entity.property import _MaltegoEntityProperty
from maltego.model.entity.type_handling import to_v3_property_type

from tests.conftest import RichEntity, Phrase, Person

pytestmark = pytest.mark.unit
TEST_RESOURCES = pathlib.Path(__file__).resolve().parents[1] / "resources"


class Mock(MaltegoEntity):
    TYPE_NAME = "maltego.Mock"
    Config = MaltegoEntityConfig(
        value_property="value",
        display_name="Mock",
        description="Mock Entity used for tests",
        display_property="value",
        category="Personal",
        display_name_plural="Mocks",
        icon_resource="Mock",
        _visible=True
    )
    value: str = MEF(
        name="value",
        display_name="Value",
        sample_value='Some Value',
    )


class MockChild(Mock):
    TYPE_NAME = "maltego.MockChild"
    Config = MaltegoEntityConfig(
        value_property="value_child",
        display_name="Mock Child",
        description="Mock Entity used for tests",
        display_property="value_child",
        category="Personal",
        display_name_plural="Mock Children",
        icon_resource="Mock",
        _visible=True
    )
    value_child: str = MEF(
        name="value_child",
        display_name="Value",
        sample_value='Some Value',
    )


class MockChild2(Mock):
    TYPE_NAME = "maltego.MockChild2"
    value_property = "value_child"
    display_name = "Mock Child"
    display_property = "value_child"
    display_name_plural = "Mock Children"

    value_child: str = MEF(
        name="value_child",
        display_name="Value",
        sample_value='Some Value',
    )


def _assert_entity_config(entity_config) -> None:
    assert entity_config
    assert entity_config.allowed_root
    assert entity_config.category == "Custom1"
    assert entity_config.conversion_order == 2147483647
    assert entity_config.description == "A new fancy phrase entity"
    assert entity_config.display_name == "My Fancy Phrase"
    assert entity_config.display_name_plural == "My Fancy Phrases"
    assert entity_config.display_property == "my_string_value"
    assert entity_config.value_property == "my_string_value"
    assert entity_config.icon_name == "Assemble"
    assert entity_config.gen_icon_path == str(TEST_RESOURCES / "BtcBlock.png")


def assert_entity_config(entity) -> None:
    assert entity.TYPE_NAME == "maltego.RichEntity"
    _assert_entity_config(entity.Config)


def test_empty_entity_def() -> None:

    @register_entity
    class SimpleMock(MaltegoEntity):
        pass

    assert SimpleMock.TYPE_NAME == "maltego.SimpleMock"
    assert SimpleMock.Config is not None
    assert SimpleMock.Config.value_property is None


def test_entity_config_overlays() -> None:
    assert MaltegoEntityConfig(
        value_property=1,  # type:ignore
        display_name="Parent1Entity",
        overlays=None
    )
    assert MaltegoEntityConfig(
        value_property=1,  # type:ignore
        display_name="Parent1Entity",
        overlays=[]
    )
    with pytest.raises(TypeError):
        MaltegoEntityConfig(
            value_property=1,  # type:ignore
            display_name="Parent1Entity",
            overlays=[1, 2, 3]  # type:ignore
        )
    with pytest.raises(TypeError):
        MaltegoEntityConfig(
            value_property=1,  # type:ignore
            display_name="Parent1Entity",
            overlays=[Overlay("foo", "bar", "baz"), 2, 3]  # type:ignore
        )


def test_inheritance_mixin() -> None:
    @register_entity
    class ParentEntity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="parent1_text",
            display_name="Parent1Entity",
            icon_resource="Phrase"
        )
        parent1_text: str = MaltegoEntityProperty()

    class Mixin:
        mixin_test: str = MaltegoEntityProperty()

    @register_entity
    class ChildEntity(ParentEntity, Mixin):
        Config = MaltegoEntityConfig(
            value_property="child1_text",
            display_name="ChildEntity",
            icon_resource="Phrase"
        )
        child1_text: str = MaltegoEntityProperty()

    child1_entity = ChildEntity("")
    assert len(child1_entity.Config.get_base_entities()) == 1
    assert child1_entity.Config.get_base_entities()[0] == "maltego.ParentEntity"

    class Child2Entity(ChildEntity, Mixin):
        Config = MaltegoEntityConfig(
            value_property="child2_text",
            display_name="Child2Entity",
            icon_resource="Phrase"
        )
        child2_text: str = MaltegoEntityProperty()

    child2_entity = Child2Entity("")
    assert len(child2_entity.Config.get_base_entities()) == 1
    assert child2_entity.Config.get_base_entities()[0] == "maltego.ChildEntity"

    assert len(child2_entity.base_entity_types()) == 2
    assert "maltego.ChildEntity" in child2_entity.base_entity_types()
    assert "maltego.ParentEntity" in child2_entity.base_entity_types()


def test_inheritance_and_composition() -> None:
    @register_entity
    class TestParent1Entity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="parent1_text",
            display_name="Parent1Entity",
            icon_resource="Phrase"
        )
        parent1_text: str = MaltegoEntityProperty()

    @register_entity
    class TestParent2Entity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="parent2_text",
            display_name="Parent2Entity",
            icon_resource="Phrase"
        )
        parent2_text: str = MaltegoEntityProperty()

    @register_entity
    class TestChild1Entity(TestParent1Entity):
        child1_text: str = MaltegoEntityProperty()

    @register_entity
    class TestChild2Entity(TestParent2Entity):
        child2_text: str = MaltegoEntityProperty()

    @register_entity
    class TestChild3Entity(TestChild1Entity, TestChild2Entity):
        child3_text: str = MaltegoEntityProperty()

    parent1_entity = TestParent1Entity("")
    assert len(parent1_entity.Config.get_base_entities()) == 0
    assert len(parent1_entity.get_properties()) == 1
    assert list(parent1_entity.get_properties().values())[0].name == "parent1_text"
    assert MaltegoEntityMeta.try_get_registry("maltego.TestParent1Entity") is TestParent1Entity

    parent2_entity = TestParent2Entity("")
    assert len(parent2_entity.Config.get_base_entities()) == 0
    assert len(parent2_entity.get_properties()) == 1
    assert list(parent2_entity.get_properties().values())[0].name == "parent2_text"
    assert MaltegoEntityMeta.try_get_registry("maltego.TestParent2Entity") is TestParent2Entity

    child1_entity = TestChild1Entity("")
    assert len(child1_entity.Config.get_base_entities()) == 1
    assert child1_entity.Config.get_base_entities()[0] == "maltego.TestParent1Entity"
    assert len(child1_entity.get_properties()) == 2
    assert list(child1_entity.get_properties().values())[0].name == "parent1_text"
    assert list(child1_entity.get_properties().values())[1].name == "child1_text"
    assert MaltegoEntityMeta.try_get_registry("maltego.TestChild1Entity") is TestChild1Entity

    child2_entity = TestChild2Entity("")
    assert len(child2_entity.Config.get_base_entities()) == 1
    assert child2_entity.Config.get_base_entities()[0] == "maltego.TestParent2Entity"
    assert len(child2_entity.get_properties()) == 2
    assert list(child2_entity.get_properties().values())[0].name == "parent2_text"
    assert list(child2_entity.get_properties().values())[1].name == "child2_text"
    assert MaltegoEntityMeta.try_get_registry("maltego.TestChild2Entity") is TestChild2Entity

    child3_entity = TestChild3Entity("")
    assert len(child3_entity.Config.get_base_entities()) == 2
    assert child3_entity.Config.get_base_entities()[0] == "maltego.TestChild1Entity"
    assert child3_entity.Config.get_base_entities()[1] == "maltego.TestChild2Entity"

    assert len(child3_entity.base_entity_types()) == 5
    assert "maltego.TestChild3Entity" in child3_entity.base_entity_types()
    assert "maltego.TestChild1Entity" in child3_entity.base_entity_types()
    assert "maltego.TestParent1Entity" in child3_entity.base_entity_types()
    assert "maltego.TestChild2Entity" in child3_entity.base_entity_types()
    assert "maltego.TestParent2Entity" in child3_entity.base_entity_types()

    assert len(child3_entity.get_properties()) == 5
    assert list(child3_entity.get_properties().values())[0].name == "parent1_text"
    assert list(child3_entity.get_properties().values())[1].name == "child1_text"
    assert list(child3_entity.get_properties().values())[2].name == "parent2_text"
    assert list(child3_entity.get_properties().values())[3].name == "child2_text"
    assert list(child3_entity.get_properties().values())[4].name == "child3_text"
    assert MaltegoEntityMeta.try_get_registry("maltego.TestChild3Entity") is TestChild3Entity


def test_entity_config():
    minimal_config = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
    )
    assert minimal_config.value_property == "foo"
    assert minimal_config.display_name == "Bar"
    assert minimal_config.description == ""
    assert minimal_config.category == "Custom"
    assert minimal_config.allowed_root is True
    assert minimal_config.overlay_image_property is None
    assert minimal_config.conversion_order == 2147483647
    assert minimal_config.display_name_plural == "Bars"

    full_config = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
        description="desc",
        category="cat",
        allowed_root=False,
        overlay_image_property="Foo",
        conversion_order=1,
        display_name_plural="XYZ"
    )
    assert full_config.value_property == "foo"
    assert full_config.display_name == "Bar"
    assert full_config.description == "desc"
    assert full_config.category == "cat"
    assert full_config.allowed_root is False
    assert full_config.overlay_image_property == "Foo"
    assert full_config.conversion_order == 1
    assert full_config.display_name_plural == "XYZ"


def test_entity_config_casting():
    invalid = MaltegoEntityConfig(
        value_property=1,  # type:ignore
        display_name=2,  # type:ignore
        description=3,  # type:ignore
        category=4,  # type:ignore
        allowed_root=5,  # type:ignore
        overlays=None,
        overlay_image_property=6,  # type:ignore
        conversion_order="7",  # type:ignore
        display_name_plural=9,  # type:ignore
        display_property=10,  # type:ignore
        _visible="11"  # type:ignore
    )
    assert invalid.value_property == "1"
    assert invalid.display_name == "2"
    assert invalid.description == "3"
    assert invalid.category == "4"
    assert invalid.allowed_root is True
    assert invalid.overlays is None
    assert invalid.overlay_image_property == "6"
    assert invalid.conversion_order == 7
    assert invalid.display_name_plural == "9"
    assert invalid.display_property == "10"
    assert invalid.visible == getattr(invalid, "_visible") == True


def test_entity_config_icons():
    icon_config_tuple = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
        icon_resource=("foo", "a.out")
    )
    assert icon_config_tuple.icon_resource == ("foo", "a.out")
    assert icon_config_tuple.icon_name == "foo"
    assert icon_config_tuple.gen_icon_path
    assert icon_config_tuple.small_icon_resource
    assert icon_config_tuple.large_icon_resource
    icon_config_str = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
        icon_resource="Phrase"
    )
    assert icon_config_str.icon_resource == "Phrase"
    assert icon_config_str.icon_name == "Phrase"
    assert icon_config_str.gen_icon_path is None
    assert icon_config_str.small_icon_resource
    assert icon_config_str.large_icon_resource

    icon_config_str = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
        icon_resource="Phrase"
    )
    assert icon_config_str.icon_resource == "Phrase"
    assert icon_config_str.gen_icon_path is None
    assert icon_config_str.icon_name == "Phrase"

    icon_config_none = MaltegoEntityConfig(
        value_property="foo",
        display_name="Bar",
        icon_resource=None
    )
    assert icon_config_none.icon_resource is None
    assert icon_config_none.gen_icon_path is None
    assert icon_config_none.icon_name == "Unknown"

    with pytest.raises(TypeError):
        icon_config_str = MaltegoEntityConfig(
            value_property="foo",
            display_name="Bar",
            icon_resource=10  # type:ignore
        )
    with pytest.raises(TypeError):
        icon_config_str = MaltegoEntityConfig(
            value_property="foo",
            display_name="Bar",
            icon_resource=("foo", 1)  # type:ignore
        )

    with pytest.raises(TypeError):
        icon_config_str = MaltegoEntityConfig(
            value_property="foo",
            display_name="Bar",
            icon_resource=("foo", "bar", "baz")  # type:ignore
        )


def test_entity_config_base_entities() -> None:

    @register_entity
    class AEntity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="a_property",
            display_name="Bar",
            icon_resource="None",
            display_name_plural="BarBar",
            display_property="a_property",
            category="A"
        )
        a_property: str = "baz"

    @register_entity
    class BEntity(AEntity):
        pass

    @register_entity
    class B2Entity(AEntity):
        Config = MaltegoEntityConfig(
            value_property="b2_property",
            display_name="Bar",
            icon_resource="None",
            display_name_plural="BarBar",
            display_property="b2_property",
            category="A"
        )
        b2_property: str = "baz"

    @register_entity
    class CEntity(BEntity):
        pass

    @register_entity
    class C2Entity(B2Entity):
        Config = MaltegoEntityConfig(
            value_property="c2_property",
            display_name="Bar",
            icon_resource="None",
            display_name_plural="BarBar",
            display_property="c2_property",
            category="A"
        )
        c2_property: str = "baz"

    class DEntity(C2Entity):
        pass

    a_entity = AEntity("")
    b_entity = BEntity("")
    b2_entity = B2Entity("")
    c_entity = CEntity("")
    c2_entity = C2Entity("")
    d_entity = DEntity("")
    assert len(a_entity.Config.get_base_entities()) == 0
    assert len(b_entity.Config.get_base_entities()) == 1
    assert b_entity.Config.get_base_entities()[0] == "maltego.AEntity"
    assert len(b2_entity.Config.get_base_entities()) == 1
    assert b2_entity.Config.get_base_entities()[0] == "maltego.AEntity"
    assert len(c_entity.Config.get_base_entities()) == 1
    assert c_entity.Config.get_base_entities()[0] == "maltego.BEntity"
    assert len(c_entity.base_entity_types()) == 3
    assert "maltego.CEntity" in c_entity.base_entity_types()
    assert "maltego.BEntity" in c_entity.base_entity_types()
    assert "maltego.AEntity" in c_entity.base_entity_types()
    assert len(c2_entity.Config.get_base_entities()) == 1
    assert c2_entity.Config.get_base_entities()[0] == "maltego.B2Entity"
    assert len(c2_entity.base_entity_types()) == 3
    assert "maltego.C2Entity" in c2_entity.base_entity_types()
    assert "maltego.B2Entity" in c2_entity.base_entity_types()
    assert "maltego.AEntity" in c2_entity.base_entity_types()
    assert len(d_entity.Config.get_base_entities()) == 1
    assert d_entity.Config.get_base_entities()[0] == "maltego.C2Entity"
    assert len(d_entity.base_entity_types()) == 3
    assert "maltego.C2Entity" in d_entity.base_entity_types()
    assert "maltego.B2Entity" in d_entity.base_entity_types()
    assert "maltego.AEntity" in d_entity.base_entity_types()

    @register_entity
    class A2Entity(MaltegoEntity):  # []
        Config = MaltegoEntityConfig(
            value_property="a_property",
            display_name="Bar",
            icon_resource="None",
            display_name_plural="BarBar",
            display_property="a_property",
            category="A"
        )
        a_property: str = "baz"

    @register_entity
    class B3Entity(AEntity):
        pass

    @register_entity
    class C3Entity(B3Entity, A2Entity):
        pass

    c3_entity = C3Entity("")
    assert len(c3_entity.Config.get_base_entities()) == 2
    assert c3_entity.Config.get_base_entities()[0] == "maltego.B3Entity"
    assert c3_entity.Config.get_base_entities()[1] == "maltego.A2Entity"

    assert len(c3_entity.base_entity_types()) == 4
    assert "maltego.C3Entity" in c3_entity.base_entity_types()
    assert "maltego.B3Entity" in c3_entity.base_entity_types()
    assert "maltego.AEntity" in c3_entity.base_entity_types()
    assert "maltego.A2Entity" in c3_entity.base_entity_types()


def test_entity_value_prop_missing():
    with pytest.raises(ValueError):
        class AEntity(MaltegoEntity):
            Config = MaltegoEntityConfig(
                value_property="my_string_value",
                display_property="my_string_value",
                category="Custom1",
                display_name="My Fancy Phrase",
                description="A new fancy phrase entity",
                icon_resource=("Assemble", str(TEST_RESOURCES / "BtcBlock.png"))
            )
        AEntity("ASD")


def test_config_inheritance() -> None:
    class AEntity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="a_property",
            display_name="Bar",
            icon_resource="None",
            display_name_plural="BarBar",
            display_property="a_property",
            category="A",
            allowed_root=False
        )
        a_property: str = "baz"

    a_entity = AEntity("1")
    assert a_entity.Config.value_property == "a_property"
    assert a_entity.Config.display_name == "Bar"
    assert a_entity.Config.icon_resource == "None"
    assert a_entity.Config.display_name_plural == "BarBar"
    assert a_entity.Config.display_property == "a_property"
    assert a_entity.Config.category == "A"
    assert not a_entity.Config.allowed_root

    class B2Entity(AEntity):
        pass

    b2_entity = B2Entity("1")
    assert b2_entity.Config.value_property == "a_property"
    assert b2_entity.Config.display_name == "B2Entity"
    assert b2_entity.Config.icon_resource == "None"
    assert b2_entity.Config.display_name_plural == "BarBar"
    assert b2_entity.Config.display_property == "a_property"
    assert b2_entity.Config.category == "A"
    assert not b2_entity.Config.allowed_root

    class BEntity(AEntity):
        Config = MaltegoEntityConfig(
            value_property="b_property",
            display_name="Bar",
            icon_resource="None",
            allowed_root=True
        )
        b_property: int = 42

    b_entity = BEntity(1)
    assert b_entity.Config.value_property == "b_property"
    assert b_entity.Config.display_name == "Bar"
    assert b_entity.Config.icon_resource == "None"
    assert b_entity.Config.display_name_plural == "BarBar"
    assert b_entity.Config.display_property == "a_property"
    assert b_entity.Config.category == "A"
    assert b_entity.Config.allowed_root is True

    class CEntity(BEntity):
        Config = MaltegoEntityConfig(
            value_property="c_property",
            display_name="Bar2",
            icon_resource="NoneNone",
        )
        c_property: int = 42

    c_entity = CEntity(1)

    assert c_entity.Config.value_property == "c_property"
    assert c_entity.Config.display_name == "Bar2"
    assert c_entity.Config.icon_resource == "NoneNone"
    assert c_entity.Config.display_name_plural == "BarBar"
    assert c_entity.Config.display_property == "a_property"
    assert c_entity.Config.category == "A"
    assert c_entity.Config.allowed_root is True


def test_entity_definition() -> None:
    entity = RichEntity("Foo")
    assert_entity_config(entity)


def test_maltego_entity_instantiation() -> None:
    with pytest.raises(TypeError):
        MaltegoEntity("asd")


def test_property() -> None:
    entity = RichEntity("")
    assert entity.entity_properties.get("property_name") is not None
    assert entity.property_name == "Foo"
    assert entity.get_property('property.name') == "Foo"

    entity.set_property('property.name', "Bar")
    assert entity.property_name == "Bar"
    assert entity.get_property('property.name') == "Bar"

    entity.property_name = "Baz"
    assert entity.property_name == "Baz"
    assert entity.get_property('property.name') == "Baz"


def test_static_properties():
    entity = RichEntity("Foo")
    assert entity.Config.value_property is not None
    assert entity.get_property(entity.Config.value_property) == "Foo"
    assert entity.get_property("my_string_value") == "Foo"
    assert entity.my_string_value == "Foo"
    assert entity.value == "Foo"

    entity.set_property("my_string_value", "Baz")
    assert entity.get_property("my_string_value") == "Baz"
    assert entity.get_property(entity.Config.value_property) == "Baz"

    assert entity.my_int_value is None
    entity.set_property("my_int_value", 20)
    assert entity.my_int_value == 20
    with pytest.raises(TypeError):
        entity.set_property("my_int_value", "Foo")
    assert entity.my_int_value == 20


def test_dynamic_properties():
    entity = RichEntity("Foo")
    entity.dynamic1 = "foo"
    entity.set_property("dynamic2", "bar")
    assert entity.dynamic1 == "foo"
    assert entity.dynamic2 == "bar"


def test_defined_property_set_get():
    # Given a newly created person entity
    person = Person("John Doe")

    # When assigning defined properties to the person
    person.first_names = "John"
    person.surname = "Doe"
    person.full_name = "John Doe"

    # Then those properties can be accessed
    assert person.full_name == person.value == "John Doe"
    assert person.first_names == "John"
    assert person.surname == "Doe"


def test_dynamic_property_set_get():
    # Given a newly created person entity
    person = Person("John Doe")

    # When accessing a non-existent property
    with pytest.raises(AttributeError):
        _ = person.test
    # Then an AttributeError is raised

    # When assigning dynamic properties using attribute assignment
    person.new_property = "wrong way"
    # Then an exception is not raised

    # When assigning dynamic properties use the set_property method
    person.set_property("test", "Test value", display_name="Test")
    # Then the dynamic property can be accessed
    assert person.test == "Test value"


def test_entity_built_in_methods():
    # Given a newly created person
    person = Person("John Doe")
    person.firstnames = "John"

    # When stringifying the entity
    person_str_lower = str(person).lower()
    # Then a readable str is returned
    assert person_str_lower == "maltegoentity['maltego.person'](value=john doe)"


def test_types_are_inferred_on_set_property_with_try_parsing_set_to_true() -> None:
    # Given a type definition that includes non-string types
    class MyEntity(MaltegoEntity):
        TYPE_NAME = "test.MyEntity"
        Config = MaltegoEntityConfig(
            value_property="value_prop",
            display_name="Foo",
            icon_resource="Phrase"
        )
        value_prop: str
        int_prop: int = MaltegoEntityProperty()
        int_array_prop: List[int] = MaltegoEntityProperty()
        date_prop: datetime.date = MaltegoEntityProperty()
        daterange_prop: daterange = MaltegoEntityProperty()

    # when assigning string property values to an instance of that type with try_parsing=True
    ent = MyEntity("test")
    ent.set_property("int_prop", "1", try_parsing=True)
    # looks weird but this is how Maltego currently works
    ent.set_property("int_array_prop", "1,2,3", try_parsing=True)
    ent.set_property("date_prop", "1999-12-31", try_parsing=True)
    ent.set_property("daterange_prop", "Last 7 days", try_parsing=True)

    # Then the resulting assignments are properly parsed into the corresponding type
    assert isinstance(ent.int_prop, int) and ent.int_prop == 1

    assert isinstance(ent.int_array_prop, list)
    assert ent.int_array_prop == [1, 2, 3]

    assert isinstance(ent.date_prop, datetime.date)
    assert ent.date_prop == datetime.date(year=1999, month=12, day=31)

    assert isinstance(ent.daterange_prop, daterange)
    assert getattr(ent.daterange_prop, 'range', None) == daterange.Ranges.last_7_days


def test_entity_with_classmethod():
    class EntityWithClassmethod(MaltegoEntity):
        TYPE_NAME = "maltego.EntityWithClassmethod"
        Config = MaltegoEntityConfig(
            value_property="foo",
            display_property="foo",
            category="General",
            display_name="EntityWithClassmethod",
            display_name_plural="EntityWithClassmethods",
            description="A EntityWithClassmethod.",
            icon_resource="Language"
        )

        prop_1: str = "foo"
        prop_2: str = MaltegoEntityProperty(name="foo",
                                            display_name="Foo",
                                            sample_value="bar",
                                            matching_rule="strict")

        @classmethod
        def bar(cls, alpha_2: str) -> None:  # pylint: disable=disallowed-name
            pass

        @staticmethod
        def barstatic(cls, alpha_2: str) -> None:  # pylint: disable=bad-staticmethod-argument
            pass

        def baz(self, alpha_2: str) -> None:  # pylint: disable=disallowed-name
            pass

    assert "prop_1" in EntityWithClassmethod.entity_properties
    assert "prop_2" in EntityWithClassmethod.entity_properties
    assert "bar" not in EntityWithClassmethod.entity_properties
    assert "barstatic" not in EntityWithClassmethod.entity_properties
    assert "baz" not in EntityWithClassmethod.entity_properties


def test_entity_type_name_extrapolation():
    class Entity(MaltegoEntity):
        pass  # TYPE_NAME: maltego.Unknown
    assert Entity.TYPE_NAME == "maltego.Unknown"

    class Entity_(Entity):  # pylint: disable=invalid-name
        pass  # TYPE_NAME: maltego.Unknown
    assert Entity_.TYPE_NAME == "maltego.Unknown"

    @register_entity
    class RegisteredEntity(MaltegoEntity):
        pass  # TYPE_NAME: maltego.RegisteredEntity
    assert RegisteredEntity.TYPE_NAME == "maltego.RegisteredEntity"

    @register_entity
    class FooEntity(Entity):
        TYPE_NAME = "maltego.Foo"  # TYPE_NAME: maltego.Foo

    assert FooEntity.TYPE_NAME == "maltego.Foo"

    @register_entity
    class RegisteredEntity2(RegisteredEntity):
        pass  # TYPE_NAME: maltego.RegisteredEntity3
    assert RegisteredEntity2.TYPE_NAME == "maltego.RegisteredEntity2"

    @register_entity
    class RegisteredEntity3(Entity):
        pass  # TYPE_NAME: maltego.RegisteredEntity3
    assert RegisteredEntity3.TYPE_NAME == "maltego.RegisteredEntity3"

    @register_entity
    class RegisteredEntity4(RegisteredEntity3):
        pass  # TYPE_NAME: maltego.RegisteredEntity3
    assert RegisteredEntity4.TYPE_NAME == "maltego.RegisteredEntity4"

    class Entity2_(RegisteredEntity3):  # pylint: disable=invalid-name
        pass  # TYPE_NAME: maltego.RegisteredEntity3
    assert Entity2_.TYPE_NAME == "maltego.RegisteredEntity3"

    assert Phrase.TYPE_NAME == "maltego.Phrase"
    assert MaltegoEntity["foo"].TYPE_NAME == "foo"


def test_unknown_entity_default_property_type_str():
    unknown_entity = MaltegoEntity["foo"]
    unknown_entity_properties = unknown_entity.entity_properties
    assert unknown_entity_properties["text"].annotated_type == str


def test_overlay_during_property_initialization():
    """Test that add_overlay can be called during set_property in __init__."""
    
    @register_entity
    class EntityWithOverlayOnPropertySet(MaltegoEntity):
        """Entity that adds an overlay when a specific property is set."""
        TYPE_NAME = "maltego.EntityWithOverlayOnPropertySet"
        Config = MaltegoEntityConfig(
            value_property="value",
            display_name="Entity With Overlay",
            description="Test entity that adds overlay during property initialization",
            display_property="value",
            category="Test",
        )
        value: str = MEF(name="value")
        trigger_property: str = MEF(name="trigger_property")
        
        def set_property(
                self,
                name: str,
                value: Optional[Any],
                display_name: Optional[str] = None,
                matching_rule: Optional[Any] = None,
                try_parsing: bool = True,
                property_type: Optional[Any] = None,
        ) -> None:
            super().set_property(name, value, display_name, matching_rule, try_parsing, property_type)
            
            # setting trigger_property also adds an overlay to the entity
            if name == "trigger_property" and value:
                self.add_overlay(
                    OverlayTypes.TEXT,
                    OverlayPositions.NORTH,
                    "trigger_property"
                )
    
    # init time test
    entity = EntityWithOverlayOnPropertySet(
        value="test_value",
        properties={
            "trigger_property": _MaltegoEntityProperty(value="test_trigger", display_name="Trigger")
        }
    )
    
    assert entity.value == "test_value"
    assert entity.trigger_property == "test_trigger"
    
    assert len(entity.overlays) == 1
    assert entity.overlays[0].overlay_type == "text"
    assert entity.overlays[0].position == "N"
    assert entity.overlays[0].property_name == "trigger_property"
    
    # adding after initialization test
    entity2 = EntityWithOverlayOnPropertySet(value="test_value2")
    assert len(entity2.overlays) == 0
    
    entity2.set_property("trigger_property", "triggered")

    assert len(entity2.overlays) == 1
    assert entity2.overlays[0].overlay_type == "text"


def test_typed_property_annotations_resolve_to_wire_types() -> None:
    # Regression guard for the Python 3.14 PEP 649/749 lazy-annotation fix in
    # maltego.model.entity._namespace_annotations. Under deferred annotations the
    # metaclass namespace exposes __annotate_func__ instead of a materialized
    # __annotations__; if those annotations are dropped, every property collapses
    # to STRING on discovery/transform-run. This asserts each typed field keeps its
    # real Python type and maps to the expected v3 wire type, on every interpreter.
    @register_entity
    class TypedEntity(MaltegoEntity):
        Config = MaltegoEntityConfig(
            value_property="text",
            display_name="Typed",
            display_property="text",
            display_name_plural="Typeds",
            icon_resource="None",
            category="A",
        )
        text: str = MEF(name="text", display_name="Text", sample_value="x")
        count: int = MEF(name="count", display_name="Count", sample_value=1)
        ratio: float = MEF(name="ratio", display_name="Ratio", sample_value=1.5)
        flag: bool = MEF(name="flag", display_name="Flag", sample_value=True)
        tags: List[str] = MEF(name="tags", display_name="Tags", sample_value=["a"])

    props = TypedEntity.entity_properties
    expected_primitive = {"text": str, "count": int, "ratio": float, "flag": bool, "tags": str}
    expected_wire = {"text": "STRING", "count": "INT", "ratio": "DOUBLE", "flag": "BOOLEAN", "tags": "STRING"}

    for name, primitive in expected_primitive.items():
        prop = props[name]
        # annotation must be a real type object, not the string literal "int"/"str"/...
        assert not isinstance(prop.annotated_type, str), f"{name} annotation stayed a string literal"
        assert prop.primitive_type is primitive, f"{name} primitive_type was {prop.primitive_type!r}"
        assert to_v3_property_type(prop.primitive_type) == expected_wire[name]

    assert props["tags"].is_array is True
    assert props["count"].is_array is False


def test_namespace_annotations_reads_materialized_and_lazy() -> None:
    # Materialized namespace (Python < 3.14, and any explicitly-injected dict).
    assert _namespace_annotations({"__annotations__": {"x": int}}) == {"x": int}
    # No annotations at all -> empty mapping, never an import error.
    assert _namespace_annotations({}) == {}
    # A stray __annotate_func__ on an interpreter < 3.14 must degrade to {} rather
    # than importing annotationlib (which does not exist there). On 3.14+ the same
    # callable is evaluated in VALUE format and yields the real type.
    def _annotate(format):  # mimics CPython's __annotate_func__ signature
        return {"y": str}

    result = _namespace_annotations({"__annotate_func__": _annotate})
    if sys.version_info >= (3, 14):
        assert result == {"y": str}
    else:
        assert result == {}
