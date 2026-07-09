# Copyright (c) Maltego Technologies GmbH.
from typing import Dict, Union, List, Optional, Sequence, Any
import argparse
import logging
import os
from maltego.model.context import MaltegoContext
from maltego.model.server import (
    EntityConfigOverride,
    EntityConfigOverrides,
    MaltegoHubItem,
    ServerHTTPSettings,
    TransformRunnerType,
)
from maltego.model.types import ExecutionState, MaltegoSettingTypes
from maltego.server import (
    run_server, MaltegoServerSettings,
    MaltegoEntity, MaltegoGraph, setup
)
from maltego.model.transform import MaltegoTransform
from maltego.middlewares.middlewares import TransformMiddleware
from tests.example.transforms.entities.entities import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.entities.coalesce_test_entities import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.transforms import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.property_constraints import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.prompts import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.machines.machines import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.sets.sets import *  # pylint: disable=unused-wildcard-import
from tests.example.transforms.entity_typed_properties import * # pylint: disable=unused-wildcard-import

logging.basicConfig(level=logging.DEBUG)


class ExampleMiddleware(TransformMiddleware):
    call_on_failure = True

    async def before_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            properties: Dict[str, MaltegoSettingTypes],
            context: MaltegoContext,
            soft_limit: int,
            hard_limit: int
    ) -> None:
        print(
            f"Call before_transform in middleware {ExampleMiddleware.__name__} for transform {transform.name}"
        )

    async def after_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            output_entities: List[MaltegoEntity],
            context: MaltegoContext,
            state: ExecutionState,
            exceptions: Optional[Sequence[Exception]] = None
    ) -> None:
        print(
            f"Call after_transform in middleware {ExampleMiddleware.__name__} for transform {transform.name}"
        )


# Entities to override allowed_root for desktop clients
DESKTOP_PALETTE_ENTITIES = [
    "maltego.nonRootEntity",  # Test entity with allowed_root=False
]

# Coalesce entity WITH override - will be available for desktop with fallback
COALESCE_OVERRIDE_ENTITY = "maltego.CoalescingDisplayPropertyEntity"

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
    api_prefix="/maltego_transforms_example",
    # Browser access: set MALTEGO_SERVER_CORS_ALLOWED_ORIGINS or
    # MALTEGO_SERVER_CORS_ALLOWED_ORIGIN_REGEX env vars, picked up automatically
    # by http_settings, or pass them explicitly:
    http_settings=ServerHTTPSettings(
        cors_allowed_origins=os.environ.get("MALTEGO_SERVER_CORS_ALLOWED_ORIGINS"),
        cors_allowed_origin_regex=os.environ.get("MALTEGO_SERVER_CORS_ALLOWED_ORIGIN_REGEX"),
    ),
    transform_runner=TransformRunnerType.THREADED,
    entity_config_overrides=EntityConfigOverrides(
        rules=[
            # Override allowed_root for desktop palette visibility
            EntityConfigOverride(
                entities=DESKTOP_PALETTE_ENTITIES,
                clients=["desktop"],
                overrides={"allowed_root": True}
            ),
            # Override coalesce for ONE entity only - to test override works
            # Other coalesce entities will be filtered (skipped) for desktop
            EntityConfigOverride(
                entities=[COALESCE_OVERRIDE_ENTITY],
                clients=["desktop"],
                overrides={"fields.display_property.default_value": "$property(name)"}
            ),
        ]
    ),
)

setup(server_settings)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run with an option to enable or disable SSL.")
    parser.add_argument(
        "--ssl",
        action=argparse.BooleanOptionalAction,
        help="Enable SSL",
        default=None
    )
    parser.add_argument(
        "--port",
        help="Port",
        default=None,
        type=int
    )
    args = parser.parse_args()

    run_server(
        settings=server_settings,  # Pass settings so http_settings are used for SSL cert paths
        port=args.port,  # Override port if specified, otherwise uses MALTEGO_SERVER_HTTP_PORT from .env
        ssl=args.ssl,    # Override SSL if specified, otherwise uses settings from .env
        reload=False,
        log_level="DEBUG",
        transform_middlewares=[ExampleMiddleware()],
        hub_item=MaltegoHubItem(
            description="Example Maltego transform server",
            provider_name="Maltego Technologies",
            provider_phone='0123456789',
            provider_website="https://maltego.com",
            display_name="Jinxpy Full Example"
        )
    )
