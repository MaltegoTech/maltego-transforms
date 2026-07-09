# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from typing import Optional

from fastapi_restful.api_model import APIModel


class V3HubItemProviderResponse(APIModel):
    name: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class V3HubItemResponse(APIModel):
    id: str
    display_name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    preview_image_url: Optional[str] = None
    provider: Optional[V3HubItemProviderResponse] = None
