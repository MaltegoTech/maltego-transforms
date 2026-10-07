# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations

from maltego.protocol.api_model import APIModel


class ResponseErrorMessage(APIModel):
    message: str


class ResponseError(APIModel):
    type: str
    message: ResponseErrorMessage
