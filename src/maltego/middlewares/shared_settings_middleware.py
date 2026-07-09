# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Dict, Optional, Union, List, Sequence
import logging
import json
from json import JSONDecodeError
from cachetools import cached, TTLCache

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.entity import MaltegoEntity
from maltego.model.context import MaltegoContext
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.types import MaltegoSettingTypes, ExecutionState

log = logging.getLogger(__name__)

SHARED_CONFIG_PATH = "/etc/maltego/api_keys.json"

# cache locally for max 2 minutes, let's see how this affects performance
# another option would be caching the whole dict
#  - but if we add a new key, this will force an update
#  - is probably only 1 shared setting per server so effectively the same as caching all keys


@cached(cache=TTLCache(ttl=60 * 2, maxsize=2048))
def get_shared_setting(key: str) -> Optional[Any]:
    try:
        with open(SHARED_CONFIG_PATH, encoding='utf-8') as conf_json:
            shared_settings = json.load(conf_json)

            return shared_settings.get(key)

    except FileNotFoundError:
        log.error(
            f"FileNotFoundError: couldn't load shared settings from {SHARED_CONFIG_PATH}")
    except PermissionError:
        log.error(
            f"PermissionError: permission denied for shared settings at {SHARED_CONFIG_PATH}")
    except JSONDecodeError:
        log.error(
            f"JSONDecodeError: malformed shared settings json at {SHARED_CONFIG_PATH}")
    return None


class SharedSettingsMiddleware(TransformMiddleware):

    async def before_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        properties: Dict[str, MaltegoSettingTypes],
        context: MaltegoContext,
        soft_limit: int,
        hard_limit: int
    ) -> None:
        for key, value in properties.items():
            if value is None or (isinstance(value, str) and value.strip() == ''):
                # Fail closed — only inject shared setting when one actually
                # exists. A None return from get_shared_setting means the file is
                # missing or the key is absent; do not substitute None for a
                # blank client value (would inject an empty/missing secret).
                shared = get_shared_setting(key)
                if shared is not None:
                    properties[key] = shared
                else:
                    log.warning(
                        "SharedSettingsMiddleware: no shared setting found for key %r; "
                        "leaving client-supplied value as-is (fail-closed).",
                        key,
                    )

    async def after_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            output_entities: List[MaltegoEntity],
            context: MaltegoContext,
            state: ExecutionState,
            exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        return await super().after_transform(transform, transform_input, output_entities, context, state, exceptions)
