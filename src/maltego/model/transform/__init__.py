# Copyright (c) Maltego Technologies GmbH.
import inspect
from typing import Literal, Tuple, get_type_hints, get_origin
from typing import (
    Any,
    Callable,
    NewType,
    Optional,
    Dict,
    List,
    TypeVar,
    Union
)
from queue import Queue

import logging

from maltego.model.entity import MaltegoEntity
from maltego.model.event import TransformEntityEvent, TransformEvent, TransformLinkEvent
from maltego.model.exception import MaltegoUnsupportedCapabilityError
from maltego.model.graph import MaltegoGraph
from maltego.model.context import MaltegoCapability, MaltegoContext, MaltegoUserAgent
from maltego.model.link import MaltegoLink
from maltego.model.observer import Observer
from maltego.model.input_constraints import InputConstraint
from maltego.model.transform.setting import TransformSetting
from maltego.model.transform_input_annotation import TransformInputAnnotation
from maltego.model.oauth import OAuthAuthenticator
from maltego.model.types import MaltegoSettingTypes
from maltego.protocol.v3.discovery.transform import (
    TransformDefinitionCapabilities, TransformDiscoveryIO,
    V3TransformDefinition,
)

log = logging.getLogger(__name__)

AUTO_CREATE_LINKS = True
VALID_FORMATS = """
MaltegoEntity[...]
List[MaltegoEntity[...]]
Union[MaltegoEntity[...], MaltegoEntity[...], ...]
List[Union[MaltegoEntity[...], MaltegoEntity[...], ...]]
"""

TransformInput = TypeVar("TransformInput", MaltegoEntity,
                         MaltegoGraph[Any], List[MaltegoEntity])
E = TypeVar("E", bound=MaltegoEntity)
G = TypeVar("G", bound=MaltegoGraph[Any])

LimitType = NewType('LimitType', int)
ContextType = NewType('ContextType', MaltegoContext)
TransformSettingsType = NewType('TransformSettingsType', Dict[str, str])

# (input)
TransformCallableInputOnly = Callable[[TransformInput], Any]

# (input, settings)
TransformCallableInputWithSettings = Callable[
    [TransformInput, TransformSettingsType],
    Any
]

# (input, context)
TransformCallableInputWithContext = Callable[
    [TransformInput, ContextType], Any
]

# (input, limit)
TransformCallableInputWithLimit = Callable[
    [TransformInput, LimitType], Any
]

# (input, settings, limit)
TransformCallableInputWithSettingsAndLimit = Callable[
    [TransformInput, TransformSettingsType, LimitType], Any
]

# (input, settings, context)
TransformCallableInputWithSettingsAndContext = Callable[
    [TransformInput, TransformSettingsType, ContextType], Any
]

# (input, context, limit)
TransformCallableInputWithContextAndLimit = Callable[
    [TransformInput, ContextType, LimitType], Any
]

# (input, settings, context, limit)
TransformCallableAllInputs = Callable[
    [TransformInput, TransformSettingsType, LimitType, ContextType],
    Any
]

TransformCallableAlias = Union[
    TransformCallableInputOnly[Any],
    TransformCallableInputWithSettings[Any],
    TransformCallableInputWithContext[Any],
    TransformCallableInputWithLimit[Any],
    TransformCallableInputWithSettingsAndLimit[Any],
    TransformCallableInputWithSettingsAndContext[Any],
    TransformCallableInputWithContextAndLimit[Any],
    TransformCallableAllInputs[Any],
]

ValidInputAnnotations = Union[MaltegoGraph[Any],
MaltegoEntity, List[MaltegoEntity]]

ParamDict = Dict[
    str,
    Union[
        ValidInputAnnotations,
        Dict[str, Optional[MaltegoSettingTypes]],
        int,
        MaltegoContext,
        None,
    ],
]


class MaltegoClient:
    """
    Represents a Maltego client with a name and version.
    """

    def __init__(self, name: str, version: Tuple[int, int, int]):
        """
        Initialize the Client.

        :param name: The name of the client.
        :param version: The version of the client as a tuple (major, minor, patch).
        """
        self.name = name
        self.version = version

    def __repr__(self) -> str:
        """
        String representation of the MaltegoClient object.

        :return: A string describing the client in the format 'ClientName: major.minor.patch'.
        """
        return f"{self.name}: {self.version[0]}.{self.version[1]}.{self.version[2]}"


