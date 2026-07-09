# Copyright (c) Maltego Technologies GmbH.
import base64
import inspect
import logging
import typing
from collections import Counter
from packaging.version import Version, InvalidVersion
from typing import Any, List, Literal, Optional, Dict, Tuple, Type, Union
import time

import fastapi

from maltego.auth import AuthContext, optional_auth
from maltego.model import MaltegoPairedConfiguration
from maltego.model.context import MaltegoCapability, MaltegoContext, MaltegoUserAgent, MaltegoClientCapabilities
from maltego.model.entity import MaltegoEntity
from maltego.model.event import TransformEntityEvent
from maltego.model.exception import (
    MaltegoException, MaltegoHTTPClientError, MaltegoHTTPInputEntityMalformed, MaltegoNoTransformExecutorError,
)
from maltego.model.graph import MaltegoGraph
from maltego.model.link import MaltegoLink
from maltego.model.oauth import OAuthAuthenticator
from maltego.model.prompt import TransformPromptResponse
from maltego.model.server import EntityConfigOverrides, MaltegoHubItem, MaltegoServerSettings
from maltego.model.transform import MaltegoTransform
from maltego.model.transform_set import TransformSet
from maltego.model.types import MaltegoSettingTypes, ExecutionState
from maltego.protocol.v3.discovery.transform_set import V3TransformSetDefinition
from maltego.protocol.v3.execution.entity import TransformRunEntity
from maltego.runner import TransformRunner
from maltego.runner.transform_execution_context import MultiplexedTransformExecutionContext
from maltego.protocol.v3.discovery import V3AssetResponse
from maltego.protocol.v3.discovery.auth import V3OAuthServiceDefinition
from maltego.protocol.v3.discovery.capability import V3SupportedCapability, V3SupportedCapabilitiesResponse
from maltego.protocol.v3.discovery.entity import V3EntityDefinition
from maltego.protocol.v3.discovery.hub_item import V3HubItemProviderResponse, V3HubItemResponse
from maltego.protocol.v3.discovery.icon import V3IconDataDefinition, V3IconDefinition
from maltego.protocol.v3.discovery.machine import MachineRefs, V3MachineDefinition
from maltego.protocol.v3.discovery.status import V3StatusResponse
from maltego.protocol.v3.discovery.transform import TransformDefinitionCapabilities, V3TransformDefinition, V3Transforms
from maltego.protocol.v3.execution.transform_run import (
    SummaryItem,
    TransformRunRequest,
    TransformRunResponse,
    TransformRunInput, TransformRunPromptResponse,
    TransformRunStatus,
    TransformRunResult, TransformRunResultSummary, TransformRunExecutionContext
)
from maltego.server.capability_matrix import CapabilityNegotiator, ClientType, NegotiationContext, ResolvedCapabilitiesSet
from maltego.server.util import MALTEGO_PROTOCOL_VERSION_3_2, set_entities_added_header, \
    set_run_duration_header, \
    set_state_header, \
    set_protocol_version_header, set_vary_headers

log = logging.getLogger(__name__)

DEFAULT_FASTAPI_ARGS: Dict[str, Any] = {
    "response_model_exclude_none": True
}


def get_client_capabilities(
    maltego_client_capabilities: typing.Annotated[str | None, fastapi.Header(
        description="Optional comma-separated list of supported Maltego client capabilities."
    )] = None,
) -> MaltegoClientCapabilities:
    present = maltego_client_capabilities is not None
    caps: set[str] = set()

    if present:
        # Build a case-insensitive lookup for all known capability IDs
        canonical_by_lower = {f.id.lower(): f.id for f in MaltegoCapability}

        # treat 'interactive' as the highest interactive tier
        canonical_by_lower[TransformDefinitionCapabilities.INTERACTIVE.value.lower()] = MaltegoCapability.MULTI_CHOICE_CONTROLS.id

        for raw in (maltego_client_capabilities or "").split(","):
            t = raw.strip()
            if not t:
                continue
            canonical = canonical_by_lower.get(t.lower())
            if canonical:
                caps.add(canonical)

        # keep only known feature flagss
        known = {f.id for f in MaltegoCapability}
        caps &= known

    return MaltegoClientCapabilities(capabilities=caps, present=present)

def _parse_transform_capability_filter(raw: str | None) -> typing.Set[TransformDefinitionCapabilities]:
    """
    Parses TransformDefinitionCapabilities from a comma-separated string.
    :param raw:
    :return:
    """
    if not raw:
        return set()

    canonical_by_lower = {f.value.lower(): f for f in TransformDefinitionCapabilities}

    out: typing.Set[TransformDefinitionCapabilities] = set()
    for token in raw.split(","):
        t = token.strip().lower()
        if not t:
            continue
        cap = canonical_by_lower.get(t)
        if cap:
            out.add(cap)
    return out


def _proto_has_all_caps(
    proto: V3TransformDefinition,
    required: typing.Iterable[TransformDefinitionCapabilities],
) -> bool:
    if not required:
        return True
    have = set(proto.transform_capabilities or [])
    return set(required).issubset(have)


def _set_nested_attr(obj: Any, path: str, value: Any) -> bool:
    """
    Set a nested attribute using dot notation (e.g., "properties.display_value").

    Returns True if the attribute was set, False otherwise.
    """
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return False
    final_attr = parts[-1]
    if hasattr(obj, final_attr):
        setattr(obj, final_attr, value)
        return True
    return False


# Type alias for the pre-computed override lookup index
# Structure: {entity_id: {client_type: [(prop, value), ...]}}
OverrideLookupIndex = Dict[str, Dict[str, List[Tuple[str, Any]]]]


def build_override_lookup_index(config: Optional["EntityConfigOverrides"]) -> OverrideLookupIndex:
    """
    Build a lookup index from EntityConfigOverrides.

    This should be called once at startup/config load, not per-request.
    The index structure enables O(1) lookups by entity_id and client_type.

    Returns:
        Dict mapping entity_id -> client_type -> list of (prop, value) overrides
    """
    index: OverrideLookupIndex = {}
    if config is None:
        return index

    for rule in config.rules:
        for entity_id in rule.entities:
            if entity_id not in index:
                index[entity_id] = {}
            for client_type in rule.clients:
                if client_type not in index[entity_id]:
                    index[entity_id][client_type] = []
                # Append all overrides for this entity+client combination
                for prop, value in rule.overrides.items():
                    index[entity_id][client_type].append((prop, value))

    return index


def _apply_field_override_indexed(
    field_index: Dict[str, Any],
    field_name: str,
    field_attr: str,
    value: Any
) -> bool:
    """
    Apply an override to a specific field using pre-built field index.

    Args:
        field_index: Dict mapping field_name -> field object
        field_name: The name of the field to override
        field_attr: The attribute of the field to override (e.g., 'default_value', 'evaluator')
        value: The value to set

    Returns:
        True if the override was applied, False otherwise.
    """
    field = field_index.get(field_name)
    if field is None:
        return False
    if hasattr(field, field_attr):
        setattr(field, field_attr, value)
        return True
    return False


