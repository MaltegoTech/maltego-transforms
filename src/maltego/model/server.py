# Copyright (c) Maltego Technologies GmbH.
import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Any, Type, List, Dict, Tuple
from enum import Enum
from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

log = logging.getLogger(__name__)

# Standard environment variable prefix for all Maltego server settings
MALTEGO_ENV_PREFIX = "MALTEGO_SERVER_"

# Mapping of deprecated env var names to their field names
# These are the old unprefixed env vars that should now use MALTEGO_ENV_PREFIX
_DEPRECATED_ENV_VAR_MAPPING = {
    # Seed bridge settings
    'REQUIRE_API_KEY': 'require_api_key',
    # MaltegoServerSettings fields
    'SERVER_NAME': 'server_name',
    'TRANSFORM_EXECUTION_TIMEOUT': 'transform_execution_timeout',
    'MIDDLEWARE_EXECUTION_TIMEOUT': 'middleware_execution_timeout',
    'NS': 'ns',
    'AUTHOR': 'author',
    'OWNER': 'owner',
    'VERSION': 'version',
    'ALLOW_REGENERATING_OAUTH_KEYS': 'allow_regenerating_oauth_keys',
    'MAX_CONCURRENT_TRANSFORMS_PER_USER': 'max_concurrent_transforms_per_user',
    'TRANSFORM_PREFIX': 'transform_prefix',
    'TRANSFORM_NAME_PREFIX': 'transform_name_prefix',
    'TRANSFORM_APP_NAME_PREFIX': 'transform_app_name_prefix',
    'TRANSFORM_DISPLAY_NAME_PREFIX': 'transform_display_name_prefix',
    'API_PREFIX': 'api_prefix',
    'FULL_HOST_URL': 'full_host_url',
    'TRUST_FORWARDED_HEADERS': 'trust_forwarded_headers',
    'DISCLAIMER': 'disclaimer',
    'V3_PAGE_SIZE_MAX': 'v3_page_size_max',
    'NUM_WORKER': 'num_worker',
    'TRANSFORM_RUNNER': 'transform_runner',
    'SCHEDULED_CLEANUP_SECONDS': 'scheduled_cleanup_seconds',
}


def _get_all_env_values() -> Dict[str, str]:
    """
    Get environment values from both os.environ and .env file.
    
    Returns a merged dict with os.environ taking precedence over .env values.
    """
    # Load .env file values (returns empty dict if file doesn't exist)
    dotenv_vals = dotenv_values('.env')
    # Merge: os.environ wins over .env
    merged = {**dotenv_vals, **os.environ}
    return merged


