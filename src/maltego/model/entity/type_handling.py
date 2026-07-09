import inspect
from typing import Any, Type

from maltego.model.types import v3_property_types


def infer_v3_type_from_property_value(value: Any) -> str:
    from maltego.model import MaltegoEntity
    if isinstance(value, list) and len(value) > 0:
        return infer_v3_type_from_property_value(value[0])
    if type(value) in v3_property_types:
        return to_v3_property_type(type(value))
    if isinstance(value, MaltegoEntity):
        return to_v3_property_type(type(value))
    return to_v3_property_type(str)


def to_v3_property_type(type_: Type[Any]) -> str:
    from maltego.model import MaltegoEntity
    if inspect.isclass(type_) and issubclass(type_, MaltegoEntity):
        return "ENTITY"
    return v3_property_types.get(type_, "STRING")

def to_v3_entity_property_type(type_: Type[Any]) -> str:
    from maltego.model import MaltegoEntity
    if inspect.isclass(type_) and issubclass(type_, MaltegoEntity):
        return type_.TYPE_NAME
    return None

def contains_entity(v):
    from maltego.model import MaltegoEntity
    if isinstance(v, MaltegoEntity):
        return True
    if isinstance(v, list):
        return any(isinstance(i, MaltegoEntity) for i in v)
    return False