def apply_entity_config_overrides(
    entity_def: V3EntityDefinition,
    entity_type_id: str,
    client_type: Optional[str],
    override_index: Optional[OverrideLookupIndex],
) -> V3EntityDefinition:
    """
    Apply consumer-configured property overrides to an entity definition.

    Args:
        entity_def: The entity definition to modify
        entity_type_id: The entity TYPE_NAME (e.g., "maltego.Affiliation")
        client_type: The client type ("desktop", "web", or None)
        override_index: Pre-computed lookup index from build_override_lookup_index()

    Returns:
        The entity definition with any applicable overrides applied
    """
    if override_index is None or client_type is None:
        return entity_def

    # lookup for this entity + client combination
    entity_overrides = override_index.get(entity_type_id)
    if entity_overrides is None:
        return entity_def

    client_overrides = entity_overrides.get(client_type)
    if client_overrides is None:
        return entity_def

    # Build field index once for this entity (only if we have field overrides)
    field_index: Optional[Dict[str, Any]] = None

    for prop, value in client_overrides:
        # Check for field override syntax: fields.{field_name}.{attr}
        if prop.startswith("fields."):
            parts = prop.split(".", 2)  # Split into at most 3 parts
            if len(parts) == 3:
                _, field_name, field_attr = parts
                # Lazy-build field index on first field override
                if field_index is None:
                    if entity_def.properties is not None:
                        field_index = {f.name: f for f in (entity_def.properties.fields or [])}
                    else:
                        field_index = {}
                if not _apply_field_override_indexed(field_index, field_name, field_attr, value):
                    log.warning(
                        "Failed to apply field override %r=%r for entity %r: field or attribute not found.",
                        prop, value, entity_type_id
                    )
            else:
                log.warning(
                    "Invalid field override syntax %r for entity %r. Expected 'fields.{field_name}.{attr}'.",
                    prop, entity_type_id
                )
        elif "." in prop:
            if not _set_nested_attr(entity_def, prop, value):
                log.warning(
                    "Failed to apply override %r=%r for entity %r: invalid path.",
                    prop, value, entity_type_id
                )
        elif hasattr(entity_def, prop):
            setattr(entity_def, prop, value)
        else:
            log.warning(
                "Failed to apply override %r=%r for entity %r: unknown attribute.",
                prop, value, entity_type_id
            )

    return entity_def


def _has_coalesce_display_property(entity_def: V3EntityDefinition) -> bool:
    """
    Check if entity uses $coalesce() in a field default_value.

    Entities with coalesce expressions are not supported by desktop clients.
    Note: MEF validation ensures $coalesce() always has evaluator='maltego.replace'.
    """
    if entity_def.properties is None:
        return False

    fields = getattr(entity_def.properties, 'fields', None) or []
    for field in fields:
        default_value = getattr(field, 'default_value', None)
        if default_value is not None and "$coalesce(" in str(default_value):
            return True

    return False


def log_entity_config_overrides(config: Optional[EntityConfigOverrides]) -> None:
    """Log entity config overrides at server startup."""
    if config is None or not config.rules:
        return

    for rule in config.rules:
        overrides = ",".join(f"{k}={v}" for k, v in rule.overrides.items())
        clients = ",".join(rule.clients)
        for entity_id in rule.entities:
            log.info(f"entity_override: {entity_id} [{clients}] {overrides}")


def build_entity_map(raw_entities: List[TransformRunEntity]) -> Tuple[Dict[str, MaltegoEntity], typing.Set[str]]:
    """
    Builds a map of entity ID -> MaltegoEntity, resolving nested ENTITY refs in the process.
    Children (referenced via properties) are resolved before parents.
    """

    # validate all input entities have IDs
    ids = [raw.id for raw in raw_entities]
    if any(i is None for i in ids):
        log.error("All entities must have a non-empty 'id'")  # full detail in logs
        raise MaltegoHTTPInputEntityMalformed("Invalid request: malformed input entities")  # generic error detail for client

    # validate no duplicate IDs
    dupes = {i for i in ids if i is not None and ids.count(i) > 1}
    if dupes:
        log.error("Duplicate entity IDs in request: %s", sorted(dupes))  # full detail in logs
        raise MaltegoHTTPInputEntityMalformed("Invalid request: malformed input entities")  # generic error detail for client

    raw_by_id = {raw.id: raw for raw in raw_entities}
    entity_map: Dict[str, MaltegoEntity] = {}
    referenced_ids: typing.Set[str] = set()
    visiting: typing.Set[str] = set()  # detect cycles

    def resolve_entity(entity_id: str) -> MaltegoEntity:
        if entity_id in entity_map:
            return entity_map[entity_id]
        if entity_id in visiting:
            log.error("Cycle detected while resolving entity %r", entity_id)  # full detail in logs
            raise MaltegoHTTPInputEntityMalformed("Invalid request: malformed input entities")  # generic error detail for client

        raw = raw_by_id.get(entity_id)
        if not raw:
            log.error("Entity with ID %r not found in request payload", entity_id)  # full detail in logs
            raise MaltegoHTTPInputEntityMalformed("Invalid request: malformed input entities")  # generic error detail for client

        visiting.add(entity_id)
        try:
            for prop in (raw.properties or []):
                if prop.type == "ENTITY":
                    vals = prop.value
                    if isinstance(vals, str):
                        referenced_ids.add(vals)
                        resolve_entity(vals)
                    elif isinstance(vals, list):
                        for v in vals:
                            if isinstance(v, str):
                                referenced_ids.add(v)
                                resolve_entity(v)

            # pass the entity map in there to be able to look up properties of type ENTITY from the input
            entity = MaltegoEntity.from_v3_run_entity(raw, entity_typed_properties=entity_map)
            entity_map[entity_id] = entity
            return entity
        finally:
            visiting.discard(entity_id)

    for raw in raw_entities:
        resolve_entity(raw.id)

    return entity_map, referenced_ids


def get_root_entities(entity_map: Dict[str, MaltegoEntity], referenced_ids: typing.Set[str]) -> List[MaltegoEntity]:
    """
    From the given entity_map, return a deterministic list of entities
    which are not referenced in the id set (referenced_ids)
    :param entity_map: entity id and entity mapping as { maltego_entity_id : MaltegoEntity }
    :param referenced_ids: entity ids for entity-typed properties / only referenced entities
    :return:
    """
    root_ids = entity_map.keys() - referenced_ids
    return [entity_map[eid] for eid in sorted(root_ids)]


