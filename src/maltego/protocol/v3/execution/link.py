# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from typing import List, Optional

from fastapi_restful.api_model import APIModel
from maltego.protocol.v3.execution.property import Property


class LinkReference(APIModel):
    id: str


class TransformRunLink(APIModel):
    id: str
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    properties: Optional[List[Property]] = None
