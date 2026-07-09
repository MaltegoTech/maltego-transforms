import functools
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Union

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field

from maltego.model import MaltegoMachine
from maltego.model.context import MaltegoCapability, MaltegoClientCapabilities, MaltegoUserAgent, \
    ResolvedCapabilitiesSet
from maltego.model.transform import MaltegoTransform


# Client identifiers
CLIENT_ID_GRAPH_BROWSER = "Maltego Graph Browser"


class ClientType(str, Enum):
    """Type of Maltego client making the request."""
    WEB = "web"
    DESKTOP = "desktop"
    UNKNOWN = "unknown"


CONSTRAINT_MIN_DESKTOP: Dict[str, Version] = {
    "property_value_equals": Version("4.10.0"),
    "property_display_name_equals": Version("4.10.0"),
    "property_name_equals": Version("4.10.0"),
    "property_type_equals": Version("4.10.0"),

    "property_value_string_match": Version("4.10.0"),
    "property_display_name_string_match": Version("4.10.0"),
    "property_name_string_match": Version("4.10.0"),

    "property_value_matches_regex": Version("4.10.0"),
    "property_display_name_matches_regex": Version("4.10.0"),
    "property_name_matches_regex": Version("4.10.0"),

    "property_satisfies_all": Version("4.10.0"),
    "property_satisfies_any": Version("4.10.0"),
    "property_satisfies_none": Version("4.10.0"),

    "entity_satisfies_all": Version("4.10.0"),
    "entity_satisfies_any": Version("4.10.0"),
    "entity_satisfies_none": Version("4.10.0"),
    "entity_type_constraint": Version("4.10.0"),
    "entity_has_property_satisfying": Version("4.10.0"),
}

# Minimum Desktop version that supports $coalesce() in display_property
# Set to a future version as desktop currently doesn't support coalesce
COALESCE_MIN_DESKTOP: Version = Version("9.9.9")


def _looks_like_constraint(obj) -> bool:
    return obj is not None and (hasattr(obj, "type") or hasattr(obj, "evaluate"))


def _iter_children(node) -> Iterable[object]:
    for name in ("constraints", "constraint"):
        if hasattr(node, name):
            child = getattr(node, name)
            if isinstance(child, (list, tuple)):
                for c in child:
                    if _looks_like_constraint(c):
                        yield c
            else:
                if _looks_like_constraint(child):
                    yield child


def extract_constraint_type_ids(root) -> set[str]:
    """
    Traverses an input constraint top down,
    collects all used constraint into flat set
    :param root:
    :return:
    """
    if root is None:
        return set()
    seen: set[int] = set()
    out: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        nid = id(node)
        if nid in seen:
            continue
        seen.add(nid)

        t = getattr(node, "type", None)
        if isinstance(t, str):
            out.add(t)
        else:
            # Fallback: class name
            out.add(node.__class__.__name__)

        stack.extend(_iter_children(node))
    return out


def supported_constraint_types_for_desktop(cv: Version | None) -> Set[str]:
    """
    Returns the set of constraint type ids supported by a Desktop client version.
    If version is unknown, assume 4.10.0
    """
    if cv is None:
        cv = Version("4.10.0")
    return {t for t, min_v in CONSTRAINT_MIN_DESKTOP.items() if cv >= min_v}


