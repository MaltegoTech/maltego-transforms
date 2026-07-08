# Copyright (c) Maltego Technologies GmbH.
import datetime
from enum import Enum
from typing import TypeVar, Union, Type

from maltego.model.entity.property import _MaltegoEntityProperty
from maltego.model.types import LinkColor, LinkStyle, LinkThickness, daterange
from maltego.protocol.v3.execution.entity import Bookmark, EntityOverlay


class OverlayPositions(Enum):
    NORTH = "N"
    SOUTH = "S"
    WEST = "W"
    NORTHWEST = "NW"
    NORTH_WEST = "NW"
    SOUTHWEST = "SW"
    SOUTH_WEST = "SW"
    CENTER = "C"


class OverlayTypes(Enum):
    TEXT = "text"
    IMAGE = "image"
    COLOR = "color"
    COLOUR = "color"


class Overlay:

    def __init__(
        self,
        overlay_type: Union[str, OverlayTypes],
        position: Union[str, OverlayPositions],
        property_name: str
    ):
        if isinstance(overlay_type, str):
            self.overlay_type = overlay_type
        elif isinstance(overlay_type, OverlayTypes):
            self.overlay_type = overlay_type.value
        else:
            raise TypeError("Overlay types must be strings or OverlayTypes")

        if isinstance(position, str):
            self.position = position
        elif isinstance(position, OverlayPositions):
            self.position = position.value
        else:
            raise TypeError("Overlay position must be strings or OverlayPositions")

        if isinstance(property_name, str) and property_name:
            self.property_name: str = property_name
        else:
            raise ValueError(f"Overlay property name {property_name} must be a non-empty string")

    def to_v3_overlay(self) -> EntityOverlay:
        return EntityOverlay(
            property_name=self.property_name,
            position=self.position,
            type=self.overlay_type
        )


MaltegoEntityEnum = TypeVar(
    'MaltegoEntityEnum', Bookmark, LinkColor, LinkStyle, LinkThickness
)

PossiblePropertyTypes = Union[
    _MaltegoEntityProperty[str],
    _MaltegoEntityProperty[int],
    _MaltegoEntityProperty[float],
    _MaltegoEntityProperty[bool],
    _MaltegoEntityProperty[datetime.date],
    _MaltegoEntityProperty[datetime.datetime],
    _MaltegoEntityProperty[daterange]
]


def ensure_enum_val(value: Union[int, MaltegoEntityEnum, None], enum: Type[MaltegoEntityEnum]) -> MaltegoEntityEnum:
    if value is None:
        return enum(None)
    if isinstance(value, enum):
        return value
    if isinstance(value, int):
        return enum(value)
    raise ValueError(f"enum value needs to be int or {enum}")