def get_transform_inputs(
    graph: MaltegoGraph[Any],
    transform: MaltegoTransform,
) -> typing.Tuple[
    Union[
        MaltegoGraph[Any],
        List[MaltegoEntity],
        MaltegoEntity,
        Union[MaltegoEntity, List[MaltegoEntity]]
    ],
    ...
]:
    input_annotation = transform.annotation.input
    # Graph
    if input_annotation.is_graph():
        return (graph,)

    # Union[Graph, ...]
    if input_annotation.is_union():
        for arg in typing.get_args(input_annotation):
            if inspect.isclass(arg) and issubclass(arg, MaltegoGraph):
                return (graph,)

    input_entities = graph.entities

    # MaltegoEntity
    if input_annotation.is_entity() or input_annotation.is_any_entity():
        return tuple(input_annotation.apply_entity_filter(input_entities))

    # List[MaltegoEntity]
    if input_annotation.is_iterable():
        return (input_annotation.apply_list_filter(input_entities),)

    # Union[MaltegoEntity | List[MaltegoEntity]
    if input_annotation.is_union():
        return tuple(input_annotation.apply_union_filter(input_entities))

    raise ValueError(
        f"Cannot get inputs for invalid annotation {input_annotation}")


class V3Server:

    def __init__(
            self,
            paired_config: MaltegoPairedConfiguration,
            settings: MaltegoServerSettings,
            runner: TransformRunner,
            hub_item: MaltegoHubItem
    ):
        if settings.api_prefix:
            self.set_prefix(settings.api_prefix)
        else:
            self.set_prefix("")
        legacy_prefix = (
            f"{settings.api_prefix}/api/v3"
            if settings.api_prefix
            else "api/v3"
        )
        self._legacy_prefixes = [legacy_prefix]
        self.assume_ssl: bool = False

        self._settings = settings
        self.transform_runner = runner
        self.transforms: Dict[str, MaltegoTransform] = {}
        self.paired_config = paired_config
        self.transform = None
        self.hub_item = hub_item
        self.startup_time = time.time()

        # Pre-compute override lookup index for O(1) lookups
        self._override_index = build_override_lookup_index(settings.entity_config_overrides)

    def set_prefix(self, prefix: Optional[str]) -> None:
        if prefix is not None:
            prefix = prefix.strip()
            if prefix.startswith("/"):
                prefix = prefix[1:]
            if prefix.endswith("/"):
                prefix = prefix[:-1]
        else:
            prefix = ""
        self._prefix = prefix

    def get_prefix(self) -> str:
        return self._prefix

    def set_transforms(self, transforms: Dict[str, MaltegoTransform]) -> None:
        self.transforms = transforms

    @staticmethod
    def _path(prefix: str, suffix: str = "") -> str:
        path = "/".join(elem.strip("/") for elem in [prefix, suffix] if elem.strip("/"))
        if not path:
            return "/"
        if not suffix:
            return f"/{path}/"
        return f"/{path}"

    def _register_routes(
            self,
            router: fastapi.APIRouter,
            prefix: str,
            include_in_schema: bool,
    ) -> None:
        route_args = {
            **DEFAULT_FASTAPI_ARGS,
            "include_in_schema": include_in_schema,
        }
        router.add_api_route(
            self._path(prefix, "assets"), self.assets,
            methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "assets/icons"),
            self.assets_icons, methods=["GET"],
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "assets/entities"), self.assets_entities, methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "assets/machines"), self.assets_machines, methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "assets/sets"), self.assets_sets, methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "assets/oauthservice"), self.assets_oauthservice, methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms"), self.get_transforms, methods=["GET"], **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}"),
            self.get_transform, methods=["GET"],
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run"),
            self.post_run_transform,
            methods=["POST"],
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run/{run_id}"),
            self.delete_transform_run,
            methods=["DELETE"],
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run/{run_id}/status"),
            self.get_transform_run_results,
            methods=["GET"],
            status_code=200,  # GET must return 200, not 201 (201 is for resource creation)
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run/{run_id}/results"),
            self.get_transform_run_results,
            methods=["GET"],
            status_code=200,  # GET must return 200, not 201 (201 is for resource creation)
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "status"),
            self.get_status,
            methods=["GET"],
            status_code=200,
            **route_args
        )
        router.add_api_route(
            self._path(prefix),
            self.get_status,
            methods=["GET"],
            status_code=200,
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run/{run_id}/prompts/{prompt_id}"),
            self.post_prompt_response,
            methods=["POST"],
            status_code=fastapi.status.HTTP_204_NO_CONTENT,
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "transforms/{transform_id}/run/{run_id}/cancel"),
            self.cancel_transform_run,
            methods=["POST"],
            status_code=fastapi.status.HTTP_200_OK,
            **route_args
        )
        router.add_api_route(
            self._path(prefix, "hub_item"),
            self.get_hub_item,
            methods=["GET"],
            status_code=200,
            include_in_schema=include_in_schema,
        )
        router.add_api_route(
            self._path(prefix, ".well-known/supported_capabilities"),
            self.list_supported_capabilities,
            methods=["GET"],
            status_code=200,
            include_in_schema=include_in_schema,
            # APIModel uses camelCase aliases by default; the capabilities
            # endpoint contract is snake_case.
            response_model_by_alias=False,
        )

    def prepare_app(self) -> fastapi.APIRouter:
        log.debug("Preparing transform protocol routes..")
        router = fastapi.APIRouter(dependencies=[fastapi.Depends(optional_auth)])
        self._register_routes(router, self._prefix, include_in_schema=True)
        registered_prefixes = {self._prefix}
        for prefix in self._legacy_prefixes:
            if prefix in registered_prefixes:
                continue
            self._register_routes(router, prefix, include_in_schema=False)
            registered_prefixes.add(prefix)
        return router

    @staticmethod
    def _to_proto_entity(entity: Type[MaltegoEntity], composed_graph: Optional[bool] = False) -> V3EntityDefinition:
        return MaltegoEntity.to_v3_entity_definition(entity, composed_graph)

    @staticmethod
    def _to_proto_icon(
        icon_name: str,
        icon_format: Literal['png', 'jpg', 'svg', 'webp'],
        category: str,
        data: Dict[int, bytes]
    ) -> V3IconDefinition:
        return V3IconDefinition(
            name=icon_name,
            format=icon_format,
            category=category,
            data=[
                V3IconDataDefinition(
                    size=size, blob=base64.b64encode(blob).decode('utf-8')
                ) for size, blob in data.items()
            ],
        )

    @staticmethod
    def _to_proto_machine(
        machine_name: str,
        machine_code: str,
        favorite: bool,
        enabled: bool,
        read_only: bool = False,
        machine_capabilities: typing.Optional[set[str]] = None,
        refs: typing.Optional[MachineRefs] = None,
    ) -> V3MachineDefinition:
        return V3MachineDefinition(
            name=machine_name,
            favorite=favorite,
            enabled=enabled,
            read_only=read_only,
            code=machine_code,
            machine_capabilities=sorted(machine_capabilities) if machine_capabilities else None,
            refs=refs,
        )

    @staticmethod
    def _to_proto_transform_set(transform_set_name: str, transform_set: Type[TransformSet]) -> V3TransformSetDefinition:
        return V3TransformSetDefinition(
            name=transform_set_name,
            description=transform_set.description,
            transforms=transform_set.transforms
        )

    @staticmethod
    def _to_proto_transform(transform: MaltegoTransform) -> V3TransformDefinition:
        return transform.to_v3_transform_definition()

    @staticmethod
    def _to_proto_authenticator(authenticator: OAuthAuthenticator) -> V3OAuthServiceDefinition:
        return authenticator.to_v3_oauth_service()

    def _to_proto_entities(
        self,
        resolved: Optional[ResolvedCapabilitiesSet] = None,
        negotiator: Optional[CapabilityNegotiator] = None,
    ) -> list[V3EntityDefinition]:
        comp_allowed = resolved.composite_entities if resolved else True
        flat_allowed = resolved.flattened_composite_entities if resolved else False

        # Determine client type for config overrides
        client_type: Optional[str] = None
        if negotiator is not None:
            ct = negotiator.get_client_type()
            if ct != ClientType.UNKNOWN:
                client_type = ct.value

        out: list[V3EntityDefinition] = []
        for entity_cls in self.paired_config.entities.values():
            is_composite = entity_cls.is_composite()

            if not is_composite:
                entity_def = self._to_proto_entity(entity_cls, composed_graph=comp_allowed)

                # Layer 1: Apply config overrides
                entity_def = apply_entity_config_overrides(
                    entity_def,
                    entity_cls.TYPE_NAME,
                    client_type,
                    self._override_index,
                )

                # Layer 2: Coalesce capability check (after overrides)
                if negotiator is not None and not negotiator.supports_coalesce():
                    if _has_coalesce_display_property(entity_def):
                        log.warning("Skipping entity %r: client does not support coalesce display_property.", entity_cls.TYPE_NAME)
                        continue

                out.append(entity_def)
                continue

            # Check if client supports composite entities
            if not (comp_allowed or flat_allowed):
                log.warning("Skipping entity %r: client does not support composite entities.", entity_cls.TYPE_NAME)
                continue

            use_composed_graph = comp_allowed
            entity_def = self._to_proto_entity(entity_cls, composed_graph=use_composed_graph)

            # Layer 1: Apply config overrides for composite entities too
            entity_def = apply_entity_config_overrides(
                entity_def,
                entity_cls.TYPE_NAME,
                client_type,
                self._override_index,
            )

            # Layer 2: Coalesce capability check for composite entities
            if negotiator is not None and not negotiator.supports_coalesce():
                if _has_coalesce_display_property(entity_def):
                    log.warning("Skipping entity %r: client does not support coalesce display_property.", entity_cls.TYPE_NAME)
                    continue

            out.append(entity_def)

        return out

    def _to_proto_authenticators(self) -> List[V3OAuthServiceDefinition]:
        return [V3Server._to_proto_authenticator(auth) for auth in self.paired_config.authenticators.values()]

    def _to_proto_icons(self) -> List[V3IconDefinition]:
        results: List[V3IconDefinition] = []
        for icon_name, map_ in self.paired_config.icons.items():
            results.append(
                V3Server._to_proto_icon(
                    icon_name,
                    "png",
                    map_["category"],
                    map_["data"]
                )
            )
        return results

    def _to_proto_transform_sets(self) -> List[V3TransformSetDefinition]:
        results: List[V3TransformSetDefinition] = []
        for transform_set_name, transform_set in self.paired_config.transform_sets.items():
            results.append(
                self._to_proto_transform_set(transform_set_name, transform_set)
            )
        return results

    def _to_proto_machines(self,
                           negotiator: Optional[CapabilityNegotiator] = None,
                           include_refs: Optional[bool] = False,
                           ) -> List[V3MachineDefinition]:
        results: List[V3MachineDefinition] = []
        do_negotiate = negotiator is not None and negotiator.ctx.should_negotiate()

        for machine_name, machine_cls in self.paired_config.machines.items():

            if do_negotiate and not negotiator.allows_machine(machine_cls):
                continue

            caps_display: typing.Set[str] = set()
            if machine_cls.interactive:
                caps_display.add(TransformDefinitionCapabilities.INTERACTIVE.value)
            if machine_cls.input_constraints:
                caps_display.add(TransformDefinitionCapabilities.INPUT_CONSTRAINTS.value)
            if machine_cls.composite_entities:
                caps_display.add(
                    TransformDefinitionCapabilities.COMPOSITE_ENTITIES.value)

            results.append(
                self._to_proto_machine(
                    machine_name=machine_name,
                    machine_code=machine_cls.code,
                    favorite=machine_cls.favorite,
                    enabled=machine_cls.enabled,
                    read_only=machine_cls.read_only,
                    machine_capabilities=caps_display or None,
                    refs=machine_cls.get_refs() if include_refs else None,
                )
            )
        return results

    async def assets_entities(self,
                              response: fastapi.Response,
                              maltego_protocol_version: typing.Annotated[str | None,
                                                                         fastapi.Header()] = None,
                              maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
                              maltego_client_identifier: typing.Annotated[str | None, fastapi.Header()] = None,
                              user_agent: typing.Annotated[str | None, fastapi.Header()] = None,
                              ) -> List[V3EntityDefinition]:
        set_protocol_version_header(response, maltego_protocol_version)
        set_vary_headers(response)

        ua = MaltegoUserAgent(user_agent)

        nctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            user_agent=ua,
            client_id=maltego_client_identifier,
        )
        negotiator = CapabilityNegotiator(nctx) if nctx.should_negotiate() else None
        resolved = negotiator.resolved if negotiator else None
        return self._to_proto_entities(resolved, negotiator=negotiator)

    async def assets_icons(self,
                           response: fastapi.Response,
                           maltego_protocol_version: typing.Annotated[str | None,
                                                                      fastapi.Header()] = None) -> List[V3IconDefinition]:
        set_protocol_version_header(response, maltego_protocol_version)
        return self._to_proto_icons()

    async def assets_machines(self,
                              response: fastapi.Response,
                              maltego_protocol_version: typing.Annotated[str | None,
                                                                         fastapi.Header()] = None,
                              maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
                              maltego_client_identifier: typing.Annotated[str | None, fastapi.Header()] = None,
                              include_refs: bool = fastapi.Query(False),
                              user_agent: typing.Annotated[str | None, fastapi.Header()] = None,
                              ) -> List[V3MachineDefinition]:
        set_protocol_version_header(response, maltego_protocol_version)
        set_vary_headers(response)

        ua = MaltegoUserAgent(user_agent)

        nctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            user_agent=ua,
            client_id=maltego_client_identifier,
        )
        return self._to_proto_machines(negotiator=CapabilityNegotiator(nctx),
                                       include_refs=include_refs,
                                       )

    async def assets_sets(self,
                          response: fastapi.Response,
                          maltego_protocol_version: typing.Annotated[str | None,
                                                                     fastapi.Header()] = None) -> List[V3TransformSetDefinition]:
        set_protocol_version_header(response, maltego_protocol_version)
        return self._to_proto_transform_sets()

    async def assets_oauthservice(self,
                                  response: fastapi.Response,
                                  maltego_protocol_version: typing.Annotated[str | None,
                                                                             fastapi.Header()] = None) -> List[V3OAuthServiceDefinition]:
        set_protocol_version_header(response, maltego_protocol_version)
        response.headers["maltego-transform-supported-oauth-formats"] = "jwe"
        return self._to_proto_authenticators()

    async def assets(self,
                     response: fastapi.Response,
                     maltego_protocol_version: typing.Annotated[str | None,
                                                                fastapi.Header()] = None,
                     maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
                     maltego_client_identifier: typing.Annotated[str | None, fastapi.Header()] = None,
                     user_agent: typing.Annotated[str | None, fastapi.Header()] = None,
                     ) -> V3AssetResponse:
        set_protocol_version_header(response, maltego_protocol_version)
        set_vary_headers(response)

        ua = MaltegoUserAgent(user_agent)
        nctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            user_agent=ua,
            client_id=maltego_client_identifier,
        )
        negotiate = nctx.should_negotiate()
        negotiator = CapabilityNegotiator(nctx) if negotiate else None
        resolved = negotiator.resolved if negotiator else None
        response.headers["maltego-transform-supported-oauth-formats"] = "jwe"

        return V3AssetResponse(
            entities=self._to_proto_entities(resolved, negotiator=negotiator),
            icons=self._to_proto_icons(),
            machines=self._to_proto_machines(negotiator=negotiator),
            transform_sets=self._to_proto_transform_sets(),
            o_auth_service=self._to_proto_authenticators()
        )

    async def get_transforms(
        self,
        response: fastapi.Response,
        user_agent: typing.Annotated[str | None, fastapi.Header()] = None,
        maltego_protocol_version: str = fastapi.Header(default=None),
        maltego_client_identifier: typing.Annotated[
            str | None, fastapi.Header()
        ] = None,
        maltego_client_version: typing.Annotated[str |
                                                 None, fastapi.Header()] = None,
        maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
        capabilities: Optional[str] = fastapi.Query(default=None),
    ) -> V3Transforms:
        set_protocol_version_header(response, maltego_protocol_version)
        set_vary_headers(response)
        response.headers["maltego-transform-supported-oauth-formats"] = "jwe"

        try:
            client_ver = Version(maltego_client_version) if maltego_client_version else None
        except InvalidVersion:
            client_ver = None

        ua = MaltegoUserAgent(user_agent)

        ctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            client_id=maltego_client_identifier,
            client_version=client_ver,
            user_agent=ua,
        )

        negotiator = CapabilityNegotiator(ctx)

        required_caps = _parse_transform_capability_filter(capabilities)

        transforms: List[V3TransformDefinition] = []
        for transform_ in self.transforms.values():
            if not negotiator.allows_transform(transform_):
                log.warning("Skipping transform %r due to negotiator rules.", transform_.name)
                continue

            def _append_if_caps_ok(proto: V3TransformDefinition) -> None:
                if required_caps and not _proto_has_all_caps(proto, required_caps):
                    # Try to log which caps are missing (best-effort)
                    present = set(proto.transform_capabilities or [])
                    missing = set(required_caps) - present
                    log.warning(
                        "Skipping transform %r: missing required capabilities %s (present=%s).",
                        proto.name, sorted(missing), sorted(present)
                    )
                    return
                transforms.append(proto)
                log.debug("Included transform %r.", proto.name)

            if transform_.client_filter:
                client_headers = {
                    "maltego-client-identifier": maltego_client_identifier,
                    "maltego-client-version": maltego_client_version,
                }
                success, reason = transform_.client_filter.match(user_agent=ua, headers=client_headers)
                if not success:
                    log.warning(
                        "Skipping transform %r: client filter failed (%s).",
                        transform_.name,
                        reason or "no reason provided"
                    )
                    continue

                proto = V3Server._to_proto_transform(transform_)
                _append_if_caps_ok(proto)
            else:
                proto = V3Server._to_proto_transform(transform_)
                if required_caps and not _proto_has_all_caps(proto, required_caps):
                    continue
                transforms.append(proto)

        return V3Transforms(
            transforms=transforms, oauth=self._to_proto_authenticators()
        )


    async def get_transform(
            self,
            transform_id: str,
            response: fastapi.Response,
            maltego_protocol_version: str = fastapi.Header(default=None),
    ) -> V3TransformDefinition:
        set_protocol_version_header(response, maltego_protocol_version)
        if transform_id not in self.transforms:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Transform with id {transform_id} not found"
            )
        return V3Server._to_proto_transform(self.transforms[transform_id])

    async def delete_transform_run(
            self,
            transform_id: str,
            run_id: str,
            request: fastapi.Request,
            response: fastapi.Response,
            maltego_protocol_version: str = fastapi.Header(default=None)
    ) -> TransformRunResultSummary:
        set_protocol_version_header(response, maltego_protocol_version)

        if self.transform_runner is None:
            raise MaltegoNoTransformExecutorError()

        added_entity_count: dict[str, int] = {}
        duration = 0
        atomic_entity_count = 0
        composite_entity_count = 0

        try:
            transform_result = self.transform_runner.result(run_id)
            # Validate that the looked-up run belongs to the path transform_id.
            # Prevents cross-transform result access (IDOR-style consistency check).
            # MultiplexedTransformExecutionContext has no .transform; access via .contexts[0].
            # The full transform ID is "{transform.ns}.{transform.name}" — must match the router key.
            _exec_ctx = self.transform_runner.get_execution_context(run_id)
            if isinstance(_exec_ctx, MultiplexedTransformExecutionContext):
                _t = _exec_ctx.contexts[0].transform if _exec_ctx.contexts else None
            else:
                _t = _exec_ctx.transform
            if _t is not None:
                _ctx_transform_id = f"{_t.ns}.{_t.name}".strip(".")
                if _ctx_transform_id != transform_id:
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_404_NOT_FOUND,
                        detail="Transform run not found",
                    )
            # Fetch the headers before deleting the transform run
            response.headers.update(
                self.transform_runner.response_headers(run_id))

            self.transform_runner.cancel(run_id)
            state = transform_result.state

            # Check query parameter for run cancelled by user to be added to v4.9.0 desktop client and web client
            cancelled_param = request.query_params.get(
                "Cancelled", "").strip().lower()
            if cancelled_param == "true":
                state = ExecutionState.CANCELED
                log.info(
                    f"Transform run {run_id} explicitly set to CANCELED via query parameter.")

            # When delete is sent, and we are in a state other than terminal states we assume it was canceled
            elif state not in {ExecutionState.FINISHED, ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.TIMED_OUT}:
                log.warning(
                    f"Unexpected state {state.value} for run {run_id}. Defaulting to CANCELED.")
                state = ExecutionState.CANCELED

            added_entities = self.transform_runner.output_entities(run_id)
            added_entity_count = dict(
                Counter([entity.TYPE_NAME for entity in added_entities]))

            duration = transform_result.get_duration()
            atomic_entity_count = transform_result.atomic_entity_count
            composite_entity_count = transform_result.composite_entity_count

            self.transform_runner.delete(run_id)

        except KeyError:
            log.error(f"Transform run {run_id} not found.")  # full detail in logs
            key_exception = fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Transform run not found",  # generic detail for client
                headers={},
            )
            set_state_header(ExecutionState.FAILED, key_exception)
            raise key_exception
        except fastapi.HTTPException:
            # The transform_id<->run_id mismatch guard raises HTTPException(404)
            # inside this try block. Re-raise it untouched so FastAPI returns the 404;
            # otherwise the broad handler below would mask it as a 500.
            raise
        except Exception as e:
            set_state_header(ExecutionState.FAILED, response)
            log.exception(
                f"An unexpected error occurred while deleting run {run_id}: {str(e)}")
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing the transform run."
            )

        set_state_header(state, response)
        # add the duration to the response header
        set_run_duration_header(duration, response)
        set_entities_added_header(added_entity_count, response)

        log.debug(
            f"Transform run {run_id} deleted with final state {state}. Duration: {duration} ms.")
        result_summary = TransformRunResultSummary(
            entities=SummaryItem(added=added_entity_count),
            run_id=run_id,
            state=ExecutionState.FAILED.value if state is ExecutionState.TIMED_OUT else state.value,
            duration=duration,
            atomic_entity_count=atomic_entity_count,
            composite_entity_count=composite_entity_count,
        )
        response.status_code = fastapi.status.HTTP_200_OK
        return result_summary

    async def cancel_transform_run(
            self,
            transform_id: str,  # pylint: disable=unused-argument # part of the route path
            run_id: str,
            request: fastapi.Request,  # pylint: disable=unused-argument # signature parity with delete_transform_run
            response: fastapi.Response,
            maltego_protocol_version: str = fastapi.Header(default=None),
            # Accepted but not required: matches the dependency /results uses so
            # composition negotiation works when present and is simply off when
            # absent (no 4xx for clients that omit the header).
            maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(  # pylint: disable=unused-argument
                get_client_capabilities),
    ) -> TransformRunResultSummary:
        """Cancel a transform run without tearing it down.

        Unlike ``delete_transform_run`` this calls ``cancel`` but **not**
        ``delete``: the run context stays alive so the client can keep draining
        the remaining events via ``GET .../results``. The run is torn down later
        by an explicit ``DELETE`` or by the existing idle reaper.
        """
        set_protocol_version_header(response, maltego_protocol_version)

        if self.transform_runner is None:
            raise MaltegoNoTransformExecutorError()

        added_entity_count: dict[str, int] = {}
        duration = 0
        atomic_entity_count = 0
        composite_entity_count = 0

        try:
            transform_result = self.transform_runner.result(run_id)
            # Validate that the looked-up run belongs to the path transform_id.
            # Prevents cross-transform result access (IDOR-style consistency check).
            # MultiplexedTransformExecutionContext has no .transform; access via .contexts[0].
            # The full transform ID is "{transform.ns}.{transform.name}" — must match the router key.
            _exec_ctx = self.transform_runner.get_execution_context(run_id)
            if isinstance(_exec_ctx, MultiplexedTransformExecutionContext):
                _t = _exec_ctx.contexts[0].transform if _exec_ctx.contexts else None
            else:
                _t = _exec_ctx.transform
            if _t is not None:
                _ctx_transform_id = f"{_t.ns}.{_t.name}".strip(".")
                if _ctx_transform_id != transform_id:
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_404_NOT_FOUND,
                        detail=f"Could not find transform run with id {run_id}",
                    )
            response.headers.update(
                self.transform_runner.response_headers(run_id))

            self.transform_runner.cancel(run_id)
            state = ExecutionState.CANCELED

            added_entities = self.transform_runner.output_entities(run_id)
            added_entity_count = dict(
                Counter([entity.TYPE_NAME for entity in added_entities]))

            duration = transform_result.get_duration()
            atomic_entity_count = transform_result.atomic_entity_count
            composite_entity_count = transform_result.composite_entity_count

        except KeyError:
            log.error(f"Transform run {run_id} not found.")
            key_exception = fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Could not find transform run with id {run_id}",
                headers={},
            )
            set_state_header(ExecutionState.FAILED, key_exception)
            raise key_exception
        except fastapi.HTTPException:
            # The transform_id<->run_id mismatch guard raises HTTPException(404)
            # inside this try block. Re-raise it untouched so FastAPI returns the 404;
            # otherwise the broad handler below would mask it as a 500.
            raise
        except Exception as e:
            set_state_header(ExecutionState.FAILED, response)
            log.exception(
                f"An unexpected error occurred while cancelling run {run_id}: {str(e)}")
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing the transform run."
            )

        set_state_header(state, response)
        set_run_duration_header(duration, response)
        set_entities_added_header(added_entity_count, response)

        log.debug(
            f"Transform run {run_id} cancelled with final state {state}. Duration: {duration} ms.")
        result_summary = TransformRunResultSummary(
            entities=SummaryItem(added=added_entity_count),
            run_id=run_id,
            state=state.value,
            duration=duration,
            atomic_entity_count=atomic_entity_count,
            composite_entity_count=composite_entity_count,
        )
        response.status_code = fastapi.status.HTTP_200_OK
        return result_summary

    def get_event_limit(self, event_limit: int) -> int:
        if event_limit <= 0:
            event_limit = self._settings.v3_page_size_max
        return min(event_limit, self._settings.v3_page_size_max)

    def __parse_transform_run_request(
        self,
        transform_run_request: TransformRunRequest,
        transform: MaltegoTransform
    ) -> Tuple[Dict[str, MaltegoSettingTypes], int, int, Union[None, TransformRunExecutionContext]]:
        transform_settings_raw = transform_run_request.transformSettings or []
        soft_limit = transform_run_request.limit
        hard_limit = transform_run_request.limit

        transform_settings = transform.prepare_settings(
            {
                transform_setting.name: transform_setting.value
                for transform_setting in transform_settings_raw
            },
            transform
        )

        transform_run_execution_context = transform_run_request.transformRunExecutionContext
        return transform_settings, hard_limit, soft_limit, transform_run_execution_context

    def __schedule_transform(
        self,
        transform_run_request: TransformRunRequest,
        transform: MaltegoTransform,
        request: fastapi.Request,
        maltego_api_key: str,
        resolved_caps: ResolvedCapabilitiesSet,
    ) -> str:
        transform_settings, hard_limit, soft_limit, transform_run_execution_context = self.__parse_transform_run_request(
            transform_run_request,
            transform
        )
        remote_ip = request.client.host if request.client else None

        try:
            entity_map, referenced_ids = build_entity_map(transform_run_request.input.graph.entities)
            root_entities = get_root_entities(entity_map, referenced_ids)
            links = [MaltegoLink.from_v3_run_link(
                link) for link in transform_run_request.input.graph.links]
            graph: MaltegoGraph[Any] = MaltegoGraph(
                entities=root_entities,
                links=links
            )
            context = MaltegoContext(
                graph,
                request,
                api_key=maltego_api_key,
                remote_ip=remote_ip,
                v3_request=True,
                transform_run_execution_context=transform_run_execution_context,
                capabilities=resolved_caps,
                auth_context=AuthContext.from_request_state(request.state),
            )
            transform_inputs = get_transform_inputs(graph, transform)
            if len(transform_inputs) == 0:
                log.error(f"No matching transform_inputs in {transform.name}. "
                          f"Allowed types: {transform.annotation.input.get_entities_type_ids()}")
                log.debug(f"Input entities: {graph.entities}")
                if context.ua.version_lt(4, 6, 0):
                    transform_inputs = tuple(graph.entities)
                    log.warning(
                        "Falling back to pass all input entities to transform "
                        "for compatibility with older Maltego client versions."
                    )
                else:
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                        detail="No input entity matches the transforms signature"
                    )
            if len(transform_inputs) == 1:
                run_id = self.transform_runner.schedule_transform(
                    transform,
                    transform_inputs[0],
                    transform_settings,
                    hard_limit or soft_limit or 12,
                    context
                )
            else:
                run_id = self.transform_runner.schedule_transform_list_in(
                    transform,
                    transform_inputs,
                    transform_settings,
                    hard_limit or soft_limit or 12,
                    context
                )
        # TODO: standardize non-classic errors on RFC 9457 problem+json;
        # keep classic 240/241 codes for v2 compat. Needs a design decision
        # on which endpoints switch and whether v2 clients handle the new content type.
        except MaltegoHTTPClientError as e:
            raise fastapi.HTTPException(
                status_code=e.code or fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.message or "Malformed input",
            )
        except MaltegoException as e:
            raise fastapi.HTTPException(
                status_code=e.code or fastapi.status.HTTP_400_BAD_REQUEST,
                detail=e.message or "Bad request",
            )
        except ValueError as e:
            log.debug("Validation error scheduling transform: %s", e)
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Invalid input.",
            )
        except fastapi.HTTPException as e:
            raise e
        except Exception as e:
            log.exception("Unexpected error while scheduling transform")
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected server error occurred.",
            )
        return run_id

    async def post_run_transform(  # pylint: disable=too-many-statements
            self,
            transform_id: str,
            transform_run_request: TransformRunRequest,
            request: fastapi.Request,
            response: fastapi.Response,
            maltego_api_key: str = fastapi.Header(default=None),
            event_pointer: int = fastapi.Query(
                default=0, alias="eventPointer"),
            event_limit: int = fastapi.Query(default=0, alias="eventLimit"),
            maltego_protocol_version: str = fastapi.Header(default=None),
            maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
    ) -> TransformRunResponse:
        set_protocol_version_header(response, maltego_protocol_version)
        event_limit = self.get_event_limit(event_limit)

        transform: Optional[MaltegoTransform] = self.transforms.get(
            transform_id)
        if transform is None:
            set_state_header(ExecutionState.FAILED, response)
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Transform with id {transform_id} not found"
            )

        if not isinstance(transform_run_request.input, TransformRunInput):
            set_state_header(ExecutionState.FAILED, response)
            raise fastapi.HTTPException(
                detail=f"Unsupported request_input: {transform_run_request.input}",
                status_code=400
            )

        if self.transform_runner is None:
            set_state_header(ExecutionState.FAILED, response)
            raise MaltegoNoTransformExecutorError()

        ua = MaltegoUserAgent(request.headers.get("User-Agent"))
        try:
            if mcl := request.headers.get("Maltego-Client-Version"):
                client_ver = Version(mcl)
            else:
                client_ver = None
        except InvalidVersion:
            client_ver = None

        nctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            client_id=request.headers.get("Maltego-Client-Identifier"),
            client_version=client_ver,
            user_agent=ua,
        )
        negotiator = CapabilityNegotiator(nctx)
        resolved = negotiator.resolved

        if transform.composite_entities and not (
                resolved.composite_entities or resolved.flattened_composite_entities
        ):
            set_state_header(ExecutionState.FAILED, response)
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_412_PRECONDITION_FAILED,
                detail="Transform uses composite entities or flattened composite entities.",
            )

        run_id = self.__schedule_transform(
            transform_run_request=transform_run_request,
            transform=transform,
            request=request,
            maltego_api_key=maltego_api_key,
            resolved_caps=resolved,
        )
        try:
            transform_result = self.transform_runner.result(run_id)
        except KeyError:
            set_state_header(ExecutionState.FAILED, response)
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=f"Could not find transform run with id {run_id}"
            )

        result_response = TransformRunResponse(
            result=TransformRunResult(
                event_pointer=event_pointer,
                event_count=transform_result.event_count,
                events=[
                    event.to_v3_event(resolved.composite_entities) if isinstance(event, TransformEntityEvent)
                    else event.to_v3_event()
                    for event in transform_result.get_results()[
                        event_pointer:(event_pointer + event_limit)
                    ]
                ],
                run_id=run_id,
                state=transform_result.state.value,
                start_time=str(transform_result.start_time),
                update_time=str(transform_result.update_time),
            ),
            status=TransformRunStatus(
                ui_messages=[],
            )
        )
        response.status_code = fastapi.status.HTTP_201_CREATED
        self.transform_runner.start_transform(run_id)
        set_state_header(transform_result.state, response)
        return result_response

    async def get_transform_run_results(
            self,
            transform_id: str,
            run_id: str,
            response: fastapi.Response,
            event_pointer: int = fastapi.Query(
                default=0, alias="eventPointer"),
            event_limit: int = fastapi.Query(default=0, alias="eventLimit"),
            maltego_protocol_version: str = fastapi.Header(default=None),
            maltego_client_capabilities: MaltegoClientCapabilities = fastapi.Depends(get_client_capabilities),
            maltego_client_identifier: typing.Annotated[
                str | None, fastapi.Header()
            ] = None,
            maltego_client_version: typing.Annotated[str |
                                                     None, fastapi.Header()] = None,
            user_agent: typing.Annotated[str | None, fastapi.Header()] = None,
    ) -> TransformRunResponse:
        set_protocol_version_header(response, maltego_protocol_version)
        event_limit = self.get_event_limit(event_limit)
        try:
            transform_result = self.transform_runner.result(run_id)
        except KeyError:
            key_exception = fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Transform run not found",
                headers={},
            )
            set_state_header(ExecutionState.TIMED_OUT, key_exception)
            raise key_exception

        # Validate that the looked-up run belongs to the path transform_id.
        # Prevents cross-transform result access (IDOR-style consistency check).
        # MultiplexedTransformExecutionContext has no .transform; access via .contexts[0].
        # The full transform ID is "{transform.ns}.{transform.name}" — must match the router key.
        try:
            _exec_ctx = self.transform_runner.get_execution_context(run_id)
            if isinstance(_exec_ctx, MultiplexedTransformExecutionContext):
                _t = _exec_ctx.contexts[0].transform if _exec_ctx.contexts else None
            else:
                _t = _exec_ctx.transform
            if _t is not None:
                _ctx_transform_id = f"{_t.ns}.{_t.name}".strip(".")
                if _ctx_transform_id != transform_id:
                    raise fastapi.HTTPException(
                        status_code=fastapi.status.HTTP_404_NOT_FOUND,
                        detail="Transform run not found",
                    )
        except KeyError:
            pass  # run may have been deleted between result() and get_execution_context()

        duration = transform_result.get_current_duration()
        # add current transform run duration to the polling response header
        set_run_duration_header(duration, response)

        set_state_header(transform_result.state, response)
        set_vary_headers(response)

        ua = MaltegoUserAgent(user_agent)

        nctx = NegotiationContext(
            client_capabilities=maltego_client_capabilities,
            protocol_version=maltego_protocol_version,
            client_id=maltego_client_identifier,  # no request here; fine to omit
            client_version=maltego_client_version,
            user_agent=ua,
        )
        resolved = CapabilityNegotiator(nctx).resolved

        boundary_index = event_pointer + event_limit

        return TransformRunResponse(
            result=TransformRunResult(
                event_pointer=event_pointer,
                event_count=transform_result.event_count,
                atomic_entity_count=transform_result.atomic_entity_count,
                composite_entity_count=transform_result.composite_entity_count,
                incomplete_composite_entity=transform_result.ends_mid_composite(
                    boundary_index),
                events=[
                    event.to_v3_event(resolved.composite_entities) if isinstance(event, TransformEntityEvent)
                    else event.to_v3_event()
                    for event in transform_result.get_results()[
                        event_pointer:boundary_index]
                ],
                run_id=run_id,
                state=ExecutionState.FAILED.value if transform_result.state is ExecutionState.TIMED_OUT else transform_result.state.value,
                start_time=str(transform_result.start_time),
                update_time=str(transform_result.update_time),
            ),
            status=TransformRunStatus(
                ui_messages=[],
            )
        )

    async def get_status(
            self,
            response: fastapi.Response,
            maltego_protocol_version: str = fastapi.Header(default=None)
    ) -> V3StatusResponse:
        set_protocol_version_header(response, maltego_protocol_version)
        return V3StatusResponse(
            startup_time=self.startup_time,
            v3_transform_count=len(self.transforms),
            v2_transform_count=0,
            entity_count=len(self.paired_config.entities),
            entity_category_count=len(self.paired_config.entity_categories),
            transform_set_count=len(self.paired_config.transform_sets),
            icon_count=len(self.paired_config.icons),
            machine_count=len(self.paired_config.machines),
        )

    async def get_hub_item(
            self,
            response: fastapi.Response,
            maltego_protocol_version: str = fastapi.Header(default=None)
    ) -> V3HubItemResponse:
        set_protocol_version_header(response, maltego_protocol_version)
        return V3HubItemResponse(
            id=self._settings.ns,
            display_name=self.hub_item.display_name or self._settings.server_name,
            description=self.hub_item.description,
            icon_url=self.hub_item.icon_url,
            preview_image_url=self.hub_item.preview_image_url,
            provider=V3HubItemProviderResponse(
                name=self.hub_item.provider_name or self._settings.owner,
                website=self.hub_item.provider_website,
                email=self.hub_item.provider_email or self._settings.author,
                phone=self.hub_item.provider_phone),
        )

    async def post_prompt_response(
            self,
            transform_id: str,
            run_id: str,
            prompt_id: str,
            response: fastapi.Response,
            transform_run_prompt_response: TransformRunPromptResponse,
            maltego_protocol_version: str = fastapi.Header(default=None)
    ) -> fastapi.Response:
        set_protocol_version_header(response, maltego_protocol_version)
        transform: Optional[MaltegoTransform] = self.transforms.get(
            transform_id)
        if transform is None:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Transform with id {transform_id} not found"
            )
        if self.transform_runner is None:
            raise MaltegoNoTransformExecutorError()
        try:
            transform_prompt_response = TransformPromptResponse()
            transform_prompt_response.result = transform_run_prompt_response.result
            transform_prompt_response.reason = transform_run_prompt_response.reason

            transform_result = self.transform_runner.result(run_id)
            set_state_header(transform_result.state, response)
            if transform_result.state == ExecutionState.TIMED_OUT:
                timeout_exception = fastapi.HTTPException(
                    status_code=fastapi.status.HTTP_410_GONE,
                    detail=f"The transform execution context for {run_id} has expired.",
                    headers={},
                )
                set_state_header(ExecutionState.TIMED_OUT, timeout_exception)
                raise timeout_exception
            await self.transform_runner.prompt_response(run_id, prompt_id, transform_prompt_response)
        except ValueError as e:
            log.debug("Validation error submitting prompt response: %s", e)
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_400_BAD_REQUEST,
                detail="Invalid input.",
            )
        except KeyError as e:
            log.debug("Execution context not found for run_id=%s: %s", run_id, e)
            key_error = fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Resource not found.",
                headers={},
            )
            set_state_header(ExecutionState.FAILED, key_error)
            raise key_error

        response.status_code = fastapi.status.HTTP_204_NO_CONTENT
        return response

    async def list_supported_capabilities(self) -> V3SupportedCapabilitiesResponse:
        """
        Lists all supported optional server capabilities of this version.
        Can be enabled via `maltego-client-capabilities` in supported endpoints.
        :return: List of capabilities that can be used in `maltego-client-capabilities` header.
        """
        return V3SupportedCapabilitiesResponse(
            protocol=MALTEGO_PROTOCOL_VERSION_3_2,
            supported_capabilities=[
                V3SupportedCapability(
                    name=capability.value,
                    description=capability.description,
                )
                for capability in MaltegoCapability
            ],
        )