class ClientVersionConstraint(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client_id: str
    min_version: Version


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    description: str
    client_version_constraints: List[ClientVersionConstraint] = Field(default_factory=list)
    min_protocol_version: Optional[Version] = None


# Maltego capability‐matrix, defined as a Python list of models
CAPABILITY_MATRIX: List[CapabilityDefinition] = [
    CapabilityDefinition(
        id="inputConstraints",
        description="Show transforms that declare structured input constraints",
        client_version_constraints=[
            ClientVersionConstraint(client_id="Maltego Desktop",
                                    min_version=Version("4.10.0")),
        ]
    ),
    CapabilityDefinition(
        id="inputConstraintsUnknownSafe",
        description="Client tolerates unknown input constraint types during discovery",
        client_version_constraints=[
            ClientVersionConstraint(client_id="Maltego Desktop", min_version=Version("5.0.0")),
        ],
    ),
    CapabilityDefinition(
        id="promptBase",
        description="Enable the transform-prompt API",
        client_version_constraints=[
            ClientVersionConstraint(client_id="Maltego Desktop",
                                    min_version=Version("4.6.0")),
        ]
    ),
    CapabilityDefinition(
        id="choiceControlType",
        description="Allow specifying control types in choice prompts",
        client_version_constraints=[
            ClientVersionConstraint(client_id="Maltego Desktop",
                                    min_version=Version("4.6.1")),
        ]
    ),
    CapabilityDefinition(
        id="multiChoiceControls",
        description="Support multiple controls per prompt",
        client_version_constraints=[
            ClientVersionConstraint(client_id="Maltego Desktop",
                                    min_version=Version("4.7.2")),
        ]
    ),
    CapabilityDefinition(
        id="compositeEntities",
        description="Full entity-typed structures vs primitives",
        client_version_constraints=[],
        min_protocol_version=Version("3.2")
    ),
    CapabilityDefinition(
        id="flattenedCompositeEntities",
        description="Flattening of composite entities",
        client_version_constraints=[],  # We disable this for now unless requested by capability header
    ),
]

_CAPS_BY_ID: Dict[str, CapabilityDefinition] = {
    cap.id: cap for cap in CAPABILITY_MATRIX
}

enum_ids = {f.value for f in MaltegoCapability}
matrix_ids = set(_CAPS_BY_ID.keys())
if not matrix_ids <= enum_ids:
    raise RuntimeError(f"Matrix has unknown capabilities: {matrix_ids - enum_ids}")
if not enum_ids <= matrix_ids:
    raise RuntimeError(f"Enum has capabilities not in matrix: {enum_ids - matrix_ids}")


@dataclass(frozen=True)
class NegotiationContext:
    client_capabilities: MaltegoClientCapabilities
    protocol_version: Optional[str] = None
    client_id: Optional[str] = None
    client_version: Optional[Union[str, Version]] = None
    user_agent: Optional[MaltegoUserAgent] = None

    def get_protocol_version(self) -> Optional[Version]:
        if not self.protocol_version:
            return None
        try:
            proto_ver = Version(self.protocol_version)
        except InvalidVersion:
            return None
        return proto_ver

    def get_client_version(self) -> Optional[Version]:
        """
        Ensures client version is a semantic Version object.
        :return:
        """
        cv = self.client_version
        if cv is None:
            return None
        if isinstance(cv, Version):
            return cv
        try:
            return Version(cv)
        except InvalidVersion:
            return None

    def get_desktop_version(self) -> Optional[Version]:
        ua = self.user_agent
        if not ua or ua.major_version is None or ua.minor_version is None or ua.patch_version is None:
            return None
        try:
            return Version(f"{ua.major_version}.{ua.minor_version}.{ua.patch_version}")
        except InvalidVersion:
            return None

    def is_desktop(self) -> bool:
        return (
                self.user_agent is not None
                and self.user_agent.major_version is not None
                and self.user_agent.minor_version is not None
                and self.user_agent.patch_version is not None
        )

    def should_negotiate(self) -> bool:
        if self.client_capabilities.present:
            return True

        if self.client_id or self.client_version:
            return True

        if self.protocol_version:
            return True

        if self.is_desktop():
            return True

        return False


class CapabilityNegotiator:
    def __init__(self, ctx: NegotiationContext):
        self.ctx = ctx

    def header_is_authoritative(self) -> bool:
        return bool(self.ctx.client_capabilities.present)

    def get_client_type(self) -> ClientType:
        """
        Determine the type of client making the request.

        Returns:
            ClientType.WEB for Graph Browser
            ClientType.DESKTOP for Maltego Desktop
            ClientType.UNKNOWN for unidentified clients
        """
        if self.ctx.client_id == CLIENT_ID_GRAPH_BROWSER:
            return ClientType.WEB
        if self.ctx.is_desktop():
            return ClientType.DESKTOP
        return ClientType.UNKNOWN

    def _protocol_satisfies(self, min_proto: Version | None) -> bool:
        if min_proto is None or self.ctx.protocol_version is None:
            return True
        proto = self.ctx.get_protocol_version()
        return proto is not None and proto >= min_proto

    def _client_version_satisfies(self, definition: CapabilityDefinition) -> bool:
        cid = self.ctx.client_id
        cv = self.ctx.get_client_version()
        if cid and cv:
            for cvc in definition.client_version_constraints:
                if cid == cvc.client_id and cv >= cvc.min_version:
                    return True
        return False

    def _user_agent_satisfies(self, definition: CapabilityDefinition) -> bool:
        ua = self.ctx.user_agent
        if ua and ua.major_version is not None and ua.minor_version is not None and ua.patch_version is not None:
            ua_cid = "Maltego Desktop"
            ua_cv = Version(f"{ua.major_version}.{ua.minor_version}.{ua.patch_version}")
            for cvc in definition.client_version_constraints:
                if ua_cid == cvc.client_id and ua_cv >= cvc.min_version:
                    return True
        return False

    def _constraints_supported_by_client(self) -> set[str]:
        cv = self.ctx.get_client_version()
        return supported_constraint_types_for_desktop(cv)

    def _check_capability(self, cap: MaltegoCapability) -> bool:
        definition = _CAPS_BY_ID.get(cap.id)
        if not definition:
            return False

        if self.header_is_authoritative():
            return (
                    self.ctx.client_capabilities.has(cap)
                    and self._protocol_satisfies(definition.min_protocol_version)
            )

        if not self._protocol_satisfies(definition.min_protocol_version):
            return False

        if self._client_version_satisfies(definition):
            return True

        if self._user_agent_satisfies(definition):
            return True

        return False

    def _desktop_needs_constraint_filtering(self) -> bool:
        # Desktop doesn't use the headers
        if self.header_is_authoritative():
            return False

        # Only Desktop uses the UA flow
        if not self.ctx.is_desktop():
            return False

        # Desktop ≥ 5.0.0 advertises unknown-constraint safety via capability
        if self._check_capability(MaltegoCapability.INPUT_CONSTRAINTS_UNKNOWN_SAFE):
            return False

        return True

    def _constraints_supported_by_desktop(self) -> set[str]:
        cv = self.ctx.get_desktop_version()
        return supported_constraint_types_for_desktop(cv)

    def supports_coalesce(self) -> bool:
        """
        Check if client supports $coalesce() in entity display_property.

        Web clients (Graph Browser) always support coalesce as they run the latest version.
        Desktop clients require version >= COALESCE_MIN_DESKTOP.
        """
        client_type = self.get_client_type()

        if client_type == ClientType.WEB:
            return True

        if client_type == ClientType.DESKTOP:
            desktop_version = self.ctx.get_desktop_version()
            if desktop_version is None:
                return False  # Unknown version, assume no support
            return desktop_version >= COALESCE_MIN_DESKTOP

        return True  # Default: support (unknown client)

    def _input_constraints_allowed(self, constraint_root) -> bool:
        if not self._desktop_needs_constraint_filtering():
            return True
        required = extract_constraint_type_ids(constraint_root)
        supported = self._constraints_supported_by_desktop()
        return required.issubset(supported)

    def resolve_capabilities_set(self) -> ResolvedCapabilitiesSet:
        enabled = {
            f for f in MaltegoCapability
            if self._check_capability(f)
        }
        return ResolvedCapabilitiesSet(enabled)

    @functools.cached_property
    def resolved(self) -> ResolvedCapabilitiesSet:
        return self.resolve_capabilities_set()

    def allows_transform(self, tx: MaltegoTransform) -> bool:
        """
        Inspect a transform’s annotations
        and gate each required capability via _check_capability.
        """
        if not self.ctx.should_negotiate():
            return True

        if tx.input_constraint is not None:
            if not self._check_capability(MaltegoCapability.INPUT_CONSTRAINTS):
                return False
            if not self._input_constraints_allowed(tx.input_constraint):
                return False

        if tx.interactive:
            if not self._check_capability(MaltegoCapability.MULTI_CHOICE_CONTROLS):
                return False

        if tx.composite_entities:
            # allow if composite OR flattened is supported
            if not (self._check_capability(MaltegoCapability.COMPOSITE_ENTITIES) or
                    self._check_capability(MaltegoCapability.FLATTENED_COMPOSITE_ENTITIES)):
                return False

        return True

    def allows_machine(self, machine_cls: type[MaltegoMachine]) -> bool:
        if not self.ctx.should_negotiate():
            return True

        if machine_cls.input_constraints:
            if not self._check_capability(MaltegoCapability.INPUT_CONSTRAINTS):
                return False

        if machine_cls.interactive:
            if not self._check_capability(MaltegoCapability.MULTI_CHOICE_CONTROLS):
                return False

        if machine_cls.composite_entities:
            if not (self._check_capability(MaltegoCapability.COMPOSITE_ENTITIES) or
                    self._check_capability(MaltegoCapability.FLATTENED_COMPOSITE_ENTITIES)):
                return False

        return True