class MaltegoClientFilter:
    """
    Filters clients based on given criteria, checking headers or user agent.
    """

    def __init__(
            self,
            min_clients: Optional[List[Union[Tuple[str, Tuple[int,
            int, int]], Dict[str, Any], MaltegoClient]]] = None,
            max_clients: Optional[List[Union[Tuple[str, Tuple[int,
            int, int]], Dict[str, Any], MaltegoClient]]] = None,
            client_identifier_header: str = "maltego-client-identifier",
            client_version_header: str = "maltego-client-version",
    ):
        """
        Creates a MaltegoClientFilter for filtering Maltego clients based on request headers and user agent.

        :param min_clients: A list of clients representing the minimum version criteria. Each client can be:
            - A tuple: (name, version), e.g., ("Maltego Desktop", (2, 5, 0))
            - A dict: {"name": "Maltego Desktop", "version": (2, 5, 0)}
            - A MaltegoClient object.
        :type min_clients: Optional[List[MaltegoClient]]
        :param max_clients: A list of clients representing the maximum version criteria. Each client can be:
            - A tuple: (name, version), e.g., ("Maltego Web Browser", (3, 0, 0))
            - A dict: {"name": "Maltego Web Browser", "version": (3, 0, 0)}
            - A MaltegoClient object.
        :type max_clients: Optional[List[MaltegoClient]]
        :param client_identifier_header: The header key used to identify the client.
            Default is "maltego-client-identifier".
        :type client_identifier_header: str
        :param client_version_header: The header key used to specify the client version.
            Default is "maltego-client-version".
        :type client_version_header: str

        :return: A ClientFilter object configured with the provided criteria.
        :rtype: MaltegoClientFilter
        """
        self.min_clients = [self.__to_client(c) for c in (min_clients or [])]
        self.max_clients = [self.__to_client(c) for c in (max_clients or [])]
        self.client_identifier_header = client_identifier_header
        self.client_version_header = client_version_header

    @staticmethod
    def validate_version(version: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """
        Validates the version tuple (major, minor, patch).
        """
        if (
                not isinstance(version, tuple)
                or len(version) != 3
                or not all(isinstance(v, int) for v in version)
        ):
            raise ValueError(
                f"Invalid version: {version}. Expected a tuple of three integers (major, minor, patch)."
            )
        return version[0], version[1], version[2]

    def __to_client_from_tuple(self, client: Tuple[str, Tuple[int, int, int]]) -> MaltegoClient:
        if len(client) != 2:
            raise ValueError(
                f"Invalid tuple format: {client}. Expected a tuple with 2 elements: (name, version)."
            )
        name, version = client
        if not isinstance(name, str):
            raise ValueError(
                f"Invalid name in tuple: {name}. Expected a string.")
        if not isinstance(version, tuple):
            raise ValueError(
                f"Invalid version in tuple: {version}. Expected a tuple.")
        return MaltegoClient(name=name, version=self.validate_version(version))

    def __to_client_from_dict(self, client: Dict[str, Any]) -> MaltegoClient:
        if "name" not in client or "version" not in client:
            raise ValueError(
                f"Invalid dictionary format: {client}. Expected keys 'name' and 'version'."
            )
        name = client["name"]
        version = client["version"]
        if not isinstance(name, str):
            raise ValueError(
                f"Invalid name in dictionary: {name}. Expected a string.")
        if not isinstance(version, tuple):
            raise ValueError(
                f"Invalid version in dictionary: {version}. Expected a tuple."
            )
        return MaltegoClient(name=name, version=self.validate_version(version))

    def __to_client(self,
                    client: Union[Tuple[str, Tuple[int, int, int]], Dict[str, Any], MaltegoClient]) -> MaltegoClient:
        """
        Returns a MaltegoClient, supports mapping from tuple and dict

        :param client: A MaltegoClient or tuple or dictionary representing a client.
        :return: A MaltegoClient object.
        :raises ValueError: If the input is not a valid tuple or dictionary with required keys.
        """

        if isinstance(client, MaltegoClient):
            return client

        if isinstance(client, tuple):
            return self.__to_client_from_tuple(client)

        if isinstance(client, dict):
            return self.__to_client_from_dict(client)

        raise ValueError(
            f"Invalid input type: {client}. Expected a tuple or a dictionary."
        )

    @staticmethod
    def parse_version(version_str: Any) -> Optional[Tuple[int, int, int]]:
        """
        Parse a version string (e.g., "3.2.1") into a tuple (major, minor, patch).

        :param version_str: The version to parse.
        :return: A tuple (major, minor, patch), padded by 0 or trimmed to ensure 3 components,
                 or None if parsing fails.
        """
        if not isinstance(version_str, str) or not version_str.strip():
            return None

        parts = version_str.split(".")
        try:
            version = [int(part) for part in parts if part.isdigit()]
            if not version:
                return None

            # Pad with 0s or trim to ensure exactly 3 parts
            while len(version) < 3:
                version.append(0)
            return tuple(version[:3])  # type: ignore
        except ValueError:
            return None

    def match(self, user_agent: MaltegoUserAgent, headers: dict) -> Tuple[bool, Optional[str]]:
        """
        Matches a request against the client filter criteria.

        :param user_agent: MaltegoUserAgent object.
        :param headers: Request headers.
        :return: (True, None) if the request passes; (False, reason) otherwise.
        """
        # Skip filtering if no user-agent and no headers
        if (
                user_agent.major_version is None
                or user_agent.minor_version is None
                or user_agent.patch_version is None
        ) and not headers.get(self.client_identifier_header):
            return True, None

        if not headers.get(self.client_identifier_header):
            # if no headers for client identifier / client version, try user agent
            client_name, client_version = self._extract_from_user_agent(
                user_agent)
        else:
            client_name, client_version = self._extract_from_headers(headers)

        if not client_name or not client_version:
            return False, "Unable to determine client name or version."

        if not self._check_min_criteria(client_name, client_version):
            min_versions = ", ".join(repr(client)
                                     for client in self.min_clients)
            return False, (
                f"Does not meet the minimum client version criteria. "
                f"Supported minimum versions are: {min_versions}."
            )

        if not self._check_max_criteria(client_name, client_version):
            max_versions = ", ".join(repr(client)
                                     for client in self.max_clients)
            return False, (
                f"Exceeds the maximum client version criteria. "
                f"Supported maximum versions are: {max_versions}."
            )

        return True, None

    def _extract_from_user_agent(self, user_agent: MaltegoUserAgent) -> Tuple[
        Optional[str], Optional[Tuple[int, int, int]]]:
        """
        Extracts client name and version from the user-agent.

        :param user_agent: Parsed UserAgent object.
        :return: A tuple of client name and version, or (None, None) if invalid.
        """
        if not user_agent.user_agent:
            return None, None
        client_name = user_agent.user_agent.split("/")[0].strip()
        client_version = (user_agent.major_version,
                          user_agent.minor_version, user_agent.patch_version)
        if any(v is None for v in client_version):
            return client_name, None
        return client_name, client_version

    def _extract_from_headers(self, headers: dict) -> Tuple[Optional[str], Optional[Tuple[int, int, int]]]:
        """
        Extracts client name and version from headers.

        :param headers: Request headers.
        :return: A tuple of client name and version, or (None, None) if invalid.
        """
        client_name = headers.get(self.client_identifier_header)
        client_version_str = headers.get(self.client_version_header)
        if not client_name or not client_version_str:
            return None, None
        client_version = self.parse_version(client_version_str)
        return client_name.strip(), client_version

    def _check_min_criteria(self, client_name: str, client_version: Tuple[int, int, int]) -> bool:
        """
        Checks if the client meets the minimum version criteria.

        :param client_name: Name of the client.
        :param client_version: Version of the client.
        :return: True if the client meets the minimum version criteria, False otherwise.
        """
        if not self.min_clients:
            return True
        for client in self.min_clients:
            if client_name == client.name and client_version >= client.version:
                return True
        return False

    def _check_max_criteria(self, client_name: str, client_version: Tuple[int, int, int]) -> bool:
        """
        Checks if the client meets the maximum version criteria.

        :param client_name: Name of the client.
        :param client_version: Version of the client.
        :return: True if the client meets the maximum version criteria, False otherwise.
        """
        if not self.max_clients:
            return True
        for client in self.max_clients:
            if client_name == client.name and client_version <= client.version:
                return True
        return False

    def inject_client(self, name: str, version: Tuple[int, int, int], into_min: bool = True):
        """
        Conditionally injects or updates a client in min_clients or max_clients.

        :param name: Name of the client to inject or update.
        :param version: Version of the client to inject or update.
        :param into_min: If True, inject into min_clients; otherwise, max_clients.
        """
        target_list = self.min_clients if into_min else self.max_clients

        for client in target_list:
            if client.name == name:
                # Compare versions and update
                if into_min:
                    client.version = tuple(max(a, b)
                                           for a, b in zip(client.version, version))
                else:
                    client.version = tuple(min(a, b)
                                           for a, b in zip(client.version, version))
                return

        # If client does not exist, add a new one
        target_list.append(MaltegoClient(name=name, version=version))


class TransformAnnotation:
    input: TransformInputAnnotation

    def __init__(self, transform_function: TransformCallableAlias):
        self.function_name = transform_function.__name__
        parameters = dict(inspect.signature(transform_function).parameters)
        signatures = get_type_hints(transform_function, include_extras=True)
        self.settings_param: Optional[str] = None
        self.slider_param: Optional[str] = None
        self.context_param: Optional[str] = None
        self.default_args: List[str] = []
        self.var_keyword: Optional[str] = None
        return_type_hint = signatures.pop("return", None)
        self.parse_output(return_type_hint)

        input_argument = None
        input_type_hint = None
        try:
            input_argument = next(iter(parameters))
            parameters.pop(input_argument)
            input_type_hint = signatures.pop(input_argument, None)
        except StopIteration:
            pass
        self.input_argument = input_argument
        self.parse_input(input_type_hint)
        if not self.is_valid():
            raise ValueError(
                f"Type annotation for {transform_function.__name__} "
                f"{self.input_argument} {input_type_hint} is not valid"
            )
        self.parse_remaining_parameters(parameters)

    def parse_parameters_by_name(self, parameters: Dict[str, Any]) -> None:
        if parameters.pop("settings", None):
            self.settings_param = "settings"
        if parameters.pop("limit", None):
            self.slider_param = "limit"
        if parameters.pop("slider", None):
            if self.slider_param is not None:
                raise ValueError(
                    f"Already found slider param: {self.slider_param}")
            self.slider_param = "slider"
        if parameters.pop("context", None):
            self.context_param = "context"

    def parse_parameter_annotation(self, param_name: str, param: inspect.Parameter) -> None:
        annotation = param.annotation
        if annotation == int:
            if self.slider_param is not None:
                raise ValueError(
                    f"Already found slider param: {self.slider_param} "
                    f"cannot use {param_name}"
                )
            self.slider_param = param_name
        elif annotation == MaltegoContext:
            if self.context_param is not None:
                raise ValueError(
                    f"Already found context param: {self.context_param} "
                    f"cannot use {param_name}"
                )
            self.context_param = param_name
        elif get_origin(annotation) is dict:
            if self.settings_param is not None:
                raise ValueError(
                    f"Already found settings param: {self.settings_param} "
                    f"cannot use {param_name}"
                )
            self.settings_param = param_name

    def parse_parameters_by_annotation(self, parameters: Dict[str, inspect.Parameter]) -> None:
        for param_name, param in parameters.items():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                self.var_keyword = param_name
            elif param.default != inspect.Parameter.empty:
                self.default_args.append(param_name)
            else:
                self.parse_parameter_annotation(param_name, param)

    def parse_remaining_parameters(self, parameters: Dict[str, Any]) -> None:
        self.parse_parameters_by_name(parameters)
        self.parse_parameters_by_annotation(parameters)

        if self.settings_param is not None:
            parameters.pop(self.settings_param, None)
        if self.slider_param is not None:
            parameters.pop(self.slider_param, None)
        if self.context_param is not None:
            parameters.pop(self.context_param, None)
        if self.var_keyword is not None:
            parameters.pop(self.var_keyword, None)
        for parameter_name in self.default_args:
            parameters.pop(parameter_name, None)
        if len(parameters) > 0:
            raise ValueError(
                "Could not extrapolate parameter by "
                f"name or by annotation: {list(parameters.keys())} "
                f"for transform function {self.function_name}"
            )

    def is_valid(self) -> bool:
        return self.input.is_valid() and self.output.is_valid()

    def uses_graph_payload(self) -> bool:
        return self.input.uses_graph_payload() or self.output.uses_graph_payload()

    def is_composed(self) -> bool:
        return self.input.is_composed() or self.output.is_composed()

    def parse_output(self, return_type_hint: Optional[TypeVar]) -> None:
        self.output = TransformInputAnnotation(return_type_hint)

    def parse_input(self, input_type_hint: Optional[TypeVar]) -> None:
        if self.input_argument is None:
            raise ValueError(
                f"Missing input annotation for transform {self.function_name}")
        self.input = TransformInputAnnotation(input_type_hint)


class MaltegoTransform:

    def __init__(
            self,
            impl: TransformCallableAlias,
            name: str,
            display_name: str,
            description: str,
            settings: List[TransformSetting],
            transform_ns: Optional[str],
            any_properties: Optional[List[str]] = None,
            all_properties: Optional[List[str]] = None,
            author: Optional[str] = None,
            owner: Optional[str] = None,
            disclaimer: Optional[str] = None,
            version: Optional[str] = None,
            location_relevance: Optional[str] = None,
            extra_annotations: Optional[Dict[str, Any]] = None,
            transform_set: Optional[str] = None,
            authenticator: Optional["OAuthAuthenticator"] = None,
            metadata: Optional[Dict[str, str]] = None,
            client_filter: Optional[MaltegoClientFilter] = None,
            input_constraint: Optional[InputConstraint] = None,
            interactive: Optional[bool] = None,
            composite_entities: Optional[bool] = None,
    ):
        if not isinstance(settings, List):
            raise ValueError("Transform settings need to be a List type")
        self.impl = impl
        self.name = name
        self.display_name = display_name
        self.annotation = TransformAnnotation(self.impl)
        self.description = description
        self.author = author
        self.location_relevance = location_relevance
        self.settings = {
            setting.name: setting for setting in settings
        }
        self.transform_ns = transform_ns
        self.owner = owner
        self.disclaimer = disclaimer
        self.version = version
        self.transform_set = transform_set
        self.authenticator = None if not authenticator else authenticator
        self.prefix: Optional[str] = None
        self._server_ns: Optional[str] = None
        # This can be used for middlewares and such (e.g. specify required entitlements, rate limits, etc)
        self.extra_annotations = extra_annotations or {}
        self.metadata = metadata
        self.properties_type: Optional[Literal['ANY', 'ALL']] = None
        if any_properties and all_properties:
            raise RuntimeError(
                "Cannot use all_properties and any_properties for the same transform")
        if all_properties:
            self.properties_type = "ALL"
        if any_properties:
            self.properties_type = "ANY"
        self.properties = all_properties or any_properties
        if any_properties or all_properties:
            log.warning(
                "Deprecation Warning: any_properties or all_properties will be deprecated in the following versions. please use input_constraint instead.")
        self.input_constraint = input_constraint
        self.client_filter = client_filter
        self.interactive = interactive or False
        self.composite_entities = composite_entities or False

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return self.__str__()

    async def __add_link_result_to_queue(
            self,
            source: MaltegoEntity,
            target: MaltegoEntity,
            queue: Queue[TransformEvent]
    ) -> None:
        link = MaltegoLink(
            source.maltego_entity_id,
            target.maltego_entity_id,
            label=target.link_label,
            is_reversed=target.reverse_link,
            style=target.link_style,
            thickness=target.link_thickness,
            color=target.link_color
        )
        queue.put(TransformLinkEvent(link))

    async def __add_entity_result_to_queue(
            self,
            result: MaltegoEntity,
            queue: Queue[TransformEvent],
            input_entities: Optional[List[MaltegoEntity]] = None,
            auto_create_links: bool = False
    ) -> None:
        if result is None:
            return None
        if isinstance(result, MaltegoEntity):
            # Create a temp graph to reuse the entity-typed property handling logic
            if (result.is_composite() or result.is_composite_instance) and not self.composite_entities:
                # if the entity is composite but the transform does not declare composition support,
                # raise an exception and fail the transform
                raise MaltegoUnsupportedCapabilityError(capability=MaltegoCapability.COMPOSITE_ENTITIES.id)
            temp_graph: MaltegoGraph = MaltegoGraph()
            temp_graph.add_entity(result)

            for ent in temp_graph.entities:
                event: TransformEvent = TransformEntityEvent(ent)
                queue.put(event)

            for link in temp_graph.links:
                event = TransformLinkEvent(link)
                queue.put(event)

            if auto_create_links:
                for input_entity in input_entities or []:
                    await self.__add_link_result_to_queue(input_entity, result, queue)

        else:
            raise ValueError(
                f"Transform returned object that is not a MaltegoEntity or MaltegoGraph. {type(result)}"
            )

    async def __handle_async_result(
            self,
            input_entities: List[MaltegoEntity],
            async_res: Union[MaltegoEntity, List[MaltegoEntity]],
            output_queue: Queue[TransformEvent],
            auto_create_links: bool
    ) -> None:
        if not isinstance(async_res, (list, tuple, set, MaltegoGraph)):
            await self.__add_entity_result_to_queue(async_res, output_queue, input_entities, auto_create_links)
        elif not isinstance(async_res, MaltegoGraph):
            for item in async_res:
                await self.__add_entity_result_to_queue(item, output_queue, input_entities, auto_create_links)

    async def __add_async_results(
            self,
            output_queue: Queue[TransformEvent],
            is_generator: bool,
            params: ParamDict
    ) -> None:
        assert inspect.isfunction(self.impl)
        input_entities = self.get_input_entities(params)
        auto_create_links = False if not input_entities else AUTO_CREATE_LINKS
        if is_generator:
            async for item in self.impl(**params):
                if not isinstance(item, MaltegoGraph):
                    await self.__add_entity_result_to_queue(item, output_queue, input_entities, auto_create_links)
        else:
            async_res = await self.impl(**params)
            if async_res is None:
                return
            await self.__handle_async_result(input_entities, async_res, output_queue, auto_create_links)

    async def __add_sync_results(self, output_queue: Queue[TransformEvent], params: ParamDict) -> None:
        assert inspect.isfunction(self.impl)
        input_entities = self.get_input_entities(params)
        auto_create_links = False if not input_entities else AUTO_CREATE_LINKS
        log.warning(
            f"Transforms should be asynchronous! Consider altering '{self.name}'."
        )
        if inspect.isgeneratorfunction(self.impl):
            result = list(self.impl(**params))
        else:
            result = self.impl(**params)

        if not isinstance(result, (list, tuple, set, MaltegoGraph)):
            await self.__add_entity_result_to_queue(result, output_queue, input_entities, auto_create_links)
        else:
            for item in self.impl(**params):
                if not isinstance(item, MaltegoGraph):
                    await self.__add_entity_result_to_queue(item, output_queue, input_entities, auto_create_links)

    def __remove_setting_prefix(
            self,
            setting_name: str
    ) -> str:
        is_global = False
        ns = ""
        if self.ns:
            ns = f"{self.ns}."

        # Remove global prefix if present. Only present if is_global=True. See discovery.py
        if setting_name.startswith("global#"):
            setting_name = MaltegoTransform.remove_string_prefix(
                setting_name, "global#"
            )
            is_global = True

        # Remove namespace. Should be present in all maltego-transform transform settings
        setting_name = MaltegoTransform.remove_string_prefix(setting_name, ns)

        # Need to do it twice for compatibility reasons 8573f0a7e8599a1867ed6b7c4f7589908717349b
        if setting_name.startswith("global.global#"):
            setting_name = MaltegoTransform.remove_string_prefix(
                setting_name, "global.global#"
            )
            is_global = True

        # Remove Transform name. Global settings do not have one
        if not is_global:
            setting_name = MaltegoTransform.remove_string_prefix(
                setting_name, f"{self.name}."
            )
        return setting_name

    def _register(self, transform_input: MaltegoGraph[Any], transform_graph_observer: Observer) -> None:
        for entity in transform_input.entities:
            entity.register(transform_graph_observer)
        for link in transform_input.links:
            link.register(transform_graph_observer)

    def _unregister(self, transform_input: MaltegoGraph[Any], transform_graph_observer: Observer) -> None:
        for entity in transform_input.entities:
            entity.unregister(transform_graph_observer)
        for link in transform_input.links:
            link.unregister(transform_graph_observer)
        transform_input.unregister(transform_graph_observer)

    async def __call__(
            self,
            transform_input: ValidInputAnnotations,
            output_queue: Queue[TransformEvent],
            transform_graph_observer: Observer,
            transform_settings: Optional[Dict[str,
            Optional[MaltegoSettingTypes]]] = None,
            context: Optional[MaltegoContext] = None,
            soft_limit: Optional[int] = None,
    ) -> None:
        assert context is None or isinstance(context, MaltegoContext)
        assert soft_limit is None or isinstance(soft_limit, int)

        if isinstance(transform_input, MaltegoGraph):
            self._register(transform_input, transform_graph_observer)
        if context is not None:
            context.graph.register(transform_graph_observer)

        params = self.prepare_tf_input_args(
            transform_input, transform_settings, context, soft_limit
        )
        is_coroutine = inspect.iscoroutinefunction(self.impl)
        is_asyncgen = inspect.isasyncgenfunction(self.impl)
        is_async = is_coroutine or is_asyncgen
        if not inspect.isfunction(self.impl):
            raise RuntimeError(
                f"Invalid transform function {self.impl}: Not a function")
        if is_async:
            await self.__add_async_results(output_queue, is_asyncgen, params)
        else:
            await self.__add_sync_results(output_queue, params)
        if isinstance(transform_input, MaltegoGraph):
            self._unregister(transform_input, transform_graph_observer)
        if context is not None:
            context.graph.unregister(transform_graph_observer)
        return None

    @staticmethod
    def remove_string_prefix(string: str, prefix: str) -> str:
        if not isinstance(string, str) or not isinstance(prefix, str):
            raise ValueError(
                "remove_string_prefix: Input string needs to be string type")
        if string.startswith(prefix):
            return string[len(prefix):]
        return string

    @property
    def ns(self) -> str:
        prefix = self.prefix if self.prefix else ''
        ns = self.transform_ns if self.transform_ns else self._server_ns
        if ns is None:
            raise ValueError(
                "No namespace was given! Set 'ns' param on Transforms or at server level."
            )

        return '.'.join([
            prefix,
            ns
        ]).strip('.')

    def set_server_ns(self, server_ns: Optional[str]) -> None:
        self._server_ns = server_ns

    def get_input_entities(self, params: ParamDict) -> List[MaltegoEntity]:
        input_entities: List[MaltegoEntity] = []
        if self.annotation.input_argument:
            input_param = params[self.annotation.input_argument]
            if isinstance(input_param, MaltegoGraph):
                return []
            if isinstance(input_param, MaltegoEntity):
                input_entities.append(input_param)
            elif isinstance(input_param, (list, tuple, set)):
                for elem in input_param:
                    assert isinstance(elem, MaltegoEntity)
                    input_entities.append(elem)
            else:
                raise RuntimeError(
                    f"Invalid transform input {type(input_param)}")
        return input_entities

    def prepare_settings(
            self,
            proto_settings_raw: Dict[str, str],
            transform: "MaltegoTransform",
    ) -> Dict[str, MaltegoSettingTypes]:
        transform_settings: Dict[str, MaltegoSettingTypes] = {
            setting_name: setting.default_value for setting_name, setting in self.settings.items()
        }
        if transform.authenticator is not None:
            if access_token_input_setting := proto_settings_raw.pop(transform.authenticator.access_token_input, None):
                transform_settings[transform.authenticator.access_token_input] = access_token_input_setting

        for proto_setting_name, proto_setting_value in proto_settings_raw.items():
            setting_name = self.__remove_setting_prefix(proto_setting_name)
            if setting_blueprint := self.settings.get(setting_name):
                transform_settings[setting_blueprint.name] = setting_blueprint.transform_setting_from_blueprint(
                    proto_setting_value
                )
            else:
                log.warning(f"Unrecognized Setting was sent: {setting_name}")
                transform_settings[setting_name] = proto_setting_value

        return transform_settings

    def prepare_tf_input_args(
            self,
            transform_input: ValidInputAnnotations,
            transform_settings: Optional[Dict[str, Optional[MaltegoSettingTypes]]],
            context: Optional[MaltegoContext],
            soft_limit: Optional[int]
    ) -> ParamDict:
        params: ParamDict = {}
        if self.annotation.input_argument:
            params[self.annotation.input_argument] = transform_input

        if self.annotation.settings_param:
            params[self.annotation.settings_param] = transform_settings
        if self.annotation.slider_param:
            params[self.annotation.slider_param] = soft_limit
        if self.annotation.context_param:
            params[self.annotation.context_param] = context
        return params

    def to_v3_transform_definition(self) -> V3TransformDefinition:
        tx_def_props = []
        if self.interactive:
            tx_def_props.append(TransformDefinitionCapabilities.INTERACTIVE)
        if bool(self.input_constraint):
            tx_def_props.append(TransformDefinitionCapabilities.INPUT_CONSTRAINTS)
        if self.composite_entities:
            tx_def_props.append(TransformDefinitionCapabilities.COMPOSITE_ENTITIES)
        return V3TransformDefinition(
            name=f"{self.ns}.{self.name}".strip("."),
            display_name=self.display_name,
            description=self.description,
            author=self.author,
            owner=self.owner,
            disclaimer=self.disclaimer,
            version=self.version,
            sets=[self.transform_set] if self.transform_set else [],
            max_entity_input_count=0,
            max_entity_output_count=0,
            transform_settings=[setting.to_v3_transform_setting_definition(
                self.ns, self.name
            ) for setting in self.settings.values()],
            input=self.to_v3_transform_input_definition(),
            output=self.to_v3_transform_output_definition(),
            metadata=self.metadata,
            authenticator=None if not self.authenticator else self.authenticator.name,
            transform_capabilities=tx_def_props if tx_def_props else None,
        )

    def to_v3_transform_input_definition(self) -> TransformDiscoveryIO:
        input_annotation = self.annotation.input
        if input_annotation.is_graph():
            graph_input_type_ids = input_annotation.get_entities_type_ids()
            return TransformDiscoveryIO(
                type='GRAPH',
                type_ids=graph_input_type_ids if graph_input_type_ids else [
                    'maltego.Unknown'],
                property_input_type=self.properties_type,
                properties=self.properties,
                input_constraint=self.input_constraint.to_v3_model(
                ) if self.input_constraint else None,
            )
        if input_annotation.is_entity() or input_annotation.is_union():
            return TransformDiscoveryIO(
                type='ENTITY',
                type_ids=input_annotation.get_entities_type_ids(),
                property_input_type=self.properties_type,
                properties=self.properties,
                input_constraint=self.input_constraint.to_v3_model(
                ) if self.input_constraint else None,
            )
        if input_annotation.is_iterable():
            return TransformDiscoveryIO(
                type='ENTITIES',
                type_ids=input_annotation.get_entities_type_ids(),
                property_input_type=self.properties_type,
                properties=self.properties,
                input_constraint=self.input_constraint.to_v3_model(
                ) if self.input_constraint else None,
            )
        raise ValueError("Unsupported transform definition")

    def to_v3_transform_output_definition(self) -> TransformDiscoveryIO:
        if self.annotation.output.is_graph():
            graph_output_type_ids = self.annotation.output.get_entities_type_ids()
            return TransformDiscoveryIO(
                type='GRAPH',
                type_ids=graph_output_type_ids if graph_output_type_ids else [
                    'maltego.Unknown'],
            )
        return TransformDiscoveryIO(
            type='ENTITIES',
            type_ids=self.annotation.output.get_entities_type_ids(),
        )


class TransformRunExecutionInput:

    def __init__(
            self,
            input_id: str,
            data: Any
    ):
        self.input_id = input_id
        self.data = data
