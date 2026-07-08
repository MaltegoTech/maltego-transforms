# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
import datetime
from fastapi_restful.api_model import APIModel

from maltego.model.types import daterange, to_str_format
from maltego.protocol.v3.discovery.auth import V3OAuthServiceDefinition


class TransformDefinitionCapabilities(str, Enum):
    INTERACTIVE = "interactive"
    PROPERTY_TRANSFORM = "propertyTransform"
    INPUT_CONSTRAINTS = "inputConstraints"
    COMPOSITE_ENTITIES = "compositeEntities"


def serialize_daterange(daterange_: daterange) -> str:
    if daterange_.range:
        return daterange_.range.value
    assert isinstance(daterange_.start, (datetime.date, datetime.datetime))
    assert isinstance(daterange_.end, (datetime.date, datetime.datetime))
    return (
        f'{to_str_format(daterange_.start)}/{to_str_format(daterange_.end)}'
    )


class TransformDiscoveryIO(APIModel):
    type: Literal['GRAPH', 'ENTITIES', 'ENTITY']
    type_ids: List[str]
    property_input_type: Optional[Literal['ANY', 'ALL']] = None
    properties: Optional[List[str]] = None
    input_constraint: Optional[Dict] = None
    operator: Optional[str] = None


class V3TransformSetting(APIModel):
    display_name: str
    type: str
    name: str
    default_value: Optional[Any] = None
    optional: bool = False
    popup: bool = False
    is_global: bool = False
    auth: bool = False


class V3TransformDefinition(APIModel):
    name: str
    display_name: str
    input: TransformDiscoveryIO
    output: TransformDiscoveryIO
    description: Optional[str]
    author: Optional[str]
    owner: Optional[str]
    disclaimer: Optional[str]
    version: Optional[str]
    sets: List[str]
    max_entity_input_count: Optional[int]
    max_entity_output_count: Optional[int]
    transform_settings: List[V3TransformSetting]
    metadata: Optional[Dict[str, str]]
    authenticator: Optional[str]
    transform_capabilities: Optional[List[str]]


class V3Transforms(APIModel):
    transforms: List[V3TransformDefinition]
    oauth: List[V3OAuthServiceDefinition]
