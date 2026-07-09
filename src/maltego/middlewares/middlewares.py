# Copyright (c) Maltego Technologies GmbH.
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, Sequence
import logging

from maltego.model.graph import MaltegoGraph
from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.transform import MaltegoTransform
from maltego.model.types import MaltegoSettingTypes, ExecutionState

log = logging.getLogger(__name__)


class TransformMiddleware(ABC):
    call_on_failure = True

    @abstractmethod
    async def before_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            properties: Dict[str, MaltegoSettingTypes],
            context: MaltegoContext,
            soft_limit: int,
            hard_limit: int
    ) -> None:
        """
        Needs to be implemented by middleware. Gets the transform object and metadata as input before it gets executed

        :param transform: Transform object of transform to be executed
        :type transform: MaltegoTransform
        :param transform_input: Input entities or graph used in transform execution
        :type transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]]
        :param properties: Transform settings sent by the client
        :type properties: Dict[str, MaltegoSettingTypes]
        :param context: Server context for this transform execution
        :type context: MaltegoContext
        :param soft_limit: Soft limit as sent by the client (requested number of entities)
        :type soft_limit: int
        :param hard_limit: Hard limit as sent by the client (maximum possible number of entities useable by a client)
        :type hard_limit: int
        """
        limit = hard_limit or soft_limit
        log.debug(
            f"middleware {self} {__name__} called on input {transform_input} "
            f"for transform {transform.name} with {len(properties)} properties "
            f"{limit=}"
        )

    @abstractmethod
    async def after_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            output_entities: List[MaltegoEntity],
            context: MaltegoContext,
            state: ExecutionState,
            exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        """
        Needs to be implemented by middleware. Gets the transform object and metadata as input after it gets executed

        :param transform: Transform object of transform to be executed
        :type transform: MaltegoTransform
        :param transform_input: Input entities or graph used in transform execution
        :type transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]]
        :param output_entities: List of entities returned by the transform
        :type output_entities: List[MaltegoEntity]
        :param context: Server context for this transform execution
        :type context: MaltegoContext
        :param exceptions: A sequence of exceptions raised throughout transform execution
        :type exceptions: Optional[Sequence[Exception]]
        """
        log.debug(
            f"middleware {self} {__name__} called on input {transform_input} "
            f"for transform {transform.name} returned with {len(output_entities)} entities "
            f"and {len(exceptions) if exceptions else 0} exceptions. State: {state}"
        )
