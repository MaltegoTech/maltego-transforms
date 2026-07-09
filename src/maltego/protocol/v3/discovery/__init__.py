# Copyright (c) Maltego Technologies GmbH.
from typing import List
from fastapi_restful.api_model import APIModel
from maltego.protocol.v3.discovery.auth import V3OAuthServiceDefinition
from maltego.protocol.v3.discovery.entity import V3EntityDefinition
from maltego.protocol.v3.discovery.icon import V3IconDefinition
from maltego.protocol.v3.discovery.machine import V3MachineDefinition
from maltego.protocol.v3.discovery.transform_set import V3TransformSetDefinition


class V3AssetResponse(APIModel):
    entities: List[V3EntityDefinition]
    icons: List[V3IconDefinition]
    machines: List[V3MachineDefinition]
    transform_sets: List[V3TransformSetDefinition]
    o_auth_service: List[V3OAuthServiceDefinition]