def _check_deprecated_env_vars(values: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check for deprecated environment variable names, emit warnings, and apply values.
    
    If a deprecated env var is set and the new prefixed version is NOT set,
    the value is passed through with a deprecation warning.
    
    This checks both os.environ and .env file, with os.environ taking precedence.
    
    Priority: New prefixed env vars > deprecated env vars > CLI args > code values.
    """
    all_env = _get_all_env_values()
    
    for old_name, field_name in _DEPRECATED_ENV_VAR_MAPPING.items():
        new_name = f'{MALTEGO_ENV_PREFIX}{old_name}'
        
        # Check both case variations
        old_value = all_env.get(old_name) or all_env.get(old_name.lower())
        new_value = all_env.get(new_name) or all_env.get(new_name.lower())
        
        if old_value is not None and new_value is None:
            # Old env var is set but new one isn't - emit warning and apply value
            log.warning(
                f"Deprecation Warning: Environment variable '{old_name}' is deprecated. "
                f"Please use '{new_name}' instead. "
                f"Support for '{old_name}' will be removed in a future version."
            )
            # Set the value - deprecated env vars override CLI and code values
            values[field_name] = old_value
    
    return values

PAGE_SIZE_DEFAULT = 50


class HTTPSettingsCLISource(PydanticBaseSettingsSource):
    """CLI argument source for ServerHTTPSettings.
    
    Supports both SDK names (--http-port, --protocol) and legacy names (--port, --ssl).
    """
    
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> Tuple[Any, str, bool]:
        args, _ = _http_settings_cli_parser().parse_known_args()
        field_value = vars(args).get(field_name)
        return field_value, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        return value

    def __call__(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(field, field_name)
            field_value = self.prepare_field_value(field_name, field, field_value, value_is_complex)
            if field_value is not None:
                result[field_key] = field_value
        return result


class ServerSettingsCLISource(PydanticBaseSettingsSource):
    """CLI argument source for MaltegoServerSettings.
    
    Provides command-line configuration for all server settings fields.
    """
    
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> Tuple[Any, str, bool]:
        args, _ = _server_settings_cli_parser().parse_known_args()
        field_value = vars(args).get(field_name)
        return field_value, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        return value

    def __call__(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(field, field_name)
            field_value = self.prepare_field_value(field_name, field, field_value, value_is_complex)
            if field_value is not None:
                result[field_key] = field_value
        return result


def _server_settings_cli_parser() -> argparse.ArgumentParser:
    """CLI argument parser for MaltegoServerSettings.
    
    Provides CLI arguments for all server configuration fields:
    - Server identity: --server-name, --ns, --author, --owner, --version
    - Timeouts: --transform-execution-timeout, --middleware-execution-timeout
    - URL configuration: --api-prefix, --full-host-url
    - Transform naming: --transform-prefix, --transform-name-prefix, etc.
    - Seed bridge settings: --require-api-key
    - Logging: --log-level
    """
    parser = argparse.ArgumentParser()
    # Server identity
    parser.add_argument("--server-name", dest="server_name", default=None,
                        help="Unique name for the server")
    parser.add_argument("--ns", dest="ns", default=None,
                        help="Namespace for transforms")
    parser.add_argument("--author", dest="author", default=None,
                        help="Author attribution for transforms")
    parser.add_argument("--owner", dest="owner", default=None,
                        help="Owner attribution for transforms")
    parser.add_argument("--version", dest="version", default=None,
                        help="Server version")
    # Timeouts
    parser.add_argument("--transform-execution-timeout", dest="transform_execution_timeout", type=int, default=None,
                        help="Transform execution timeout in seconds")
    parser.add_argument("--middleware-execution-timeout", dest="middleware_execution_timeout", type=int, default=None,
                        help="Middleware execution timeout in seconds")
    # URL configuration
    parser.add_argument("--api-prefix", dest="api_prefix", default=None,
                        help="API URI prefix")
    parser.add_argument("--full-host-url", dest="full_host_url", default=None,
                        help="Override host URL in seed responses")
    # Transform naming
    parser.add_argument("--transform-prefix", dest="transform_prefix", action=argparse.BooleanOptionalAction, default=None,
                        help="Enable transform name prefixes")
    parser.add_argument("--transform-name-prefix", dest="transform_name_prefix", default=None,
                        help="Prefix for transform names")
    parser.add_argument("--transform-app-name-prefix", dest="transform_app_name_prefix", default=None,
                        help="Prefix for transform app names")
    parser.add_argument("--transform-display-name-prefix", dest="transform_display_name_prefix", default=None,
                        help="Prefix for transform display names")
    # Pagination and concurrency
    parser.add_argument("--v3-page-size-max", dest="v3_page_size_max", type=int, default=None,
                        help="Max page size for v3 pagination")
    parser.add_argument("--max-concurrent-transforms-per-user", dest="max_concurrent_transforms_per_user", type=int, default=None,
                        help="Max concurrent transforms per user")
    # OAuth
    parser.add_argument("--allow-regenerating-oauth-keys", dest="allow_regenerating_oauth_keys", action=argparse.BooleanOptionalAction, default=None,
                        help="Allow regenerating OAuth keys")
    # Seed bridge settings
    parser.add_argument("--require-api-key", dest="require_api_key", action=argparse.BooleanOptionalAction, default=None,
                        help="Require API key authentication")
    # Logging
    parser.add_argument("--log-level", dest="log_level",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
                                 'debug', 'info', 'warning', 'error', 'critical'],
                        default=None, help="Server log level")
    # Runtime settings
    parser.add_argument("--num-worker", dest="num_worker", type=int, default=None,
                        help="Number of worker threads")
    parser.add_argument("--transform-runner", dest="transform_runner",
                        choices=['THREADED', 'ASYNC', 'threaded', 'async'],
                        default=None, help="Transform runner type")
    parser.add_argument("--scheduled-cleanup-seconds", dest="scheduled_cleanup_seconds", type=int, default=None,
                        help="Cleanup interval in seconds")
    parser.add_argument("--disclaimer", dest="disclaimer", default=None,
                        help="Disclaimer URL")
    return parser


def _http_settings_cli_parser() -> argparse.ArgumentParser:
    """CLI argument parser for HTTP settings.
    
    Supports both SDK-aligned names and legacy names for backward compatibility:
    - --http-port / --port -> http_port
    - --http-addr -> http_addr
    - --protocol / --ssl / --no-ssl -> protocol
    - --cert-file / --ssl-cert-file -> cert_file
    - --cert-key / --ssl-key-file -> cert_key
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-port", "--port", dest="http_port", type=int, default=None,
                        help="HTTP server port")
    parser.add_argument("--http-addr", dest="http_addr", type=str, default=None,
                        help="HTTP server bind address")
    parser.add_argument("--protocol", dest="protocol", type=str, choices=['http', 'https'], default=None,
                        help="Server protocol (http or https)")
    parser.add_argument("--ssl", dest="protocol", action="store_const", const="https",
                        help="Enable SSL (shortcut for --protocol https)")
    parser.add_argument("--no-ssl", dest="protocol", action="store_const", const="http",
                        help="Disable SSL (shortcut for --protocol http)")
    parser.add_argument("--cert-file", "--ssl-cert-file", dest="cert_file", type=str, default=None,
                        help="Path to SSL certificate file")
    parser.add_argument("--cert-key", "--ssl-key-file", dest="cert_key", type=str, default=None,
                        help="Path to SSL certificate key file")
    parser.add_argument("--domain", dest="domain", type=str, default=None,
                        help="Server domain name (e.g., mysite.com) for public URL construction")
    parser.add_argument("--root-url", dest="root_url", type=str, default=None,
                        help="Full server root URL (e.g., https://api.mysite.com:8080)")
    return parser


