# Copyright (c) Maltego Technologies GmbH.
from typing import Optional
from fastapi_restful.api_model import APIModel


class V3OAuthServiceDefinition(APIModel):
    name: str
    display_name: str
    access_token_endpoint: str
    access_token_input: str
    access_token_public_key: str
    app_key: str
    app_secret: str
    authorization_url: str
    call_back_port: int = 443
    description: Optional[str]
    icon_name: str
    o_auth_version: str = "2.0"
    request_token_endpoint: Optional[str]
    refresh_token_endpoint: Optional[str]
    request_type_for_access_token: Optional[str]
    request_type_for_request_token: Optional[str]
    use_ssl_host: bool = True
