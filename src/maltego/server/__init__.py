# Copyright (c) Maltego Technologies GmbH.
import asyncio
from collections.abc import Iterable
from warnings import warn
from typing import (
    AsyncIterator,
    List,
    Dict,
    Callable,
    Optional,
    Type,
    TypeVar,
    Union,
    Any,
    Tuple,
)
import re
import logging
from urllib.parse import urlsplit, urlunsplit
from contextlib import asynccontextmanager
from importlib.metadata import entry_points
import uvicorn
from uvicorn.supervisors import ChangeReload
import fastapi
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi_restful.tasks import repeat_every
from fastapi_restful.api_settings import get_api_settings

# Imports used by this file
from maltego.config import get_logging_config
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.middlewares.oauth_middleware import OAuthMiddleware
from maltego.middlewares.user_concurrency_limit_middleware import (
    UserConcurrencyLimitMiddleware,
)
from maltego.middlewares.verify_metadata_middleware import VerifyMetadataMiddleware
from maltego.model import MaltegoPairedConfiguration
from maltego.model.exception import MaltegoHTTPClientError, MaltegoHTTPError
from maltego.model.icon import MaltegoIcon
from maltego.model.machine import MaltegoMachine
from maltego.model.transform import (
    MaltegoClientFilter,
    TransformCallableAlias,
    MaltegoTransform,
)
from maltego.model.oauth import OAuthAuthenticator
from maltego.model.input_constraints import InputConstraint
from maltego.model.transform_set import TransformSet
from maltego.runner import (
    TransformRunner,
    ThreadedTransformRunner,
    AsyncTransformRunner,
)
from maltego.server.tracing_middleware import TraceparentMiddleware
from maltego.server.etag_middleware import ETagMiddleware
from maltego.server.v3 import V3Server, log_entity_config_overrides
from maltego.tracing import setup_tracing
from maltego.server.util import (
    get_supported_protocol_version,
    is_forwarded_client_allowed,
    set_protocol_version_header,
)
from maltego.auth import (
    AuthMode,
    AuthProblemException,
    AuthTokenOrigin,
    AuthSettings,
    close_validator,
    get_auth_settings,
    optional_auth,
    set_auth_settings,
)

# Imports used for explicit export
from maltego.server.version import __version__
from maltego.model.server import (
    EntityConfigOverride,
    EntityConfigOverrides,
    MaltegoHubItem,
    MaltegoServerSettings,
    ServerHTTPSettings,
    TransformRunnerType,
)
from maltego.model.context import MaltegoContext
from maltego.util import IntegrationClient
from maltego.model.types import daterange, Url, Color
from maltego.model.entity import (
    MaltegoEntity,
    MaltegoEntityConfig,
    MaltegoEntityMeta,
    MaltegoEntityAction,
    MaltegoActionType,
    MaltegoEntityRegexConverter,
)
from maltego.model.entity.property import MaltegoEntityProperty
from maltego.model.entity.constants import OverlayTypes, OverlayPositions, Overlay
from maltego.protocol.v3.execution.entity import Bookmark
from maltego.model.transform.setting import TransformSetting
from maltego.model.graph import MaltegoGraph
from maltego.model.link import MaltegoLink
from maltego.model.exception import MaltegoException
from maltego.model.prompt import PromptItem, InputPromptItem, InputTypes

__all__ = [
    "EntityConfigOverride",
    "EntityConfigOverrides",
    "MaltegoTransformServer",
    "MaltegoServerSettings",
    "ServerHTTPSettings",
    "TransformRunnerType",
    "MaltegoContext",
    "IntegrationClient",
    "daterange",
    "Url",
    "Color",
    "MaltegoEntity",
    "MaltegoEntityProperty",
    "OverlayTypes",
    "OverlayPositions",
    "Overlay",
    "Bookmark",
    "MaltegoEntityConfig",
    "TransformSetting",
    "MaltegoGraph",
    "MaltegoLink",
    "MaltegoException",
    "register_entity",
    "register_transform",
    "register_machine",
    "register_transform_set",
    "register_icon",
    "run_server",
    "__version__",
    "MaltegoHubItem",
    "PromptItem",
    "InputPromptItem",
    "InputTypes",
    "MaltegoMachine",
    "TransformSet",
    "MaltegoIcon",
    "MaltegoEntityAction",
    "MaltegoActionType",
    "MaltegoEntityRegexConverter",
    "AuthSettings",
    "AuthMode",
    "AuthTokenOrigin",
    "setup_tracing",
]


log = logging.getLogger(__name__)

SCHEDULED_CLEANUP_SECONDS = 60
MachineT = TypeVar("MachineT", bound=MaltegoMachine)
IconT = TypeVar("IconT", bound=MaltegoIcon)
MaltegoEntityT = TypeVar("MaltegoEntityT", bound=MaltegoEntity)
TransformSetT = TypeVar("TransformSetT", bound=TransformSet)
AnyTransformMiddleware = TypeVar("AnyTransformMiddleware", bound=TransformMiddleware)
ProtocolExtension = Callable[
    ["MaltegoTransformServer", Dict[str, MaltegoTransform]], None
]
PROTOCOL_EXTENSION_ENTRY_POINT_GROUP = "maltego_transforms.protocol_extensions"

ALLOWED_TX_ID = re.compile(r"^[a-zA-Z0-9\-\_\.]+[a-zA-Z0-9]+$")


def assert_metadata(metadata: Optional[Dict[str, str]]) -> None:
    for key, value in (metadata or {}).items():
        if not isinstance(key, str):
            raise TypeError(f"cannot parse metadata key of non-string type {type(key)}")
        if not isinstance(value, str):
            raise TypeError(
                f"cannot parse metadata value of non-string type {type(value)}"
            )


def assert_client_version(version: Tuple[int, int, int]) -> None:
    if (
        not isinstance(version[0], int)
        or not isinstance(version[1], int)
        or not isinstance(version[2], int)
    ):
        raise TypeError(
            f"Invalid client version {version}. Please make sure its a 3-Tuple of integers"
        )


