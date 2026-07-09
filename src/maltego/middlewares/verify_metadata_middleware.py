# Copyright (c) Maltego Technologies GmbH.
import logging
from collections import defaultdict
from json import JSONDecodeError
from typing import Dict, Optional, Union, List, Any, Sequence

from maltego.model.entity import MaltegoEntity
from maltego.model.context import MaltegoContext
from maltego.model.graph import MaltegoGraph
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.exception import MaltegoException
from maltego.model.transform import MaltegoTransform
from maltego.model.types import MaltegoSettingTypes, ExecutionState


class VerifyMetadataMiddleware(TransformMiddleware):

    async def before_transform(self,  # pylint: disable=unused-argument
                               transform: MaltegoTransform,
                               transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
                               properties: Dict[str, MaltegoSettingTypes],
                               context: MaltegoContext,
                               soft_limit: int,
                               hard_limit: int
                               ) -> None:
        if not context.v3_request:
            logging.debug(
                f"{self.__class__.__name__}: V3 Middleware does not support runs on v2 context"
            )
            return

        try:
            if context.request:
                body = await context.request.json()
            else:
                raise MaltegoException("Context has no request body to parse")
        except JSONDecodeError:
            raise MaltegoException("Could not parse request body as json")
        try:
            expected_types_stats = body['input']['metadata']['entitiesTypesStat']
            expected_entity_count = int(body['input']['metadata']['entitiesTotalCount'])
            entities = body['input']['graph']['entities']
        except (AttributeError, KeyError, TypeError):
            raise MaltegoException("Malformed request body")

        actual_type_stats: Dict[str, int] = defaultdict(lambda: 0)
        for entity in entities:
            for base_entities in entity.get("baseEntities", []):
                actual_type_stats[base_entities] += 1
            actual_type_stats[entity['type']] += 1

        actual_type_stats = dict(actual_type_stats)
        if expected_types_stats != actual_type_stats:
            context.log.fatal("Metadata validation failed")
            raise MaltegoException(
                message="Mismatch between request metadata and actual content"
            )
        if expected_entity_count != len(entities):
            raise MaltegoException(
                message="Mismatch between number of entities in request and number of entities in metadata"
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
