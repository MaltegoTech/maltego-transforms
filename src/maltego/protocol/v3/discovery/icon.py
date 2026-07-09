# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List, Literal

from fastapi_restful.api_model import APIModel


class V3IconDefinition(APIModel):
    name: str
    format: Literal['png', 'jpg', 'svg', 'webp'] = 'png'
    category: str
    version: str = '1.0.0'
    data: List[V3IconDataDefinition]


class V3IconDataDefinition(APIModel):
    size: int
    blob: str
