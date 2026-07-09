# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from typing import List

from fastapi_restful.api_model import APIModel

from maltego.protocol.v3.execution.entity import TransformRunEntity
from maltego.protocol.v3.execution.link import TransformRunLink


class TransformRunInputGraph(APIModel):
    entities: List[TransformRunEntity]
    links: List[TransformRunLink]
