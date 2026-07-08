# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from typing import List, Optional

from fastapi_restful.api_model import APIModel

class MachineRefs(APIModel):
    """
    Lists transforms and entities a machine contains.
    Parsed from the machine code.
    If fails to parse some values, references will be marked with indeterminate = True
    """
    transforms: list[str]
    entities: list[str]
    indeterminate: bool


class V3MachineDefinition(APIModel):
    name: str
    favorite: bool = False
    enabled: bool = True
    read_only: bool = False
    code: str
    machine_capabilities: Optional[List[str]] = None
    refs: Optional[MachineRefs] = None
