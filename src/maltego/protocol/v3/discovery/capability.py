# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List

from fastapi_restful.api_model import APIModel


class V3SupportedCapability(APIModel):
    name: str
    description: str


class V3SupportedCapabilitiesResponse(APIModel):
    protocol: str
    supported_capabilities: List[V3SupportedCapability]
