# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from enum import Enum

from typing import List, Optional
import logging

from fastapi_restful.api_model import APIModel
from maltego.protocol.v3.execution.property import Property

log = logging.getLogger(__name__)


class Bookmark(Enum):
    NONE = -1
    BLUE = 0
    GREEN = 1
    YELLOW = 2
    PURPLE = 3
    RED = 4


class DisplayInformationField(APIModel):
    name: str
    value: str
    type: str


class EntityOverlay(APIModel):
    property_name: str
    position: str
    type: str


class TransformRunEntity(APIModel):

    id: str
    value_ref: Optional[str] = None
    weight: Optional[int] = None
    properties: Optional[List[Property]] = None
    display_information: Optional[List[DisplayInformationField]] = None
    type: Optional[str] = None
    bookmark: Optional[Bookmark] = None
    overlays: List[EntityOverlay] = []
    note: Optional[str] = None
    base_entities: Optional[List[str]] = None