class MaltegoTransformServer:
    def __init__(
        self,
        settings: MaltegoServerSettings,
    ) -> None:
        self._registration_queue: List[MaltegoTransform] = []
        self.paired_config = MaltegoPairedConfiguration()
        self._settings: MaltegoServerSettings = settings
        self.runner: TransformRunner
        if not isinstance(settings.transform_runner, TransformRunnerType):
            raise ValueError(
                "Transform Runner needs to be a enum of type TransformRunnerType"
            )
        if settings.transform_runner == TransformRunnerType.THREADED:
            self.runner = ThreadedTransformRunner(
                middlewares=[],
                transform_execution_timeout=self._settings.transform_execution_timeout,
                middleware_execution_timeout=self._settings.middleware_execution_timeout,
            )
            self.runner.set_worker(self._settings.num_worker)
        elif settings.transform_runner == TransformRunnerType.ASYNC:
            self.runner = AsyncTransformRunner(
                middlewares=[],
                transform_execution_timeout=self._settings.transform_execution_timeout,
                middleware_execution_timeout=self._settings.middleware_execution_timeout,
            )
        else:
            raise RuntimeError(
                f"Unsupported Transform Runner {settings.transform_runner} configured"
            )

        self.scheduled_cleanup_seconds = (
            self._settings.scheduled_cleanup_seconds
            if self._settings.scheduled_cleanup_seconds
            else SCHEDULED_CLEANUP_SECONDS
        )
        self.runner.retention_time = self.scheduled_cleanup_seconds
        self.__setup = False
        self._hub_item = MaltegoHubItem()
        self.add_middleware(VerifyMetadataMiddleware())
        self.v2server: Optional[Any] = None
        self.v3server: Optional[V3Server] = None
        self._protocol_routers: List[fastapi.routing.APIRouter] = []
        self._protocol_extensions: List[ProtocolExtension] = []
        self._installed_protocol_extensions_loaded = False
        get_api_settings.cache_clear()
        fastapi_settings = get_api_settings()

        @asynccontextmanager
        async def lifespan(
            app: fastapi.FastAPI,
        ) -> AsyncIterator[None]:  # pylint: disable=unused-argument
            @repeat_every(
                seconds=self.scheduled_cleanup_seconds, logger=log, wait_first=True
            )
            async def remove_expired_executions_task() -> None:
                if self.runner:
                    self.runner.cleanup()

            await remove_expired_executions_task()
            yield
            # Shutdown
            self.runner.shutdown()
            await close_validator()  # Close auth HTTP client

        fastapi_kwargs = dict(fastapi_settings.fastapi_kwargs)
        fastapi_kwargs["docs_url"] = None
        fastapi_kwargs["redoc_url"] = None
        self.app = fastapi.FastAPI(**fastapi_kwargs, lifespan=lifespan)

        @self.app.exception_handler(MaltegoHTTPClientError)
        async def exception_handler(
            request: fastapi.Request, exc: MaltegoHTTPError
        ) -> fastapi.Response:
            log.error(f"Exception in request {request}: {exc.detail}")
            return fastapi.Response(
                str(exc.detail), status_code=exc.classic_status_code, media_type="text/plain"
            )

        @self.app.exception_handler(AuthProblemException)
        async def auth_problem_exception_handler(
            request: fastapi.Request, exc: AuthProblemException
        ) -> fastapi.Response:
            return fastapi.responses.JSONResponse(
                status_code=exc.status_code,
                content=exc.problem.model_dump(mode="json", exclude_none=True),
                headers=exc.headers,
                media_type="application/problem+json",
            )

        @self.app.get("/health")
        async def health() -> Dict[str, str]:
            return {"status": "ok"}

    def _finalize_transform(self, transform: MaltegoTransform) -> str:
        transform.set_server_ns(self._settings.ns)
        if self._settings.transform_prefix and self._settings.transform_name_prefix:
            transform.prefix = self._settings.transform_name_prefix
        if (
            self._settings.transform_prefix
            and self._settings.transform_display_name_prefix
            and transform.transform_set
        ):
            transform.transform_set = f"{self._settings.transform_display_name_prefix}{transform.transform_set}"

        transform.author = (
            transform.author or self._settings.author
            if self._settings.author is not None
            else transform.author
        )
        if transform.author is None:
            raise ValueError(
                f"No author found for Transform '{transform.name}' - "
                "specify one, or add it to the server's default"
                " settings."
            )

        transform.owner = transform.owner or self._settings.owner
        transform.version = transform.version or self._settings.version

        transform_id = f"{transform.ns}.{transform.name}".strip(".")
        self.add_config_to_set(transform_id, transform)
        return transform_id

    def _finalize_transform_registrations(self) -> Dict[str, MaltegoTransform]:
        # applies default settings and actual registration
        # (settings may have been added/changed since initial registration)
        finalized_transforms: Dict[str, MaltegoTransform] = {}
        for transform in self._registration_queue:
            transform_id = self._finalize_transform(transform)
            if transform_id in finalized_transforms:
                raise ValueError(
                    f"A Transform with the name {transform_id} was already registered, "
                    "Transform ids must be unique."
                )
            finalized_transforms[transform_id] = transform

        return finalized_transforms

    def __get_config(
        self,
        ssl: bool,
        ssl_cert_file: Optional[str],
        ssl_key_file: Optional[str],
        host: str,
        port: int,
        log_config: Optional[Union[Dict[str, Any], str]] = None,
        reload: bool = False,
    ) -> uvicorn.Config:
        uvicorn_logger = logging.getLogger("uvicorn.error")
        uvicorn_logger.name = "uvicorn"
        app: Optional[Union[fastapi.FastAPI, str]] = None
        if reload:
            app = "maltego.server:_server.app"
        else:
            app = self.app

        if ssl:
            if self._settings.ssl_cert_file is not None:
                warn(
                    "ssl_cert_file in settings is deprecated, pass ssl_cert_file to run_server instead",
                    DeprecationWarning,
                    stacklevel=3,
                )
                raise ValueError(
                    "ssl_cert_file must be passed to run_server, not set in settings"
                )
            if not isinstance(ssl_cert_file, str) or not ssl_cert_file:
                raise ValueError(
                    "If SSL is enabled the ssl_key_file parameter needs to be a valid location"
                )

            if self._settings.ssl_key_file is not None:
                warn(
                    "ssl_key_file in settings is deprecated, pass ssl_key_file to run_server instead",
                    DeprecationWarning,
                    stacklevel=3,
                )
                raise ValueError(
                    "ssl_key_file must be passed to run_server, not set in settings"
                )
            if not isinstance(ssl_key_file, str) or not ssl_key_file:
                raise ValueError(
                    "If SSL is enabled the ssl_key_file parameter needs to be a valid location"
                )
            return uvicorn.Config(
                app=app,
                loop="asyncio",
                host=host,
                port=port,
                ssl_certfile=ssl_cert_file,
                ssl_keyfile=ssl_key_file,
                log_config=log_config,
                reload=reload,
                proxy_headers=False,
                forwarded_allow_ips=self._settings.http_settings.forwarded_allow_ips,
            )
        return uvicorn.Config(
            app=app,
            loop="asyncio",
            host=host,
            port=port,
            log_config=log_config,
            reload=reload,
            proxy_headers=False,
            forwarded_allow_ips=self._settings.http_settings.forwarded_allow_ips,
        )

    @staticmethod
    def get_transform_description(description: Optional[str] = None) -> str:
        return (description or "").strip()

    def add_middleware(self, middleware: TransformMiddleware) -> None:
        if not isinstance(middleware, TransformMiddleware):
            raise ValueError(
                f"Registered middleware {middleware} does not inherit TransformMiddleware! {type(middleware)}"
            )
        self.runner.middlewares.append(middleware)

    def add_protocol_extension(self, extension: ProtocolExtension) -> None:
        if extension not in self._protocol_extensions:
            self._protocol_extensions.append(extension)

    def add_protocol_router(self, router: fastapi.routing.APIRouter) -> None:
        if router not in self._protocol_routers:
            self._protocol_routers.append(router)
            self.app.include_router(router)

    def _load_installed_protocol_extensions(self) -> None:
        if self._installed_protocol_extensions_loaded:
            return
        installed_entry_points = entry_points(
            group=PROTOCOL_EXTENSION_ENTRY_POINT_GROUP
        )
        allowlist = getattr(self._settings, 'allowed_protocol_extensions', None)
        for entry_point in installed_entry_points:
            # Honor optional allowlist; log every load attempt.
            if allowlist is not None and entry_point.name not in allowlist:
                log.warning(
                    "Skipping protocol extension %r — not in allowed_protocol_extensions allowlist.",
                    entry_point.name,
                )
                continue
            try:
                extension = entry_point.load()
            except Exception as exc:
                raise RuntimeError(
                    "Failed to load Maltego transform protocol extension "
                    f"{entry_point.name!r}"
                ) from exc
            log.info("Loaded protocol extension: %r", entry_point.name)
            self.add_protocol_extension(extension)
        self._installed_protocol_extensions_loaded = True

    def set_settings(self, settings: MaltegoServerSettings) -> None:
        if settings.ns is None:
            raise ValueError(
                "Transform Server namespace cannot be None. Please specify a namespace"
            )
        self._settings = settings
        self.runner.transform_execution_timeout = (
            self._settings.transform_execution_timeout
        )
        self.runner.middleware_execution_timeout = (
            self._settings.middleware_execution_timeout
        )
        if isinstance(self.runner, ThreadedTransformRunner):
            self.runner.set_worker(self._settings.num_worker)

    def set_hub_item(self, hub_item: Optional[MaltegoHubItem]) -> None:
        if hub_item:
            self._hub_item = hub_item

    def _setup_cors(self) -> None:
        if any(m.cls is CORSMiddleware for m in self.app.user_middleware):
            return
        http = self._settings.http_settings
        if not http.cors_allowed_origins and not http.cors_allowed_origin_regex:
            return

        # Reject wildcard origins combined with credentials — browsers block
        # this combination anyway; fail-closed avoids misconfigurations that silently
        # break cross-origin requests or weaken the Same-Origin policy.
        # Safe config: use an explicit origin list (e.g. ["https://app.example.com"])
        # or set allow_credentials=False when a wildcard is required.
        origins = http.cors_allowed_origins or []
        if "*" in origins:
            raise ValueError(
                "CORS misconfiguration: allow_origins=['*'] cannot be combined with "
                "allow_credentials=True. Use an explicit origin list or disable credentials."
            )

        # A catch-all regex is equivalent to a wildcard origin: with
        # allow_credentials=True it reflects any origin. Perfectly detecting a
        # "matches everything" regex is undecidable, so reject the common
        # catch-all forms explicitly.
        regex = (http.cors_allowed_origin_regex or "").strip()
        if regex in {".*", ".+", "^.*$", "^.+$", "(.*)", "(.+)"}:
            raise ValueError(
                "CORS misconfiguration: a catch-all cors_allowed_origin_regex cannot be "
                "combined with allow_credentials=True. Anchor the regex to trusted domains "
                "or disable credentials."
            )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_origin_regex=http.cors_allowed_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_response_compression(self) -> None:
        http = self._settings.http_settings
        if not http.http_response_compression_enabled:
            return
        if any(m.cls is GZipMiddleware for m in self.app.user_middleware):
            return
        self.app.add_middleware(
            GZipMiddleware,
            minimum_size=http.http_response_compression_minimum_size,
        )

    def _is_route_registered(self, path: str, method: str) -> bool:
        for route in self.app.routes:
            if getattr(route, "path", None) != path:
                continue
            methods = getattr(route, "methods", None) or set()
            if method in methods:
                return True
        return False

    def _configure_openapi(self) -> None:
        def custom_openapi() -> Dict[str, Any]:
            if self.app.openapi_schema:
                return self.app.openapi_schema
            self.app.openapi_schema = get_openapi(
                title=f"{self._settings.server_name} API",
                version=self._settings.version,
                description="OpenAPI specification for the Maltego Transform Server.",
                routes=self.app.routes,
            )
            schema = self.app.openapi_schema
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT Bearer token. Required when server authentication is enabled.",
            }
            schema["security"] = [{"BearerAuth": []}]
            return self.app.openapi_schema

        self.app.openapi = custom_openapi

        if not self._settings.swagger_enabled:
            # Strip FastAPI's built-in /openapi.json route so the endpoint is unreachable.
            self.app.router.routes = [
                r for r in self.app.router.routes
                if getattr(r, "path", None) != "/openapi.json"
            ]
            return

        # Strip FastAPI's default /openapi.json route (methods=None, no auth) before registering
        # our auth-protected version. Without this, the default route matches first in Starlette's
        # route resolution and the auth dependency is never invoked.
        self.app.router.routes = [
            r for r in self.app.router.routes
            if getattr(r, "path", None) != "/openapi.json"
        ]

        @self.app.get("/openapi.json", include_in_schema=False, dependencies=[fastapi.Depends(optional_auth)])
        async def openapi_spec() -> Dict[str, Any]:
            return self.app.openapi()

    def _setup_swagger(self) -> None:
        if self._is_route_registered("/swagger", "GET"):
            return

        @self.app.get("/swagger", include_in_schema=False, dependencies=[fastapi.Depends(optional_auth)])
        async def swagger_ui() -> fastapi.responses.HTMLResponse:
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title=f"{self._settings.server_name} API Swagger UI",
            )

    @staticmethod
    def _display_host(host: str) -> str:
        return host if host != "0.0.0.0" else "127.0.0.1"

    @staticmethod
    def _is_protocol_compatibility_route(
        path: str,
        compatibility_prefixes: Iterable[str],
    ) -> bool:
        normalized_path = path.strip("/")
        for prefix in compatibility_prefixes:
            normalized_prefix = prefix.strip("/")
            if not normalized_prefix:
                continue
            if (
                normalized_path == normalized_prefix
                or normalized_path.startswith(f"{normalized_prefix}/")
            ):
                return True
        return False

    def get_registered_route_urls(
        self,
        scheme: str,
        host: str,
        port: int,
    ) -> List[str]:
        def iter_registered_routes(routes: Iterable[Any]) -> Iterable[Any]:
            for route in routes:
                yield route
                child_routes = getattr(route, "routes", None)
                if child_routes:
                    yield from iter_registered_routes(child_routes)
                    continue
                original_router = getattr(route, "original_router", None)
                if original_router is not None:
                    yield from iter_registered_routes(original_router.routes)

        base_url = f"{scheme}://{self._display_host(host)}:{port}"
        route_urls: List[str] = []
        seen: set[str] = set()
        compatibility_prefixes = (
            self.v3server._legacy_prefixes  # pylint: disable=protected-access
            if self.v3server is not None
            else []
        )
        for route in iter_registered_routes(self.app.routes):
            path = getattr(route, "path", None)
            if not path:
                continue
            if self._is_protocol_compatibility_route(path, compatibility_prefixes):
                continue
            methods = getattr(route, "methods", None) or set()
            method_names = sorted(method for method in methods if method != "HEAD")
            method_prefix = ",".join(method_names) if method_names else "ANY"
            route_url = f"{method_prefix} {base_url}{path}"
            if route_url in seen:
                continue
            seen.add(route_url)
            route_urls.append(route_url)
        return route_urls

    def setup(self, settings: MaltegoServerSettings) -> None:
        self.set_settings(settings)
        # Expose the trusted-proxy list on app state so request-scoped auth
        # dependencies (client-IP / rate-limit keying) honour the configured
        # forwarded_allow_ips instead of falling back to the loopback default.
        http_settings = self._settings.http_settings
        self.app.state.forwarded_allow_ips = (
            http_settings.forwarded_allow_ips if http_settings else "127.0.0.1"
        )
        self._setup_response_compression()
        self._setup_cors()
        self._load_installed_protocol_extensions()
        max_runs = self._settings.max_concurrent_transforms_per_user
        if max_runs is not None:
            log.debug(
                f"Adding concurrency limiting middleware for {max_runs} concurrent Transform runs per user."
            )
            self.runner.middlewares.insert(0, UserConcurrencyLimitMiddleware(max_runs))

        for auth in self.paired_config.authenticators.values():
            auth.allow_regenerating_keys = self._settings.allow_regenerating_oauth_keys
            auth.generate_keys_if_needed()

        transforms = self._finalize_transform_registrations()

        self.v3server = V3Server(
            self.paired_config, self._settings, self.runner, hub_item=self._hub_item
        )
        self.v3server.set_transforms(transforms)
        self.app.include_router(self.v3server.prepare_app())
        for extension in self._protocol_extensions:
            extension(self, transforms)
        if self.v2server is None:
            self.app.include_router(self._prepare_seed_bridge_app())
        self._configure_openapi()
        if self._settings.swagger_enabled:
            self._setup_swagger()
        self.__setup = True

    @staticmethod
    def _first_header_value(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.split(",", 1)[0].strip()
        return value or None

    @staticmethod
    def _is_forwarded_client_allowed(
        client_host: Optional[str], forwarded_allow_ips: str
    ) -> bool:
        # Delegates to shared utility in server/util.py so auth/dependency.py
        # can reuse the same logic without a circular import.
        return is_forwarded_client_allowed(client_host, forwarded_allow_ips)

    def _get_trusted_forwarded_proto(
        self,
        request: fastapi.Request,
        forwarded_allow_ips: str,
    ) -> Optional[str]:
        forwarded_proto = self._first_header_value(
            request.headers.get("x-forwarded-proto")
        )
        if forwarded_proto not in ("http", "https"):
            return None
        if not self._settings.trust_forwarded_headers:
            return None

        client_host = request.client.host if request.client else None
        if not self._is_forwarded_client_allowed(client_host, forwarded_allow_ips):
            return None
        return forwarded_proto

    def _promote_explicit_host_url_scheme(
        self,
        host_url: str,
        request: fastapi.Request,
        forwarded_allow_ips: str,
    ) -> str:
        parsed_url = urlsplit(host_url)
        if parsed_url.scheme != "http":
            return host_url

        trusted_proto = self._get_trusted_forwarded_proto(request, forwarded_allow_ips)
        configured_proto = self._settings.http_settings.protocol
        if trusted_proto != "https" and configured_proto != "https":
            return host_url

        promoted = urlunsplit(parsed_url._replace(scheme="https"))
        log.debug(
            "Seed URL promoted explicit host URL scheme from http to https: %s",
            promoted,
        )
        return promoted

    def _resolve_seed_bridge_host_url(self, request: fastapi.Request) -> Optional[str]:
        http_settings = self._settings.http_settings
        if http_settings and http_settings.root_url:
            resolved = http_settings.root_url.rstrip("/")
            resolved = self._promote_explicit_host_url_scheme(
                resolved,
                request,
                http_settings.forwarded_allow_ips,
            )
            log.debug("Seed URL using explicit http_settings.root_url=%s", resolved)
            return resolved

        if self._settings.full_host_url:
            resolved = self._settings.full_host_url.rstrip("/")
            resolved = self._promote_explicit_host_url_scheme(
                resolved,
                request,
                http_settings.forwarded_allow_ips,
            )
            log.debug("Seed URL using explicit full_host_url=%s", resolved)
            return resolved

        if http_settings and http_settings.domain:
            protocol = http_settings.protocol or "https"
            port = http_settings.http_port or 3000
            if (protocol == "https" and port == 443) or (
                protocol == "http" and port == 80
            ):
                resolved = f"{protocol}://{http_settings.domain}"
            else:
                resolved = f"{protocol}://{http_settings.domain}:{port}"
            log.debug("Seed URL using http_settings domain=%s", resolved)
            return resolved

        forwarded_proto = self._first_header_value(
            request.headers.get("x-forwarded-proto")
        )
        forwarded_host = self._first_header_value(
            request.headers.get("x-forwarded-host")
        )
        host_header = self._first_header_value(request.headers.get("host"))
        base_url = request.base_url
        client_host = request.client.host if request.client else None
        forwarded_allow_ips = http_settings.forwarded_allow_ips

        log.debug(
            "Seed URL request headers: base_url=%s host=%s x-forwarded-host=%s x-forwarded-proto=%s "
            "client_host=%s forwarded_allow_ips=%s trust_forwarded_headers=%s full_host_url=%s",
            str(base_url).rstrip("/") if base_url else None,
            host_header,
            forwarded_host,
            forwarded_proto,
            client_host,
            forwarded_allow_ips,
            self._settings.trust_forwarded_headers,
            self._settings.full_host_url,
        )

        if not self._settings.trust_forwarded_headers:
            resolved = str(base_url).rstrip("/") if base_url else None
            log.debug("Seed URL using base_url=%s", resolved)
            return resolved

        if not self._is_forwarded_client_allowed(client_host, forwarded_allow_ips):
            resolved = str(base_url).rstrip("/") if base_url else None
            log.debug(
                "Seed URL ignored forwarded headers from untrusted client_host=%s allowed=%s",
                client_host,
                forwarded_allow_ips,
            )
            return resolved

        scheme = forwarded_proto or base_url.scheme
        if scheme not in ("http", "https"):
            scheme = base_url.scheme

        host = forwarded_host or host_header or base_url.netloc
        if not host:
            resolved = str(base_url).rstrip("/") if base_url else None
            log.debug("Seed URL fell back to base_url=%s because host was missing", resolved)
            return resolved

        base_path = base_url.path.rstrip("/")
        resolved = f"{scheme}://{host}{base_path}".rstrip("/")
        log.debug(
            "Seed URL resolved from headers: scheme=%s host=%s base_path=%s resolved=%s",
            scheme,
            host,
            base_path or "/",
            resolved,
        )
        return resolved

    def _get_seed_bridge_protocol_base_url(self, request: fastapi.Request) -> str:
        host_url = self._resolve_seed_bridge_host_url(request)
        if not host_url:
            raise RuntimeError("Couldn't generate protocol base URL")
        prefix = self._settings.api_prefix.strip("/") if self._settings.api_prefix else ""
        if not prefix:
            return host_url.rstrip("/")
        return f"{host_url.rstrip('/')}/{prefix}"

    def _get_seed_bridge_server_name(self) -> str:
        server_name_prefix = ""
        if (
            self._settings.transform_prefix
            and isinstance(self._settings.transform_app_name_prefix, str)
        ):
            server_name_prefix = self._settings.transform_app_name_prefix
        return f"{server_name_prefix}{self._settings.server_name}"

    def _get_seed_bridge_seed_url(self) -> str:
        prefix = self._settings.api_prefix.strip("/") if self._settings.api_prefix else ""
        return "/".join(elem for elem in [prefix, "seed"] if elem)

    async def _handle_seed_bridge(
        self,
        request: fastapi.Request,
        response: fastapi.Response,
        maltego_protocol_version: str = fastapi.Header(default=None),
    ) -> Any:
        protocol_base_url = self._get_seed_bridge_protocol_base_url(request)
        set_protocol_version_header(response, maltego_protocol_version)
        return {
            "TransformApplications": [
                {
                    "name": self._get_seed_bridge_server_name(),
                    "requireAPIKey": self._settings.require_api_key,
                    "URL": protocol_base_url,
                    "V3URL": protocol_base_url,
                    "version": self._settings.version,
                    "disclaimer": self._settings.disclaimer,
                }
            ]
        }

    async def _handle_seed_bridge_options(
        self,
        response: fastapi.Response,
        maltego_protocol_version: str = fastapi.Header(default=None),
    ) -> None:
        response.headers["maltego-protocol-version"] = get_supported_protocol_version(
            maltego_protocol_version,
            self._settings,
        )
        response.headers["v3-page-size"] = str(self._settings.v3_page_size_max)

    def _prepare_seed_bridge_app(self) -> fastapi.APIRouter:
        router = fastapi.APIRouter(dependencies=[fastapi.Depends(optional_auth)])
        prefix = self._settings.api_prefix.strip("/") if self._settings.api_prefix else ""
        seed_url = "/".join(
            elem for elem in [prefix, "seed"] if elem
        )
        router.add_api_route(
            f"/{seed_url}",
            self._handle_seed_bridge,
            methods=["GET"],
            response_model=None,
            response_model_exclude_none=True,
        )
        router.add_api_route(
            f"/{seed_url}",
            self._handle_seed_bridge_options,
            methods=["OPTIONS"],
            response_model_exclude_none=True,
        )
        return router

    def register_entity(
        self, entity_type: Type[MaltegoEntityT]
    ) -> Type[MaltegoEntityT]:
        if self.paired_config is None:
            raise ValueError(
                "This Transform server is not set up to dynamically generate a paired configuration, "
                f"refusing to register entity {entity_type}."
            )
        entity_config = entity_type.Config
        if not isinstance(entity_config, MaltegoEntityConfig):
            raise ValueError(
                "To register an Entity type for a paired configuration, please add an attribute 'Config'"
                " of type MaltegoEntityConfiguration inside your Entity class definition."
            )

        # Overwrite TYPE_NAME for all entities that share the same TYPE_NAME as one of their parents
        # For convenience reasons the TYPE_NAME is auto generated based on the class name
        for base in entity_type.__bases__:
            if hasattr(base, "TYPE_NAME") and base.TYPE_NAME == entity_type.TYPE_NAME:
                entity_type.TYPE_NAME = f"maltego.{entity_type.__name__}"
                break

        MaltegoEntityMeta.try_add_registry(entity_type.TYPE_NAME, entity_type)

        category = entity_config.category
        if entity_config.overlays is not None:
            for overlay in entity_config.overlays:
                if isinstance(overlay.overlay_type, OverlayTypes):
                    overlay.overlay_type = (
                        overlay.overlay_type.value
                    )  # make sure we have a str here
                if isinstance(overlay.position, OverlayPositions):
                    overlay.position = overlay.position.value

        self.paired_config.entity_categories.add(category)
        self.paired_config.add_entity(entity_type)
        return entity_type

    def register_transform_set(
        self, transform_set: Type[TransformSetT]
    ) -> Type[TransformSetT]:
        if self.paired_config is None:
            raise ValueError(
                "This Transform server is not set up to dynamically generate a paired configuration, "
                f"refusing to register Transform set {transform_set}."
            )

        if not issubclass(transform_set, TransformSet):
            raise ValueError(
                "To register an transform set for a paired configuration, please annotate a subclass of TransformSet"
            )

        name = (
            transform_set.__name__ if transform_set.name is None else transform_set.name
        )
        transforms = transform_set.transforms
        if not transforms:
            raise ValueError(f"Transform set {name} does not define transforms")

        for val in transforms:
            if not isinstance(val, str):
                raise ValueError(
                    "Transform Set members need to be valid transform id strings"
                )

        if name not in self.paired_config.transform_sets:
            self.paired_config.transform_sets[name] = transform_set
        else:
            self.paired_config.transform_sets[name].name = transform_set.name
            self.paired_config.transform_sets[name].description = (
                transform_set.description
            )
            self.paired_config.transform_sets[name].transforms.extend(
                transform_set.transforms
            )
        return transform_set

    def register_machine(self, machine: Type[MachineT]) -> Type[MachineT]:
        if self.paired_config is None:
            raise ValueError(
                "This Transform server is not set up to dynamically generate a paired configuration, "
                f"refusing to register machine {machine}."
            )

        if not issubclass(machine, MaltegoMachine):
            raise ValueError(
                "To register an machine for a paired configuration, please annotate a subclass of Machine"
            )

        name = machine.__name__ if machine.name is None else machine.name
        code = machine.code
        if not isinstance(code, str):
            raise ValueError(
                f"Machine {name} code needs to be a valid machine definition string"
            )

        machine.get_refs()

        self.paired_config.machines[name] = machine
        return machine

    def register_icon(self, icon: Type[IconT]) -> Type[IconT]:
        if self.paired_config is None:
            raise ValueError(
                "This Transform server is not set up to dynamically generate a paired configuration, "
                f"refusing to register icon {icon}."
            )

        if not issubclass(icon, MaltegoIcon):
            raise ValueError(
                "To register an machine for a paired configuration, please annotate a subclass of Machine"
            )

        name = icon.__name__ if icon.name is None else icon.name
        filename = icon.filename
        if not isinstance(filename, str) or not filename:
            raise ValueError(
                f"Icon filename {filename} needs to be a valid non-empty string"
            )

        category = icon.category
        if not isinstance(category, str) or not category:
            raise ValueError(
                f"Icon {name} category needs to be a valid non-empty string"
            )

        self.paired_config.add_icon_from_file(name, filename, category)
        return icon

    def get_transform_display_name(
        self, display_name: Optional[str], tf_function_name: str
    ) -> str:
        _display_name = display_name or tf_function_name
        display_name_prefix = ""
        if (
            self._settings.transform_prefix
            and self._settings.transform_display_name_prefix
        ):
            display_name_prefix = self._settings.transform_display_name_prefix
        _display_name = f"{display_name_prefix}{_display_name}"
        return _display_name

    def add_authenticator(self, authenticator: OAuthAuthenticator) -> TransformSetting:
        if not self.paired_config.authenticators:
            self.runner.middlewares.append(OAuthMiddleware())
        self.paired_config.authenticators[authenticator.name] = authenticator
        setting = TransformSetting(
            name=authenticator.access_token_input,
            display_name="OAuth Token",
            optional=True,
            auth=True,
            popup=False,
            is_oauth=True,
        )
        return setting

    def register_transform(
        self,
        tf_function: Optional[TransformCallableAlias] = None,
        display_name: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        author: Optional[str] = None,
        location_relevance: Optional[str] = None,
        ns: Optional[str] = None,
        owner: Optional[str] = None,
        disclaimer: Optional[str] = None,
        version: Optional[str] = None,
        settings: Optional[List[TransformSetting]] = None,
        transform_set: Optional[str] = None,
        authenticator: Optional[OAuthAuthenticator] = None,
        metadata: Optional[Dict[str, str]] = None,
        any_properties: Optional[List[str]] = None,
        all_properties: Optional[List[str]] = None,
        client_filter: Optional[MaltegoClientFilter] = None,
        input_constraint: Optional[InputConstraint] = None,
        interactive: Optional[bool] = False,
        composite_entities: Optional[bool] = False,
    ) -> Callable[[TransformCallableAlias], TransformCallableAlias]:
        """
        This decorator registers a function as a Maltego transform, making it discoverable by the Maltego client.

        :param tf_function: The function to register as a Maltego transform.
        :type tf_function: Optional[TransformCallableAlias]

        :param display_name: The display name shown in the Maltego Client. If not specified,
            it is derived from the transform function name.
        :type display_name: Optional[str]

        :param name: The unique name for the transform. If not specified, the transform function name is used.
        :type name: Optional[str]

        :param description: A brief description of the transform's purpose and functionality.
        :type description: Optional[str]

        :param author: The author's email or identifier. Defaults to the value in the server settings.
        :type author: Optional[str]

        :param location_relevance: Metadata for specifying the transform's relevance to geographic locations.
        :type location_relevance: Optional[str]

        :param ns: The namespace for the transform. Defaults to the server settings.
        :type ns: Optional[str]

        :param owner: The owner of the transform. Defaults to the server settings.
        :type owner: Optional[str]

        :param disclaimer: A disclaimer for using the transform, shown in the Maltego Client.
        :type disclaimer: Optional[str]

        :param version: The version of the transform. Defaults to the value in the server settings.
        :type version: Optional[str]

        :param settings: A list of configurable settings for the transform, such as API keys or toggles.
        :type settings: Optional[List[TransformSetting]]

        :param transform_set: The transform set to which this transform belongs.
        :type transform_set: Optional[str]

        :param authenticator: An OAuth authenticator for securing transform requests.
        :type authenticator: Optional[OAuthAuthenticator]

        :param metadata: Additional metadata for tagging or categorizing the transform during discovery.
        :type metadata: Optional[Dict[str, str]]

        :param client_filter: Filter for Maltego client versions supported for this transform. Must provide with MaltegoClient.

            Example::

                client_filter = MaltegoClientFilter(
                    min_clients=[
                        MaltegoClient(name="Maltego Desktop", version=(2, 5, 0)),
                        MaltegoClient(name="Maltego Web Browser", version=(1, 0, 0)),
                    ],
                    max_clients=[
                        MaltegoClient(name="Maltego Web Browser", version=(3, 0, 0)),
                    ],
                )
        :type client_filter: Optional[MaltegoClientFilter]

        :param any_properties: A list of properties where the transform can run if any are present in the entity.
        :type any_properties: Optional[List[str]]

        :param all_properties: A list of properties where the transform can run only if all are present in the entity.
        :type all_properties: Optional[List[str]]

        :param input_constraint: Logical constraints for filtering transform inputs.
        :type input_constraint: Optional[InputConstraint]

        :param interactive: Whether the transform uses prompts or not.
        :type interactive: Optional[bool]

        :param composite_entities: Whether the transform uses composite entities.
        :type composite_entities: Optional[bool]

        :raises ValueError: If the transform name is invalid, or if mutual exclusivity between `any_properties` and
            `all_properties` is violated.
        :raises TypeError: If metadata or client version parameters are not valid types.

        :return: The decorated function that acts as a Maltego transform.
        :rtype: Callable[[TransformCallableAlias], TransformCallableAlias]
        """

        def inner(tf_function: TransformCallableAlias) -> TransformCallableAlias:
            _name = name or tf_function.__name__
            try:
                if not ALLOWED_TX_ID.fullmatch(_name):
                    raise ValueError(f"Invalid transform name: {_name!r}.")
                _display_name = self.get_transform_display_name(
                    display_name, tf_function.__name__
                )
                _description = MaltegoTransformServer.get_transform_description(description)
                settings_as_list = list(settings) if settings else []
                if authenticator:
                    settings_keys = {p.name for p in settings_as_list}
                    auth_setting = self.add_authenticator(authenticator)
                    if authenticator.access_token_input not in settings_keys:
                        settings_as_list.append(auth_setting)
                assert_metadata(metadata)

                self._registration_queue.append(
                    MaltegoTransform(
                        impl=tf_function,
                        name=_name,
                        description=_description,
                        display_name=_display_name,
                        author=author,
                        location_relevance=location_relevance,
                        settings=settings_as_list,
                        owner=owner,
                        disclaimer=disclaimer,
                        version=version,
                        transform_ns=ns,
                        transform_set=transform_set,
                        authenticator=authenticator,
                        metadata=metadata,
                        client_filter=client_filter,
                        any_properties=any_properties,
                        all_properties=all_properties,
                        input_constraint=input_constraint,
                        interactive=interactive,
                        composite_entities=composite_entities,
                    )
                )
            except (ValueError, TypeError) as exc:
                raise type(exc)(
                    f"Failed to register transform {_name!r} "
                    f"(defined in {tf_function.__module__}.{tf_function.__qualname__}): {exc}"
                ) from exc
            return tf_function

        if tf_function is not None:
            inner(tf_function)
        return inner

    def add_config_to_set(self, transform_id: str, transform: MaltegoTransform) -> None:
        if transform.transform_set is None:
            log.warning(
                f"Transform {transform_id} does not specify a Transform set, "
                "consider adding it to one."
            )
        elif self.paired_config is not None:
            self.paired_config.add_transform_to_set(
                transform.transform_set, transform_id
            )

    @property
    def is_setup(self) -> bool:
        return self.__setup

    def run_server(
        self,
        host: str,
        port: int,
        ssl: bool = True,
        ssl_cert_file: Optional[str] = None,
        ssl_key_file: Optional[str] = None,
        log_config: Optional[Union[Dict[str, Any], str]] = None,
        reload: bool = False,
        tracer_provider: Optional[Any] = None,
        tracing_excluded_urls: Optional[str] = None,
    ) -> None:
        if not self.is_setup:
            raise RuntimeError(
                "Cannot run APP since server setup has not run yet. Please run setup() before calling run_server"
            )
        # TraceparentMiddleware is added first so it ends up innermost.
        # setup_tracing (when provided) adds the OTEL middleware last, making
        # it outermost — OTEL creates the span before TraceparentMiddleware runs.
        # ETags are process-start timestamps, not content hashes, so they can
        # stay outermost with gzip enabled.
        self.app.add_middleware(TraceparentMiddleware)
        self.app.add_middleware(ETagMiddleware)
        if tracer_provider is not None:
            setup_tracing(self.app, tracer_provider, excluded_urls=tracing_excluded_urls)
        if not self.v3server:
            raise RuntimeError(
                "Cannot run APP since transform protocol routes are not initialized. Please run setup() first"
            )
        self.runner.startup()
        http_scheme = "https" if ssl else "http"
        config = self.__get_config(
            ssl, ssl_cert_file, ssl_key_file, host, port, log_config, reload
        )
        log.info(
            f"maltego-transforms {__version__} - {self._settings.server_name} {self._settings.version} server "
            "started and ready to serve requests."
        )
        log.info(
            "Seed URL configuration: full_host_url=%s trust_forwarded_headers=%s",
            self._settings.full_host_url,
            self._settings.trust_forwarded_headers,
        )
        _host = self._display_host(host)
        if self.v3server:
            log.info(
                f"Seed Endpoint: {http_scheme}://{_host}:{port}/{self._get_seed_bridge_seed_url()}"
            )
            log.info(
                f"Transform API Endpoint: {http_scheme}://{_host}:{port}/{self.v3server.get_prefix()}"
            )
            log.info(f"Transforms discovered: {len(self.v3server.transforms)}")
        else:
            log.info("No built-in protocol routes enabled.")

        log.info("Available app URLs:")
        for route_url in self.get_registered_route_urls(http_scheme, host, port):
            log.info(route_url)

        log.info("Discovery Results:")
        log.info(f"{len(self.paired_config.entities)} Entities")
        log.info(f"{len(self.paired_config.transform_sets)} Transform Sets")
        log.info(f"{len(self.paired_config.icons)} Icons")
        log.info(f"{len(self.paired_config.authenticators)} Authenticators")
        log.info(f"{len(self.paired_config.machines)} Machines")

        # Log entity config overrides if configured
        if self._settings.entity_config_overrides:
            log_entity_config_overrides(self._settings.entity_config_overrides)
        server = uvicorn.Server(config)
        if config.should_reload:
            assert config.workers == 1
            sock = config.bind_socket()
            ChangeReload(config, target=server.run, sockets=[sock]).run()
        else:
            asyncio.run(server.serve())

    def get_routers(
        self,
    ) -> List[fastapi.routing.APIRouter]:
        """Return routers that should be included when composing servers."""
        routers: List[fastapi.routing.APIRouter] = []
        if self.v3server:
            routers.append(self.v3server.prepare_app())
        routers.extend(self._protocol_routers)
        return routers

    def concat_server(self, other: "MaltegoTransformServer") -> None:
        """Concatenates two transform server, meaning that the routes of other will be included in the main servers
        routing table. This allows to run multiple integration servers as part of a single server setup.

        :param other: The other transform server which routes shall be included into the main transform server
        :type MaltegoTransformServer: MaltegoTransformServer
        """
        for router in other.get_routers():
            self.app.include_router(router)


_DEFAULT_SETTINGS = MaltegoServerSettings(server_name="", ns="None", author=None)
_server = MaltegoTransformServer(
    settings=_DEFAULT_SETTINGS,
)
register_transform = _server.register_transform
register_entity = _server.register_entity
register_transform_set = _server.register_transform_set
register_machine = _server.register_machine
register_icon = _server.register_icon


def setup(settings: MaltegoServerSettings) -> None:
    _server.setup(settings)


def run_server(
    settings: Optional[MaltegoServerSettings] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    prefix: Optional[str] = None,
    full_host_url: Optional[str] = None,
    ssl: Optional[bool] = None,
    ssl_cert_file: Optional[str] = None,
    ssl_key_file: Optional[str] = None,
    transform_middlewares: Optional[List[TransformMiddleware]] = None,
    log_level: str = "INFO",
    reload: bool = False,
    hub_item: Optional[MaltegoHubItem] = None,
    auth_settings: Optional["AuthSettings"] = None,
    tracer_provider: Optional[Any] = None,
    tracing_excluded_urls: Optional[str] = None,
) -> None:
    """This function runs a maltego transform server using uvicorn and fastapi.

    :param settings: A MaltegoServerSettings Object. This uses pydantic's BaseSettings and environment variables
                      or a .env file can be used to overwrite the values via the Environment.
    :type settings: MaltegoServerSettings, optional
    :param host: The host used by uvicorn to bind to. Can be overridden by ``MALTEGO_SERVER_HTTP_ADDR`` env var.
        Default is ``127.0.0.1`` (loopback only). Pass ``0.0.0.0`` to listen on all interfaces.
    :type host: str, Optional
    :param port: The host port used by uvicorn to bind to. Can be overridden by ``MALTEGO_SERVER_HTTP_PORT`` env var.
        Default is ``3000``.
    :type port: int, Optional
    :param ssl: Whether SSL should be used for the transform server.
        Converted internally to protocol ("https" if True, "http" if False).
    :type ssl: bool, Optional
    :param ssl_cert_file: The file system path of an SSL certificate used for HTTPS communication.
        Can be overridden by ``MALTEGO_SERVER_CERT_FILE`` env var.
    :type ssl_cert_file: str, Optional
    :param ssl_key_file: The file system path of an SSL private key matching the certificate.
        Can be overridden by ``MALTEGO_SERVER_CERT_KEY`` env var.
    :type ssl_key_file: str, Optional
    :param transform_middlewares:
        Instances of TransformMiddleware's used in transform executions.
        Transform Middlewares can be used to add additional logic right before or right after a transform has run.
        The middleware sees the transforms execution context metadata and can be used in all kinds of applications
        from rate-limiting to logging. See :ref:`middleware_api`
    :type transform_middlewares: List[TransformMiddleware], Optional
    :param log_level:
        Log Level used by the transform server.
        Possible values: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``
    :type log_level: str
    :param reload:
        Hot code reloading (experimental. Do not use in production environments).
        Allows for hot code-reloading to change transform code without restarting the server
        please make sure the start_server function is guarded by a main guard and setup is called
        outside of the main guard to ensure this is working
    :type reload: bool
    :param hub_item:
        A Instance of :class:`MaltegoHubItem`, allowing to announce hub item metadata associated with an integration.
        See  :ref:`hub_item_api`
    :type hub_item: MaltegoHubItem, Optional
    :param prefix:
        A, optional API prefix for the integrations. By default the integrations is reachable on
        ``http://<host>:<port>/seed``. When specifying this parameter
        it will be ``http://<host>:<port>/<api-prefix>/seed``

        .. deprecated:: 3.3.0
            Use prefix parameter in TransformServerSettings instead
    :type prefix: str, Optional
    :param full_host_url:
        Hard codes the server url returned in the seed response. Under normal operation the content
        of the response is auto-generated to point to the same server then the seed request.
        It can be beneficial to overwrite that in some cases (for example if we want to point to another server).

        .. deprecated:: 3.3.0
            Use prefix parameter in TransformServerSettings instead
    :param auth_settings:
        Optional authentication settings for JWT/OIDC/SAML validation.
        If provided, will be used for token validation on protected endpoints.
        Can also be configured via MALTEGO_SERVER_AUTH_* environment variables.
    :type auth_settings: AuthSettings, Optional
    :param tracer_provider:
        An OpenTelemetry ``TracerProvider`` instance pre-configured with your
        chosen exporter (e.g. Azure Monitor, OTLP, Jaeger). When provided,
        the server sets it as the global OTEL provider, registers W3C
        TraceContext, B3 and W3C Baggage propagators, and instruments the
        FastAPI application. Requires the ``tracing`` optional extra::

            pip install maltego-transforms[tracing]

        Example::

            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            run_server(settings=..., tracer_provider=provider)

    :type tracer_provider: opentelemetry.sdk.trace.TracerProvider, Optional
    :param tracing_excluded_urls:
        Comma-separated list of URL patterns to exclude from OTEL tracing
        (forwarded to the FastAPI instrumentor). Example: ``"/health,/metrics"``.
        Only applies when ``tracer_provider`` is set.
    :type tracing_excluded_urls: str, Optional

    """
    # Resolve log level
    effective_log_level = log_level
    if settings is not None and hasattr(settings, 'log_level'):
        effective_log_level = settings.log_level
    if isinstance(effective_log_level, str):
        effective_log_level = effective_log_level.upper()

    log_config = get_logging_config(effective_log_level)

    # Configure auth settings - provided or load from env/CLI and log at startup
    if auth_settings is not None:
        set_auth_settings(auth_settings)
    else:
        # Load from env vars / CLI args
        auth_settings = get_auth_settings()

    log.info(
        "Auth configuration: enabled=%s, mode=%s, provider_type=%s, provider_url=%s",
        auth_settings.enabled,
        auth_settings.mode.value,
        auth_settings.provider_type,
        auth_settings.provider_url,
    )

    if full_host_url is not None:
        warn(
            "full_host_url setting in run_server is deprecated. Use TransformServerSettings directly instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if settings is None:
            raise ValueError(
                "Cannot use deprecated full_host_url argument without a settings argument"
            )
        settings.full_host_url = full_host_url
    if prefix is not None:
        warn(
            "prefix setting in run_server is deprecated. Use TransformServerSettings directly instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if settings is None:
            raise ValueError(
                "Cannot use deprecated prefix argument without a settings argument"
            )
        settings.api_prefix = prefix

    if reload:
        log.warning("Hot code-reload currently not working. Disabling feature")
        reload = False
    if settings is not None:
        if reload:
            raise RuntimeError(
                "Hot-reloading cannot be used if settings argument is supplied to run_server. "
                "To enable hot reloading behavior please call setup() first and remove settings argument"
            )
        _server.setup(settings)

    _server.set_hub_item(hub_item)
    if transform_middlewares:
        for middleware in transform_middlewares:
            _server.add_middleware(middleware)

    # Build http_kwargs from all sources
    # ENV vars > .env file > function params > http_settings > defaults
    http_kwargs: Dict[str, Any] = {}

    if settings is not None and settings.http_settings is not None:
        http_kwargs['http_addr'] = settings.http_settings.http_addr
        http_kwargs['http_port'] = settings.http_settings.http_port
        http_kwargs['protocol'] = settings.http_settings.protocol
        http_kwargs['cert_file'] = settings.http_settings.cert_file
        http_kwargs['cert_key'] = settings.http_settings.cert_key
        http_kwargs['domain'] = settings.http_settings.domain
        http_kwargs['root_url'] = settings.http_settings.root_url
        http_kwargs['forwarded_allow_ips'] = settings.http_settings.forwarded_allow_ips

    # Function params override http_settings (both can be overridden by MALTEGO_SERVER_* env vars)
    http_func_params: Dict[str, Any] = {}
    if host is not None:
        http_func_params['http_addr'] = host
    if port is not None:
        http_func_params['http_port'] = port
    if ssl is not None:
        http_func_params['protocol'] = 'https' if ssl else 'http'
    if ssl_cert_file is not None:
        http_func_params['cert_file'] = ssl_cert_file
    if ssl_key_file is not None:
        http_func_params['cert_key'] = ssl_key_file

    # Warn if both http_settings and function params are provided
    if settings is not None and http_func_params:
        http_settings_explicitly_set = 'http_settings' in settings.model_fields_set
        if http_settings_explicitly_set:
            warn(
                f"Both settings.http_settings and run_server() HTTP params ({list(http_func_params.keys())}) "
                "were provided. Function params will override http_settings values (but env vars will take precedence).",
                UserWarning,
                stacklevel=2
            )

    http_kwargs.update(http_func_params)

    # Create new instance - pydantic-settings applies: env > dotenv > CLI > init
    resolved_http = ServerHTTPSettings(**http_kwargs)

    if settings is not None:
        settings.http_settings = resolved_http

    effective_host = resolved_http.http_addr
    effective_port = resolved_http.http_port
    effective_ssl = resolved_http.use_ssl
    effective_ssl_cert_file = resolved_http.cert_file
    effective_ssl_key_file = resolved_http.cert_key

    if effective_host == "0.0.0.0":
        log.warning(
            "Server is listening on all interfaces (0.0.0.0) — ensure this is intended."
        )

    return _server.run_server(
        effective_host,
        effective_port,
        ssl=effective_ssl,
        ssl_cert_file=effective_ssl_cert_file,
        ssl_key_file=effective_ssl_key_file,
        log_config=log_config.model_dump(),
        reload=reload,
        tracer_provider=tracer_provider,
        tracing_excluded_urls=tracing_excluded_urls,
    )
