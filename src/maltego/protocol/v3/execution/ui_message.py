# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from enum import Enum
from typing import Optional, List

from fastapi_restful.api_model import APIModel


class UiMessageType(Enum):
    DEBUG = "Debug"
    INFORM = "Inform"
    PARTIAL_ERROR = "PartialError"
    FATAL_ERROR = "FatalError"


class Button(APIModel):
    id: str
    text: str
    url: Optional[str] = None


class UiMessage(APIModel):
    text: str
    type: UiMessageType = UiMessageType.INFORM
    buttons: Optional[List[Button]]
