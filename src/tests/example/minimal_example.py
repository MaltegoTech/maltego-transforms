# Copyright (c) Maltego Technologies GmbH.
import argparse
import logging
import os
from maltego.model.server import MaltegoHubItem, ServerHTTPSettings
from maltego.server import run_server, MaltegoServerSettings, setup

logging.basicConfig(level=logging.DEBUG)

# Server settings - these values can be overridden via environment variables:
#   MALTEGO_SERVER_TRANSFORM_PREFIX, MALTEGO_SERVER_TRANSFORM_NAME_PREFIX,
#   MALTEGO_SERVER_TRANSFORM_APP_NAME_PREFIX, MALTEGO_SERVER_TRANSFORM_DISPLAY_NAME_PREFIX
# Or via a .env file. Priority: ENV > .env > code values > defaults
server_settings = MaltegoServerSettings(
    server_name="Maltego Transform Server",
    ns="com.maltego.pyjinx",
    author="author@example.com",
    owner="Maltego Technologies GmbH",
    version="1.2.3",
    transform_prefix=True,
    transform_name_prefix="onprem",
    transform_app_name_prefix="[On-Premise] ",
    transform_display_name_prefix="[On-Premise] ",
    allow_regenerating_oauth_keys=True,
    disclaimer="https://maltego.com",
    api_prefix="/maltego_transforms_minimal_example",
    # Browser access: set MALTEGO_SERVER_CORS_ALLOWED_ORIGINS or
    # MALTEGO_SERVER_CORS_ALLOWED_ORIGIN_REGEX env vars, picked up automatically
    # by http_settings, or pass them explicitly:
    http_settings=ServerHTTPSettings(
        cors_allowed_origins=os.environ.get("MALTEGO_SERVER_CORS_ALLOWED_ORIGINS"),
        cors_allowed_origin_regex=os.environ.get("MALTEGO_SERVER_CORS_ALLOWED_ORIGIN_REGEX"),
    ),
)

setup(server_settings)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Run with an option to enable or disable SSL.")
    parser.add_argument(
        "--ssl",
        action=argparse.BooleanOptionalAction,
        help="Enable SSL",
        default=False
    )
    parser.add_argument(
        "--port",
        help="Port",
        default=8080,
        type=int
    )
    args = parser.parse_args()

    run_server(
        host="0.0.0.0",
        port=args.port,
        ssl=args.ssl,
        log_level="DEBUG",
        ssl_cert_file="resources/server.crt",
        ssl_key_file="resources/server.key",
        transform_middlewares=[],
        reload=True,
        hub_item=MaltegoHubItem(
            description="Example Maltego transform server",
            provider_name="Maltego Technologies",
            provider_phone='0123456789',
            provider_website="https://maltego.com",
            display_name="Jinxpy Full Example"
        )
    )