class ServerHTTPSettings(BaseSettings):
    """
    HTTP server configuration settings that can be overridden via environment variables.

    All settings can be configured via environment variables with the ``MALTEGO_SERVER_`` prefix.
    For example: ``MALTEGO_SERVER_HTTP_ADDR``, ``MALTEGO_SERVER_HTTP_PORT``, etc.

    Environment variables are optional and will use default values if not set.

    :param http_addr: HTTP server bind address, defaults to 127.0.0.1 (loopback only).
        Set to ``0.0.0.0`` to listen on all interfaces.
        Can be overridden via ``MALTEGO_SERVER_HTTP_ADDR`` env var or ``--http-addr`` CLI arg.
    :type http_addr: str
    :param http_port: HTTP server port, defaults to 3000
    :type http_port: int
    :param domain: Server domain name (e.g., mysite.com). Used to construct the server URL in discovery responses when root_url is not set.
    :type domain: Optional[str]
    :param root_url: Full server root URL (e.g., https://subdomain.mysite.com:3000). Takes precedence over domain. Used in discovery responses to tell Maltego where to connect.
    :type root_url: Optional[str]
    :param cert_key: Path to SSL certificate key file
    :type cert_key: Optional[str]
    :param cert_file: Path to SSL certificate file
    :type cert_file: Optional[str]
    :param protocol: Server protocol (http or https), defaults to https
    :type protocol: str
    :param cors_allowed_origins:
        Optional list of browser origins allowed to access the server via CORS.
        Defaults to the Maltego Graph Browser app origin.
        When provided, app-level CORS middleware is added during setup.
    :type cors_allowed_origins: List[str], Optional
    :param cors_allowed_origin_regex:
        Optional regular expression used to match browser origins for CORS. Disabled by default.
        Can be used instead of or in addition to ``cors_allowed_origins``.
    :type cors_allowed_origin_regex: str, Optional
    :param forwarded_allow_ips:
        Comma-separated IP addresses, CIDR ranges, or host literals allowed to supply forwarded headers.
        Use ``*`` only when every direct client is trusted.
    :type forwarded_allow_ips: str
    :param http_response_compression_enabled:
        Enable gzip response compression for clients that send a compatible ``Accept-Encoding`` header.
        Disabled by default.
    :type http_response_compression_enabled: bool
    :param http_response_compression_minimum_size:
        Minimum response size in bytes before gzip compression is applied. Defaults to 500.
    :type http_response_compression_minimum_size: int
    """

    http_addr: str = Field(default="127.0.0.1", description="HTTP server bind address (loopback by default; set to 0.0.0.0 to listen on all interfaces)")
    http_port: int = Field(default=3000, description="HTTP server port")
    domain: Optional[str] = Field(default=None, description="Server domain name")
    root_url: Optional[str] = Field(default=None, description="Full server root URL")
    cert_key: Optional[str] = Field(default=None, description="Path to SSL certificate key file")
    cert_file: Optional[str] = Field(default=None, description="Path to SSL certificate file")
    protocol: str = Field(default="https", description="Server protocol (http or https)")
    cors_allowed_origins: Optional[List[str]] = Field(
        default_factory=lambda: ["https://app.maltego.com"],
        description="Browser origins allowed to access the server via CORS",
    )
    cors_allowed_origin_regex: Optional[str] = None
    forwarded_allow_ips: str = Field(default="127.0.0.1", description="Allowed forwarded-header proxy IPs")
    http_response_compression_enabled: bool = Field(
        default=False,
        description="Enable gzip response compression for compatible clients",
    )
    http_response_compression_minimum_size: int = Field(
        default=500,
        ge=0,
        description="Minimum response size in bytes before gzip compression is applied",
    )

    model_config = SettingsConfigDict(
        env_prefix=MALTEGO_ENV_PREFIX,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
        env_ignore_empty=True,
    )

    @classmethod
    def settings_customise_sources(
        cls: Any,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Any:
        return (
            env_settings,
            dotenv_settings,
            HTTPSettingsCLISource(settings_cls),
            init_settings,
        )

    @field_validator('domain', 'root_url', 'cert_key', 'cert_file', 'cors_allowed_origin_regex', mode='before')
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Optional[str]:
        """Convert empty strings to None for optional fields"""
        if v == "" or v is None:
            return None
        return v

    @field_validator('forwarded_allow_ips', mode='before')
    @classmethod
    def empty_str_to_default_forwarded_allow_ips(cls, v: Any) -> str:
        """Convert empty strings to default value for forwarded_allow_ips"""
        if v == "" or v is None:
            return "127.0.0.1"
        return str(v)

    @field_validator('http_addr', mode='before')
    @classmethod
    def empty_str_to_default_addr(cls, v: Any) -> str:
        """Convert empty strings to default value for http_addr (127.0.0.1, loopback)"""
        if v == "" or v is None:
            return "127.0.0.1"
        return v

    @field_validator('protocol', mode='before')
    @classmethod
    def empty_str_to_default_protocol(cls, v: Any) -> str:
        """Convert empty strings to default value for protocol"""
        if v == "" or v is None:
            return "https"
        return v

    @field_validator('http_port', mode='before')
    @classmethod
    def empty_str_to_default_port(cls, v: Any) -> Any:
        """Convert empty strings to default value for http_port"""
        if v == "" or v is None:
            return 3000
        return v

    @field_validator('cors_allowed_origins', mode='before')
    @classmethod
    def _parse_cors_allowed_origins(cls, value: Any) -> Optional[List[str]]:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = [origin.strip() for origin in value.split(",") if origin.strip()]
            else:
                if parsed is None:
                    return None
                if not isinstance(parsed, list):
                    raise ValueError("cors_allowed_origins must be a list of strings")
                value = parsed
            if isinstance(parsed, list):
                value = parsed
        if not isinstance(value, list):
            raise ValueError("cors_allowed_origins must be a list of strings")
        origins = [origin.strip() for origin in value if isinstance(origin, str) and origin.strip()]
        return origins or None

    @property
    def use_ssl(self) -> bool:
        """Determine if SSL should be used based on protocol and cert files.

        Raises ValueError when protocol is 'https' but cert_file or cert_key is
        missing — fail closed instead of silently downgrading to plaintext.
        """
        if self.protocol == "https":
            if self.cert_file is None or self.cert_key is None:
                raise ValueError(
                    "protocol='https' requires both cert_file and cert_key to be set. "
                    "Refusing to start without TLS certificates (fail-closed). "
                    "To use plain HTTP, set protocol='http'."
                )
            return True
        return False


class MaltegoHubItem(BaseSettings):
    """
    This class can be used to define a "hub item" to be discovered by a Maltego Client.
    In future releases this implementation is used to show a integration in the Maltego hub
    alongside with meta information about the integration and the provider.

    :param display_name: Hub Item display name
    :type display_name: str
    :param description: Hub Item description.
    :type description: str, Optional
    :param icon_url: A URL pointing to an icon (PNG) to be shown in the hub item panel
    :type icon_url: str, Optional
    :param preview_image_url: A preview image showcasing a graph, shown in the hub items detail view.
    :type preview_image_url: str, Optional
    :param provider_name: The name of the transform developer, shown in details view
    :type provider_name: str, Optional
    :param provider_website: The website of the transform developer, shown in details view
    :type provider_website: str, Optional
    :param provider_email: Transform developer email, shown in details view
    :type provider_email: str, Optional
    :param provider_phone: The developers phone number, shown in details view
    :type provider_phone: str, Optional

    """

    display_name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    preview_image_url: Optional[str] = None
    provider_name: Optional[str] = None
    provider_website: Optional[str] = None
    provider_email: Optional[str] = None
    provider_phone: Optional[str] = None

    @classmethod
    def settings_customise_sources(
        cls: Any,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,

    ) -> Any:
        return (
            env_settings,
            dotenv_settings,
            file_secret_settings,
            init_settings,
        )


class TransformRunnerType(Enum):
    """Enum to define which transform runner to use

    :param THREADED: Threaded Transform runner with variable amount of worker
    :param ASYNC: Async transform runner, executing all transforms in the main threads event loop
    """
    THREADED = 1
    ASYNC = 2


@dataclass
class EntityConfigOverride:
    """
    A single entity config override rule.

    :param entities: List of entity type IDs to override (e.g., ["maltego.Affiliation", "maltego.affiliation.Bebo"])
    :param clients: List of client types this rule applies to (e.g., ["desktop", "web"])
    :param overrides: Dictionary of property names to override values (e.g., {"allowed_root": True})
    """
    entities: List[str]
    clients: List[str]
    overrides: Dict[str, Any]


@dataclass
class EntityConfigOverrides:
    """
    Consumer-configurable entity property overrides.

    Allows SDK consumers to specify per-client property overrides for entities.
    These are applied during entity discovery, allowing different property values
    to be served to different clients (e.g., desktop vs web).

    Example::

        EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Affiliation"],
                    clients=["desktop"],
                    overrides={"allowed_root": True}
                ),
            ]
        )

    Can also be configured via environment variable ``MALTEGO_SERVER_ENTITY_CONFIG_OVERRIDES``
    using JSON format::

        MALTEGO_SERVER_ENTITY_CONFIG_OVERRIDES='[
            {"entities": ["maltego.Affiliation"], "clients": ["desktop"], "overrides": {"allowed_root": true}}
        ]'
    """
    rules: List[EntityConfigOverride] = field(default_factory=list)


# Environment variable name for entity config overrides
ENTITY_CONFIG_OVERRIDES_ENV_VAR = f"{MALTEGO_ENV_PREFIX}ENTITY_CONFIG_OVERRIDES"


def parse_entity_config_overrides_json(json_str: str) -> EntityConfigOverrides:
    """
    Parse EntityConfigOverrides from a JSON string.

    Args:
        json_str: JSON string containing an array of override rules.

    Returns:
        EntityConfigOverrides instance.

    Raises:
        ValueError: If JSON is invalid or doesn't match expected structure.

    Example JSON format::

        [
            {
                "entities": ["maltego.Entity1", "maltego.Entity2"],
                "clients": ["desktop"],
                "overrides": {"properties.display_value": "name"}
            },
            {
                "entities": ["maltego.Entity3"],
                "clients": ["desktop", "web"],
                "overrides": {"allowed_root": true}
            }
        ]
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for entity config overrides: {e}") from e

    if not isinstance(data, list):
        raise ValueError("Entity config overrides JSON must be an array of rules")

    rules: List[EntityConfigOverride] = []
    for i, rule_data in enumerate(data):
        if not isinstance(rule_data, dict):
            raise ValueError(f"Rule at index {i} must be an object")

        entities = rule_data.get("entities")
        clients = rule_data.get("clients")
        overrides = rule_data.get("overrides")

        if not isinstance(entities, list) or not all(isinstance(e, str) for e in entities):
            raise ValueError(f"Rule at index {i}: 'entities' must be an array of strings")
        if not isinstance(clients, list) or not all(isinstance(c, str) for c in clients):
            raise ValueError(f"Rule at index {i}: 'clients' must be an array of strings")
        if not isinstance(overrides, dict):
            raise ValueError(f"Rule at index {i}: 'overrides' must be an object")

        rules.append(EntityConfigOverride(
            entities=entities,
            clients=clients,
            overrides=overrides,
        ))

    return EntityConfigOverrides(rules=rules)


def _normalize_ns_for_env(ns: str) -> str:
    """Normalize namespace for use in environment variable names.
    
    Strips common prefixes like 'maltego.' and normalizes to uppercase with underscores.
    
    Examples:
        'maltego.jinxpy_sentinel' -> 'JINXPY_SENTINEL'
        'maltego.sandbox' -> 'SANDBOX'
        'com.example.transforms' -> 'COM_EXAMPLE_TRANSFORMS'
    """
    # Strip common 'maltego.' prefix to avoid MALTEGO_SERVER_MALTEGO_...
    if ns.lower().startswith('maltego.'):
        ns = ns[8:]  # len('maltego.') == 8
    # Replace dots, spaces, hyphens, and other non-alphanumeric chars with underscores
    normalized = re.sub(r'[^a-zA-Z0-9]', '_', ns)
    # Remove consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    normalized = normalized.strip('_')
    return normalized.upper()


def load_entity_config_overrides_from_env(
    ns: Optional[str] = None,
) -> Optional[EntityConfigOverrides]:
    """
    Load EntityConfigOverrides from environment variable or .env file.

    Checks for namespace-specific env var first, then falls back to generic:
    1. MALTEGO_SERVER_{NS}_ENTITY_CONFIG_OVERRIDES (if ns provided)
    2. MALTEGO_SERVER_ENTITY_CONFIG_OVERRIDES (generic fallback)

    The 'maltego.' prefix is stripped from ns to avoid redundant naming.
    E.g., ns='maltego.sandbox' -> MALTEGO_SERVER_SANDBOX_ENTITY_CONFIG_OVERRIDES

    Values are checked in both os.environ and .env file, with os.environ taking precedence.

    Args:
        ns: Optional namespace for namespace-specific env var lookup.

    Returns:
        EntityConfigOverrides instance if env var is set and valid, None otherwise.

    Logs a warning if the env var is set but contains invalid JSON.
    """
    # Get merged env values (os.environ wins over .env)
    all_env = _get_all_env_values()
    
    env_var_name: Optional[str] = None
    env_value: Optional[str] = None

    # Try namespace-specific env var first
    if ns:
        normalized = _normalize_ns_for_env(ns)
        ns_specific_var = f"{MALTEGO_ENV_PREFIX}{normalized}_ENTITY_CONFIG_OVERRIDES"
        env_value = all_env.get(ns_specific_var)
        if env_value and env_value.strip():
            env_var_name = ns_specific_var

    # Fall back to generic env var
    if not env_value or not env_value.strip():
        env_value = all_env.get(ENTITY_CONFIG_OVERRIDES_ENV_VAR)
        if env_value and env_value.strip():
            env_var_name = ENTITY_CONFIG_OVERRIDES_ENV_VAR

    if not env_value or not env_value.strip():
        return None

    try:
        overrides = parse_entity_config_overrides_json(env_value)
        log.info(
            "Loaded %d entity config override rule(s) from %s environment variable",
            len(overrides.rules),
            env_var_name,
        )
        return overrides
    except ValueError as e:
        log.warning(
            "Failed to parse %s environment variable: %s",
            env_var_name,
            e,
        )
        return None


def merge_entity_config_overrides(
    *overrides_list: Optional[EntityConfigOverrides],
) -> Optional[EntityConfigOverrides]:
    """
    Merge multiple EntityConfigOverrides into one.

    Rules are combined in order, with later rules taking precedence for the same
    entity/client combination.

    Args:
        *overrides_list: Variable number of EntityConfigOverrides to merge (None values are skipped).

    Returns:
        Merged EntityConfigOverrides, or None if all inputs are None/empty.
    """
    all_rules: List[EntityConfigOverride] = []
    for overrides in overrides_list:
        if overrides is not None:
            all_rules.extend(overrides.rules)

    if not all_rules:
        return None

    return EntityConfigOverrides(rules=all_rules)


class MaltegoServerSettings(BaseSettings):
    """This data class is used to control the behaviour of a maltego transform server.

    All settings can be configured via environment variables with the ``MALTEGO_SERVER_`` prefix.
    For example: ``MALTEGO_SERVER_SERVER_NAME``, ``MALTEGO_SERVER_NS``, etc.

    Environment variables take precedence over programmatic values, following the priority:
    ENV vars > .env file > code.

    :param server_name: Common name for the server. Should be a unique identifier.
    :type server_name: str
    :param http_settings: HTTP server configuration settings (address, port, SSL, etc.)
    :type http_settings: ServerHTTPSettings
    :param transform_execution_timeout:
        Maximum allowed runtime for a single transform in seconds before a transform gets canceled, defaults to 3600
    :type transform_execution_timeout: int
    :param middleware_execution_timeout:
        Maximum allowed runtime for a middleware execution before a transform gets canceled, defaults to 600
    :type middleware_execution_timeout: int
    :param ns: Namespace of the transform server. Should be unique string identifying the vendor.
    :type ns: str, Optional
    :param author: Author attribution used in transform discovery, defaults to John Doe
    :type author: str, Optional
    :param owner: Owner attribution used in transform discovery
    :type owner: str, Optional
    :param version: Version of the deployed transform server, defaults to 1.0.0
    :type version: str
    :param max_concurrent_transforms_per_user:
        Optional cap on the number of in-flight transform runs allowed per user
        at any moment.  Unset by default, meaning concurrency is unbounded.  When
        set, further requests from a user that has reached the cap are rejected
        immediately with ``HTTP 429`` — there is no waiting queue.

        This is most effective when authentication is enabled: each user is then
        identified by their auth-backend identity claims (``sub`` / ``org_id``),
        so the cap applies per authenticated user and protects the worker pool
        from any single client monopolising it.  Without auth, requests are keyed
        only by source IP, so everyone behind a shared egress (e.g. an office NAT)
        shares one pool — set the value with that in mind, or leave it unset.

        Set via the ``MALTEGO_SERVER_MAX_CONCURRENT_TRANSFORMS_PER_USER``
        environment variable to override.
    :type max_concurrent_transforms_per_user: int, Optional
    :param transform_prefix:
        Enabled Transform Prefixes. Can be used in deployments to easily deploy different Transform servers
        from the same codebase. When this option is enabled the
        transform_name_prefix, transform_app_name_prefix and transform_display_name_prefix are effective.
    :type transform_prefix: bool
    :param transform_name_prefix: Adds a prefix to all transform names in discovery and execution
    :type transform_name_prefix: str, Optional
    :param transform_app_name_prefix: Adds a prefix to the transform server name
    :type transform_app_name_prefix: str, Optional
    :param transform_display_name_prefix: Adds a prefix to all discovered transforms display names
    :type transform_display_name_prefix: str, Optional
    :param v3_page_size_max:
        Max supported JSON protocol page size sent in the OPTION response during discovery.
        Currently not implemented in Maltego (4.7.0)
    :type v3_page_size_max: int
    :param entity_config_overrides:
        Optional per-client entity property overrides applied during JSON entity discovery (e.g. desktop vs web).
        Can also be provided via environment variables (see ``EntityConfigOverrides``).
    :type entity_config_overrides: EntityConfigOverrides, Optional
    :param full_host_url:
        Hard codes the server url returned in the seed response. Under normal operation the content
        of the response is auto-generated to point to the same server then the seed request.
        It can be beneficial to overwrite that in some cases (for example if we want to point to another server).
    :type full_host_url: str, Optional
    :param trust_forwarded_headers:
        Trusts x-forwarded-proto and x-forwarded-host request headers from allowed proxy IPs when auto-generating
        seed response runner URLs.
        Enable this only when the server is behind a trusted reverse proxy or ingress.
    :type trust_forwarded_headers: bool
    :param api_prefix:
        A, optional API prefix for the integrations. By default the integrations is reachable on
        ``http://<host>:<port>/seed``. When specifying this parameter
        it will be ``http://<host>:<port>/<api-prefix>/seed``
    :type api_prefix: str, Optional
    :param disclaimer:
        An optional URL displayed in the discovery step as a disclaimer, requires to be acknowledged by the user
    :type disclaimer: str, Optional
    :param num_worker:
        Number of workers to be used in :class:`ThreadedTransformRunner`
    :type num_worker: int
    :param transform_runner:
        Transform Runner implementation to be used.
        See :class:`ThreadedTransformRunner` and :class:`AsyncTransformRunner`, defaults to TransformRunnerType.THREADED
    :type transform_runner: TransformRunnerType
    :param scheduled_cleanup_seconds:
        The interval used for cleaning up inactive transforms in the runner queue.
    :type scheduled_cleanup_seconds: int
    :param log_level:
        Log level for the transform server. Possible values: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    :type log_level: str
    :param swagger_enabled:
        Enable or disable the ``/swagger`` UI and ``/openapi.json`` spec endpoints.
        Set to ``True`` in development to expose the API surface.
        Can be overridden via ``MALTEGO_SERVER_SWAGGER_ENABLED=true``.
        Defaults to ``False``.
    :type swagger_enabled: bool

    """

    model_config = SettingsConfigDict(
        env_prefix=MALTEGO_ENV_PREFIX,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
        env_ignore_empty=True,
    )

    server_name: str
    http_settings: ServerHTTPSettings = Field(default_factory=ServerHTTPSettings)
    transform_execution_timeout: int = 3600
    middleware_execution_timeout: int = 600
    ns: str = 'maltego'
    author: Optional[str] = 'John Doe'
    owner: Optional[str] = None
    version: str = "1.0.0"
    allow_regenerating_oauth_keys: bool = False
    max_concurrent_transforms_per_user: Optional[int] = None
    transform_prefix: bool = False
    transform_name_prefix: Optional[str] = None
    transform_app_name_prefix: Optional[str] = None
    transform_display_name_prefix: Optional[str] = None
    v3_page_size_max: int = PAGE_SIZE_DEFAULT
    full_host_url: Optional[str] = None
    trust_forwarded_headers: bool = False
    api_prefix: Optional[str] = None
    disclaimer: Optional[str] = None
    num_worker: int = 1
    transform_runner: TransformRunnerType = TransformRunnerType.THREADED
    scheduled_cleanup_seconds: int = 60
    entity_config_overrides: Optional[EntityConfigOverrides] = None
    log_level: str = "INFO"
    allowed_protocol_extensions: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional allowlist of protocol extension entry-point names that may be loaded. "
            "When set, only extensions whose entry-point name appears in this list are loaded; "
            "all others are skipped with a warning. When None (default), all installed "
            "extensions are loaded (backward-compatible behavior)."
        ),
    )
    swagger_enabled: bool = False

    # Deprecated
    ssl_cert_file: Optional[str] = None
    ssl_key_file: Optional[str] = None

    require_api_key: bool = Field(
        default=False,
        description=(
            "Advertised to desktop clients in discovery (as ``requireAPIKey``). When True, "
            "clients authenticate to this server with the Maltego license key in the "
            "``Maltego-API-Key`` header instead of the machine MAC address. It is not validated "
            "or enforced server-side (it is not an authentication control). It is superseded by "
            "Maltego ID: when the user is signed in with Maltego ID this flag is effectively "
            "bypassed on Maltego-hosted servers. "
            "Legacy license-mode compatibility only; leave False for new Maltego ID deployments."
        ),
    )

    @model_validator(mode='before')
    @classmethod
    def _check_deprecated_env_vars(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Check for deprecated unprefixed env vars and emit warnings."""
        return _check_deprecated_env_vars(values)

    @classmethod
    def settings_customise_sources(
        cls: Any,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Any:
        return (
            env_settings,
            dotenv_settings,
            ServerSettingsCLISource(settings_cls),
            init_settings,
        )

    @field_validator('transform_runner', mode='before')
    @classmethod
    def parse_transform_runner(cls, v: Any) -> TransformRunnerType:
        """Convert string names like 'ASYNC' or 'THREADED' to TransformRunnerType enum."""
        if isinstance(v, TransformRunnerType):
            return v
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper == 'ASYNC':
                return TransformRunnerType.ASYNC
            elif v_upper == 'THREADED':
                return TransformRunnerType.THREADED
            else:
                raise ValueError(f"Invalid transform_runner value: '{v}'. Must be 'ASYNC' or 'THREADED'.")
        if isinstance(v, int):
            return TransformRunnerType(v)
        raise ValueError(f"Invalid transform_runner type: {type(v)}. Must be string or TransformRunnerType.")

    @model_validator(mode='after')
    def _merge_env_entity_config_overrides(self) -> 'MaltegoServerSettings':
        """
        Merge entity config overrides from environment variable with programmatic overrides.

        Checks for namespace-specific env var first, then falls back to generic:
        1. MALTEGO_SERVER_{NS}_ENTITY_CONFIG_OVERRIDES (e.g., MALTEGO_SERVER_SANDBOX_...)
        2. MALTEGO_SERVER_ENTITY_CONFIG_OVERRIDES

        The 'maltego.' prefix is stripped from ns to avoid redundant naming.

        Environment variable overrides are applied after programmatic overrides,
        allowing deployment-level configuration to take precedence.
        """
        env_overrides = load_entity_config_overrides_from_env(self.ns)
        if env_overrides is not None:
            # Merge: programmatic overrides first, then env overrides (env takes precedence)
            self.entity_config_overrides = merge_entity_config_overrides(
                self.entity_config_overrides,
                env_overrides,
            )
        return self
