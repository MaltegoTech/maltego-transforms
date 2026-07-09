# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import Any, Optional
from fastapi_restful.api_model import APIModel
from maltego.model.types import MatchingRule


class Property(APIModel):
    """
    For type == "ENTITY", the value is the entity ID, e.g.:
        "maltego_entity_id"

    For list-typed entity properties (ENTITY[]), the value is a list of entity IDs:
        ["id1", "id2", ...]
    """
    name: str
    value: Optional[Any] = None
    type: str
    display_name: Optional[str] = None
    matching_rule: Optional[MatchingRule] = None
