# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List
from fastapi_restful.api_model import APIModel

from maltego.protocol.v3.discovery.transform import V3TransformSetting


class V3TransformApplication(APIModel):
    name: str
    url: str
    transform_server_settings: List[V3TransformSetting]
    version: str = "3.0"


class V3SeedResponse(APIModel):
    maltego_v3_transform_discovery_message: List[V3TransformApplication]
    hub_item_settings: List[V3TransformSetting]
