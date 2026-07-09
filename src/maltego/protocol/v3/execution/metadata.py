# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from typing import Dict

from fastapi_restful.api_model import APIModel


class Metadata(APIModel):
    entities_types_stat: Dict[str, int]
    entities_total_count: int = 0
    links_total_count: int = 0
    root_entities_count: int = 0
