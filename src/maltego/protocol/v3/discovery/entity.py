# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import Any, List, Optional, Literal
from fastapi_restful.api_model import APIModel

from maltego.protocol.v3.execution.property import Property


class V3EntityOverlay(APIModel):
    property_name: str
    position: str
    type: str


class V3EntityField(APIModel):
    name: str
    matching_rule: str
    type: str = "string"
    display_name: Optional[str] = None
    nullable: bool = True
    hidden: bool = False
    readonly: bool = False
    description: Optional[str] = None
    is_array: bool = False
    sample_value: Optional[Any] = None
    default_value: Optional[Any] = None
    evaluator: Optional[str] = None
    link_properties: Optional[List[Property]] = None
    entity_type: Optional[str] = None


class V3EntityProperties(APIModel):
    value: str
    value_key: Optional[str]
    display_value: Optional[str]
    display_key: Optional[str]
    image_overlay: Optional[str]
    fields: List[V3EntityField]


class V3EntityDefinition(APIModel):
    id: str
    display_name: str
    display_name_plural: str
    icon_resource: str
    description: Optional[str] = None
    category: str = 'Personal'
    visible: bool = True
    allowed_root: bool = True
    conversion_order: int = 2147483647
    base_entities: List[str] = []
    overlays: List[V3EntityOverlay] = []
    properties: Optional[V3EntityProperties] = None
    regex_converter: Optional[V3EntityRegexConverter] = None
    actions: List[V3EntityAction] = []


class V3EntityRegexConverter(APIModel):
    regex: str
    groups: Optional[List[str]]


class V3EntityAction(APIModel):
    name: str
    display_name: Optional[str]
    config: str
    type: Literal[
        "maltego.spec.action.type.browser",
        "maltego.spec.action.type.browse-url"
    ]
