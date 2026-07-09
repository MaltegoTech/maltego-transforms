# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from fastapi_restful.api_model import APIModel


class V3StatusResponse(APIModel):
    startup_time: float
    v2_transform_count: int
    v3_transform_count: int
    entity_count: int
    entity_category_count: int
    transform_set_count: int
    icon_count: int
    machine_count: int