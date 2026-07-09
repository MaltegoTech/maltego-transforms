# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List, Optional

from fastapi_restful.api_model import APIModel


class V3TransformSetDefinition(APIModel):
    name: str
    description: Optional[str] = None
    transforms: List[str]
