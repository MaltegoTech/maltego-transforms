# Copyright (c) Maltego Technologies GmbH.
"""
Unit tests for HTTP configuration system (ServerHTTPSettings).
"""

import logging
import importlib
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from maltego.model.server import (
    MaltegoServerSettings,
    ServerHTTPSettings,
    TransformRunnerType,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clear all MALTEGO_SERVER_* env vars and deprecated vars before each test"""
    env_vars = [
        # HTTP settings
        "MALTEGO_SERVER_HTTP_ADDR",
        "MALTEGO_SERVER_HTTP_PORT",
        "MALTEGO_SERVER_DOMAIN",
        "MALTEGO_SERVER_ROOT_URL",
        "MALTEGO_SERVER_CERT_KEY",
        "MALTEGO_SERVER_CERT_FILE",
        "MALTEGO_SERVER_PROTOCOL",
        # Server settings
        "MALTEGO_SERVER_SERVER_NAME",
        "MALTEGO_SERVER_V3_ENABLED",
        "MALTEGO_SERVER_V3_DISCOVERY",
        "MALTEGO_SERVER_TRANSFORM_EXECUTION_TIMEOUT",
        "MALTEGO_SERVER_MIDDLEWARE_EXECUTION_TIMEOUT",
        "MALTEGO_SERVER_NS",
        "MALTEGO_SERVER_AUTHOR",
        "MALTEGO_SERVER_OWNER",
        "MALTEGO_SERVER_VERSION",
        "MALTEGO_SERVER_ALLOW_REGENERATING_OAUTH_KEYS",
        "MALTEGO_SERVER_MAX_CONCURRENT_TRANSFORMS_PER_USER",
        "MALTEGO_SERVER_TRANSFORM_PREFIX",
        "MALTEGO_SERVER_TRANSFORM_NAME_PREFIX",
        "MALTEGO_SERVER_TRANSFORM_APP_NAME_PREFIX",
        "MALTEGO_SERVER_TRANSFORM_DISPLAY_NAME_PREFIX",
        "MALTEGO_SERVER_V3_PAGE_SIZE_MAX",
        "MALTEGO_SERVER_FULL_HOST_URL",
        "MALTEGO_SERVER_TRUST_FORWARDED_HEADERS",
        "MALTEGO_SERVER_API_PREFIX",
        "MALTEGO_SERVER_DISCLAIMER",
        "MALTEGO_SERVER_NUM_WORKER",
        "MALTEGO_SERVER_TRANSFORM_RUNNER",
        "MALTEGO_SERVER_SCHEDULED_CLEANUP_SECONDS",
        "MALTEGO_SERVER_LOG_LEVEL",
        "MALTEGO_SERVER_REQUIRE_API_KEY",
        "MALTEGO_SERVER_OVERWRITE_CONFIG",
        "MALTEGO_SERVER_GENERATE_CONFIG_DYNAMICALLY",
        "MALTEGO_SERVER_CORS_ALLOWED_ORIGINS",
        "MALTEGO_SERVER_CORS_ALLOWED_ORIGIN_REGEX",
        "MALTEGO_SERVER_FORWARDED_ALLOW_IPS",
        # Deprecated (unprefixed) env vars
        "SERVER_NAME",
        "V3_ENABLED",
        "V3_DISCOVERY",
        "TRANSFORM_EXECUTION_TIMEOUT",
        "MIDDLEWARE_EXECUTION_TIMEOUT",
        "NS",
        "AUTHOR",
        "OWNER",
        "VERSION",
        "TRANSFORM_PREFIX",
        "TRANSFORM_NAME_PREFIX",
        "TRANSFORM_DISPLAY_NAME_PREFIX",
        "V3_PAGE_SIZE_MAX",
        "FULL_HOST_URL",
        "TRUST_FORWARDED_HEADERS",
        "API_PREFIX",
        "DISCLAIMER",
        "NUM_WORKER",
        "SCHEDULED_CLEANUP_SECONDS",
        "REQUIRE_API_KEY",
        "OVERWRITE_CONFIG",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)

    original_config = ServerHTTPSettings.model_config
    test_config = SettingsConfigDict(
        env_prefix="MALTEGO_SERVER_", extra="ignore", case_sensitive=False
    )
    monkeypatch.setattr(ServerHTTPSettings, "model_config", test_config)

    yield

    monkeypatch.setattr(ServerHTTPSettings, "model_config", original_config)


@pytest.fixture
def server_module():
    return importlib.import_module("maltego.server")


@pytest.mark.unit
class TestServerHTTPSettings:
    """Test suite for ServerHTTPSettings configuration class"""

    def test_default_config(self):
        """Test default configuration values"""
        http_settings = ServerHTTPSettings()

        assert http_settings.http_addr == "127.0.0.1"  # PRP-8: default is loopback
        assert http_settings.http_port == 3000
        assert http_settings.protocol == "https"
        assert http_settings.cert_file is None
        assert http_settings.cert_key is None
        assert http_settings.domain is None
        assert http_settings.root_url is None
        assert http_settings.forwarded_allow_ips == "127.0.0.1"
        assert http_settings.http_response_compression_enabled is False
        assert http_settings.http_response_compression_minimum_size == 500

    def test_custom_config(self):
        """Test custom configuration values"""
        http_settings = ServerHTTPSettings(
            http_addr="127.0.0.1",
            http_port=8080,
            domain="example.com",
            root_url="https://api.example.com:8080",
            cert_key="/path/to/key.key",
            cert_file="/path/to/cert.crt",
            protocol="http",
        )

        assert http_settings.http_addr == "127.0.0.1"
        assert http_settings.http_port == 8080
        assert http_settings.domain == "example.com"
        assert http_settings.root_url == "https://api.example.com:8080"
        assert http_settings.cert_key == "/path/to/key.key"
        assert http_settings.cert_file == "/path/to/cert.crt"
        assert http_settings.protocol == "http"

    def test_cors_settings_default_to_disabled(self):
        http_settings = ServerHTTPSettings()

        assert http_settings.cors_allowed_origins is None
        assert http_settings.cors_allowed_origin_regex is None

    def test_cors_allowed_origins_parses_comma_separated_string(self):
        http_settings = ServerHTTPSettings(
            cors_allowed_origins="https://one.example.com, https://two.example.com"
        )

        assert http_settings.cors_allowed_origins == [
            "https://one.example.com",
            "https://two.example.com",
        ]

    def test_forwarded_allow_ips_can_be_configured(self):
        http_settings = ServerHTTPSettings(
            forwarded_allow_ips="10.0.0.1,10.0.0.2,fd00::/8"
        )

        assert http_settings.forwarded_allow_ips == "10.0.0.1,10.0.0.2,fd00::/8"

    def test_response_compression_minimum_size_allows_zero(self):
        http_settings = ServerHTTPSettings(
            http_response_compression_minimum_size=0,
        )

        assert http_settings.http_response_compression_minimum_size == 0

    def test_response_compression_minimum_size_rejects_negative_values(self):
        with pytest.raises(ValidationError):
            ServerHTTPSettings(http_response_compression_minimum_size=-1)

    def test_env_override(self, monkeypatch):
        """Test configuration from environment variables"""
        # Set environment variables
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "127.0.0.1")
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "8080")
        monkeypatch.setenv("MALTEGO_SERVER_DOMAIN", "example.com")
        monkeypatch.setenv("MALTEGO_SERVER_PROTOCOL", "http")
        monkeypatch.setenv(
            "MALTEGO_SERVER_ROOT_URL", "https://subdomain.example.com:8080"
        )
        monkeypatch.setenv("MALTEGO_SERVER_FORWARDED_ALLOW_IPS", "10.0.0.1")

        http_settings = ServerHTTPSettings()

        assert http_settings.http_addr == "127.0.0.1"
        assert http_settings.http_port == 8080
        assert http_settings.domain == "example.com"
        assert http_settings.protocol == "http"
        assert http_settings.root_url == "https://subdomain.example.com:8080"
        assert http_settings.forwarded_allow_ips == "10.0.0.1"

    def test_use_ssl_property_https_with_certs(self):
        """Test use_ssl property returns True for HTTPS with cert files"""
        http_settings = ServerHTTPSettings(
            protocol="https",
            cert_file="/path/to/cert.crt",
            cert_key="/path/to/cert.key",
        )
        assert http_settings.use_ssl is True

    def test_use_ssl_property_https_without_certs(self):
        """F21: use_ssl raises ValueError for HTTPS without cert files (fail-closed)"""
        http_settings = ServerHTTPSettings(protocol="https")
        with pytest.raises(ValueError, match="fail-closed"):
            _ = http_settings.use_ssl

    def test_use_ssl_property_http_with_certs(self):
        """Test use_ssl property returns False for HTTP even with cert files"""
        http_settings = ServerHTTPSettings(
            protocol="http", cert_file="/path/to/cert.crt", cert_key="/path/to/cert.key"
        )
        assert http_settings.use_ssl is False

    def test_use_ssl_property_https_only_cert_file(self):
        """F21: use_ssl raises ValueError when only cert_file is set (fail-closed)"""
        http_settings = ServerHTTPSettings(
            protocol="https", cert_file="/path/to/cert.crt"
        )
        with pytest.raises(ValueError, match="cert_key"):
            _ = http_settings.use_ssl

    def test_use_ssl_property_https_only_cert_key(self):
        """F21: use_ssl raises ValueError when only cert_key is set (fail-closed)"""
        http_settings = ServerHTTPSettings(
            protocol="https", cert_key="/path/to/cert.key"
        )
        with pytest.raises(ValueError, match="cert_file"):
            _ = http_settings.use_ssl

    # PRP-8: bind-default tests ------------------------------------------------

    def test_default_http_addr_is_loopback(self):
        """PRP-8: ServerHTTPSettings() must default to 127.0.0.1, not 0.0.0.0"""
        http_settings = ServerHTTPSettings()
        assert http_settings.http_addr == "127.0.0.1"

    def test_explicit_all_interfaces_override(self):
        """PRP-8: 0.0.0.0 is still fully supported when set explicitly"""
        http_settings = ServerHTTPSettings(http_addr="0.0.0.0")
        assert http_settings.http_addr == "0.0.0.0"

    def test_env_var_all_interfaces_override(self, monkeypatch):
        """PRP-8: MALTEGO_SERVER_HTTP_ADDR=0.0.0.0 env var still reaches 0.0.0.0"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "0.0.0.0")
        http_settings = ServerHTTPSettings()
        assert http_settings.http_addr == "0.0.0.0"

    def test_empty_string_env_resolves_to_loopback(self, monkeypatch):
        """PRP-8: empty MALTEGO_SERVER_HTTP_ADDR resolves to 127.0.0.1 (not 0.0.0.0)"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "")
        http_settings = ServerHTTPSettings()
        assert http_settings.http_addr == "127.0.0.1"

    def test_empty_string_programmatic_resolves_to_loopback(self):
        """PRP-8: http_addr='' passed in code resolves to 127.0.0.1 (not 0.0.0.0)"""
        http_settings = ServerHTTPSettings(http_addr="")
        assert http_settings.http_addr == "127.0.0.1"


@pytest.mark.unit
class TestMaltegoServerSettingsIntegration:
    """Test integration of ServerHTTPSettings with MaltegoServerSettings"""

    def test_default_http_settings(self):
        """Test MaltegoServerSettings creates default HTTP settings"""
        settings = MaltegoServerSettings(
            server_name="Test Server", ns="test", author="test@example.com"
        )

        assert settings.http_settings is not None
        assert settings.http_settings.http_addr == "127.0.0.1"  # PRP-8: default is loopback
        assert settings.http_settings.http_port == 3000

    def test_custom_http_settings(self):
        """Test MaltegoServerSettings with custom HTTP settings"""
        http_settings = ServerHTTPSettings(
            http_addr="192.168.1.100",
            http_port=5000,
            protocol="https",
            cert_file="/path/to/cert.crt",
            cert_key="/path/to/cert.key",
        )

        settings = MaltegoServerSettings(
            server_name="Test Server",
            ns="test",
            author="test@example.com",
            http_settings=http_settings,
        )

        assert settings.http_settings.http_addr == "192.168.1.100"
        assert settings.http_settings.http_port == 5000
        assert settings.http_settings.use_ssl is True
        assert settings.http_settings.cert_file == "/path/to/cert.crt"
        assert settings.http_settings.cert_key == "/path/to/cert.key"

    def test_http_settings_from_env(self, monkeypatch):
        """Test that HTTP settings can be configured via environment variables"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "127.0.0.1")
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "9000")
        monkeypatch.setenv("MALTEGO_SERVER_DOMAIN", "testserver.com")

        settings = MaltegoServerSettings(
            server_name="Test Server", ns="test", author="test@example.com"
        )

        assert settings.http_settings.http_addr == "127.0.0.1"
        assert settings.http_settings.http_port == 9000
        assert settings.http_settings.domain == "testserver.com"


@pytest.mark.unit
class TestServerHTTPSettingsCaseSensitivity:
    """Test case insensitivity of environment variables"""

    def test_case_insensitive_env_vars(self, monkeypatch):
        """Test that environment variables are case-insensitive"""
        monkeypatch.setenv("maltego_server_http_addr", "10.0.0.1")
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "7000")

        http_settings = ServerHTTPSettings()

        assert http_settings.http_addr == "10.0.0.1"
        assert http_settings.http_port == 7000


@pytest.mark.unit
class TestServerHTTPSettingsEnvPriority:
    """Test that environment variables take priority over programmatic values"""

    def test_env_overrides_kwargs(self, monkeypatch):
        """Test that ENV vars override kwargs passed to constructor"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "8080")

        # Pass a different value programmatically
        http_settings = ServerHTTPSettings(http_port=9000)

        assert http_settings.http_port == 8080

    def test_kwargs_used_when_env_not_set(self):
        """Test that kwargs are used when ENV vars are not set"""
        http_settings = ServerHTTPSettings(http_addr="192.168.1.1", http_port=5000)

        assert http_settings.http_addr == "192.168.1.1"
        assert http_settings.http_port == 5000

    def test_partial_env_override(self, monkeypatch):
        """Test partial ENV override - some from env, some from kwargs"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "8080")

        http_settings = ServerHTTPSettings(
            http_addr="192.168.1.1",
            http_port=9000,
        )

        assert http_settings.http_addr == "192.168.1.1"  # from kwargs
        assert http_settings.http_port == 8080  # from env


@pytest.mark.unit
class TestMaltegoServerSettingsDeprecatedEnvVars:
    """Test backward compatibility for deprecated unprefixed env vars"""

    def test_deprecated_env_var_still_works(self, monkeypatch, caplog):
        """Test that old unprefixed env vars still work"""
        monkeypatch.setenv("SERVER_NAME", "OldEnvServerName")

        with caplog.at_level(logging.WARNING):
            settings = MaltegoServerSettings(server_name="CodeServerName")

        assert settings.server_name == "OldEnvServerName"
        # Should log deprecation warning
        assert "SERVER_NAME" in caplog.text
        assert "deprecated" in caplog.text.lower()
        assert "MALTEGO_SERVER_SERVER_NAME" in caplog.text

    def test_new_env_var_takes_precedence(self, monkeypatch):
        """Test that new prefixed env var wins over deprecated one"""
        monkeypatch.setenv("MALTEGO_SERVER_SERVER_NAME", "NewEnvServerName")
        monkeypatch.setenv("SERVER_NAME", "OldEnvServerName")

        settings = MaltegoServerSettings(server_name="CodeServerName")

        # New prefixed env var should win
        assert settings.server_name == "NewEnvServerName"

    def test_deprecated_forwarded_headers_env_var_still_works(
        self, monkeypatch, caplog
    ):
        """Test that old TRUST_FORWARDED_HEADERS env var still works"""
        monkeypatch.setenv("TRUST_FORWARDED_HEADERS", "true")

        with caplog.at_level(logging.WARNING):
            settings = MaltegoServerSettings(server_name="Test")

        assert settings.trust_forwarded_headers is True
        assert "TRUST_FORWARDED_HEADERS" in caplog.text
        assert "MALTEGO_SERVER_TRUST_FORWARDED_HEADERS" in caplog.text

    def test_no_warning_when_only_new_env_var_set(self, monkeypatch, caplog):
        """Test no deprecation warning when only new env var is used"""
        monkeypatch.setenv("MALTEGO_SERVER_SERVER_NAME", "NewEnvServerName")

        with caplog.at_level(logging.WARNING):
            settings = MaltegoServerSettings(server_name="CodeServerName")

        assert settings.server_name == "NewEnvServerName"
        # Should NOT log any deprecation warning about SERVER_NAME
        assert (
            "SERVER_NAME" not in caplog.text
            or "MALTEGO_SERVER_SERVER_NAME" not in caplog.text
        )


@pytest.mark.unit
class TestMaltegoServerSettingsEnvPrefix:
    """Test that MaltegoServerSettings uses MALTEGO_SERVER_ prefix for env vars"""

    def test_log_level_default(self):
        """Test log_level default value is INFO"""
        settings = MaltegoServerSettings(server_name="Test")
        assert settings.log_level == "INFO"

    def test_code_value_used_when_env_not_set(self):
        """Test code values are used when env vars not set"""
        settings = MaltegoServerSettings(
            server_name="CodeServer", ns="code.ns", author="CodeAuthor"
        )

        assert settings.server_name == "CodeServer"
        assert settings.ns == "code.ns"
        assert settings.author == "CodeAuthor"

    def test_all_env_vars_work(self, monkeypatch):
        """Comprehensive test that ALL MaltegoServerSettings env vars work"""
        # Set ALL env vars
        monkeypatch.setenv("MALTEGO_SERVER_SERVER_NAME", "AllEnvServer")
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_EXECUTION_TIMEOUT", "1800")
        monkeypatch.setenv("MALTEGO_SERVER_MIDDLEWARE_EXECUTION_TIMEOUT", "300")
        monkeypatch.setenv("MALTEGO_SERVER_NS", "all.env.ns")
        monkeypatch.setenv("MALTEGO_SERVER_AUTHOR", "AllEnvAuthor")
        monkeypatch.setenv("MALTEGO_SERVER_OWNER", "AllEnvOwner")
        monkeypatch.setenv("MALTEGO_SERVER_VERSION", "9.9.9")
        monkeypatch.setenv("MALTEGO_SERVER_ALLOW_REGENERATING_OAUTH_KEYS", "true")
        monkeypatch.setenv("MALTEGO_SERVER_MAX_CONCURRENT_TRANSFORMS_PER_USER", "5")
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_PREFIX", "true")
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_NAME_PREFIX", "env_prefix")
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_APP_NAME_PREFIX", "[EnvApp] ")
        monkeypatch.setenv(
            "MALTEGO_SERVER_TRANSFORM_DISPLAY_NAME_PREFIX", "[EnvDisplay] "
        )
        monkeypatch.setenv("MALTEGO_SERVER_V3_PAGE_SIZE_MAX", "100")
        monkeypatch.setenv("MALTEGO_SERVER_FULL_HOST_URL", "https://env.example.com")
        monkeypatch.setenv("MALTEGO_SERVER_TRUST_FORWARDED_HEADERS", "true")
        monkeypatch.setenv("MALTEGO_SERVER_API_PREFIX", "/env/api")
        monkeypatch.setenv("MALTEGO_SERVER_DISCLAIMER", "https://env.disclaimer.com")
        monkeypatch.setenv("MALTEGO_SERVER_NUM_WORKER", "4")
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_RUNNER", "ASYNC")
        monkeypatch.setenv("MALTEGO_SERVER_SCHEDULED_CLEANUP_SECONDS", "120")
        monkeypatch.setenv("MALTEGO_SERVER_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("MALTEGO_SERVER_REQUIRE_API_KEY", "true")

        settings = MaltegoServerSettings(server_name="CodeServer")

        # Verify ALL values came from env vars
        assert settings.server_name == "AllEnvServer"
        assert settings.transform_execution_timeout == 1800
        assert settings.middleware_execution_timeout == 300
        assert settings.ns == "all.env.ns"
        assert settings.author == "AllEnvAuthor"
        assert settings.owner == "AllEnvOwner"
        assert settings.version == "9.9.9"
        assert settings.allow_regenerating_oauth_keys is True
        assert settings.max_concurrent_transforms_per_user == 5
        assert settings.transform_prefix is True
        assert settings.transform_name_prefix == "env_prefix"
        assert settings.transform_app_name_prefix == "[EnvApp] "
        assert settings.transform_display_name_prefix == "[EnvDisplay] "
        assert settings.v3_page_size_max == 100
        assert settings.full_host_url == "https://env.example.com"
        assert settings.trust_forwarded_headers is True
        assert settings.api_prefix == "/env/api"
        assert settings.disclaimer == "https://env.disclaimer.com"
        assert settings.num_worker == 4
        assert settings.transform_runner == TransformRunnerType.ASYNC
        assert settings.scheduled_cleanup_seconds == 120
        assert settings.log_level == "WARNING"
        assert settings.require_api_key is True

    def test_transform_runner_case_insensitive(self, monkeypatch):
        """Test TRANSFORM_RUNNER is case insensitive"""
        monkeypatch.setenv("MALTEGO_SERVER_TRANSFORM_RUNNER", "async")
        settings = MaltegoServerSettings(server_name="Test")
        assert settings.transform_runner == TransformRunnerType.ASYNC


@pytest.mark.unit
class TestServerHTTPSettingsEmptyValues:
    """Test handling of empty string values from environment variables"""

    def test_empty_string_optional_fields(self, monkeypatch):
        """Test that empty strings for optional fields are converted to None"""
        monkeypatch.setenv("MALTEGO_SERVER_DOMAIN", "")
        monkeypatch.setenv("MALTEGO_SERVER_ROOT_URL", "")
        monkeypatch.setenv("MALTEGO_SERVER_CERT_KEY", "")
        monkeypatch.setenv("MALTEGO_SERVER_CERT_FILE", "")

        http_settings = ServerHTTPSettings()

        assert http_settings.domain is None
        assert http_settings.root_url is None
        assert http_settings.cert_key is None
        assert http_settings.cert_file is None

    def test_empty_string_required_fields(self, monkeypatch):
        """Test that empty strings for required fields use default values"""
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "")
        monkeypatch.setenv("MALTEGO_SERVER_HTTP_PORT", "")
        monkeypatch.setenv("MALTEGO_SERVER_PROTOCOL", "")
        monkeypatch.setenv("MALTEGO_SERVER_FORWARDED_ALLOW_IPS", "")

        http_settings = ServerHTTPSettings()

        assert http_settings.http_addr == "127.0.0.1"  # PRP-8: empty string resolves to loopback default
        assert http_settings.http_port == 3000
        assert http_settings.protocol == "https"
        assert http_settings.forwarded_allow_ips == "127.0.0.1"


@pytest.mark.unit
class TestServerHTTPSettingsCLIArgs:
    """Test CLI argument support for ServerHTTPSettings"""

    def test_all_http_cli_args_work(self, monkeypatch):
        """Comprehensive test that ALL ServerHTTPSettings CLI args work"""
        # Simulate CLI args
        test_args = [
            "test_program",
            "--http-port", "8080",
            "--http-addr", "192.168.1.100",
            "--protocol", "http",
            "--cert-file", "/cli/cert.crt",
            "--cert-key", "/cli/cert.key",
            "--domain", "cli.example.com",
            "--root-url", "https://cli.example.com:8080",
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        http_settings = ServerHTTPSettings()

        assert http_settings.http_port == 8080
        assert http_settings.http_addr == "192.168.1.100"
        assert http_settings.protocol == "http"
        assert http_settings.cert_file == "/cli/cert.crt"
        assert http_settings.cert_key == "/cli/cert.key"
        assert http_settings.domain == "cli.example.com"
        assert http_settings.root_url == "https://cli.example.com:8080"

    def test_http_cli_legacy_args_work(self, monkeypatch):
        """Test legacy CLI arg names still work (--port, --ssl)"""
        test_args = [
            "test_program",
            "--port", "9090",
            "--ssl",  # Legacy: sets protocol to https
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        http_settings = ServerHTTPSettings()

        assert http_settings.http_port == 9090
        assert http_settings.protocol == "https"

    def test_empty_string_via_programmatic(self):
        """Test that empty strings passed programmatically are also handled"""
        http_settings = ServerHTTPSettings(
            domain="",
            root_url="",
            cert_key="",
            cert_file="",
            http_addr="",
            http_port="",
            protocol="",
            forwarded_allow_ips=""
        )

        assert http_settings.domain is None
        assert http_settings.root_url is None
        assert http_settings.cert_key is None
        assert http_settings.cert_file is None
        assert http_settings.http_addr == "127.0.0.1"  # PRP-8: empty string resolves to loopback default
        assert http_settings.http_port == 3000
        assert http_settings.protocol == "https"
        assert http_settings.forwarded_allow_ips == "127.0.0.1"


@pytest.mark.unit
class TestMaltegoServerSettingsCLIArgs:
    """Test CLI argument support for MaltegoServerSettings"""

    def test_all_server_cli_args_work(self, monkeypatch):
        """Comprehensive test that ALL MaltegoServerSettings CLI args work"""
        # Simulate CLI args
        test_args = [
            "test_program",
            "--server-name", "CLIServer",
            "--ns", "cli.namespace",
            "--author", "CLI Author",
            "--owner", "CLI Owner",
            "--version", "2.0.0",
            "--transform-execution-timeout", "7200",
            "--middleware-execution-timeout", "1200",
            "--api-prefix", "/cli/api",
            "--full-host-url", "https://cli.server.com",
            "--transform-prefix",
            "--transform-name-prefix", "cli_",
            "--transform-app-name-prefix", "[CLI] ",
            "--transform-display-name-prefix", "[CLI Display] ",
            "--v3-page-size-max", "200",
            "--max-concurrent-transforms-per-user", "10",
            "--allow-regenerating-oauth-keys",
            "--require-api-key",
            "--log-level", "DEBUG",
            "--num-worker", "8",
            "--transform-runner", "ASYNC",
            "--scheduled-cleanup-seconds", "180",
            "--disclaimer", "https://cli.disclaimer.com",
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        settings = MaltegoServerSettings(server_name="CodeServer")

        # Verify ALL values came from CLI args
        assert settings.server_name == "CLIServer"
        assert settings.ns == "cli.namespace"
        assert settings.author == "CLI Author"
        assert settings.owner == "CLI Owner"
        assert settings.version == "2.0.0"
        assert settings.transform_execution_timeout == 7200
        assert settings.middleware_execution_timeout == 1200
        assert settings.api_prefix == "/cli/api"
        assert settings.full_host_url == "https://cli.server.com"
        assert settings.transform_prefix is True
        assert settings.transform_name_prefix == "cli_"
        assert settings.transform_app_name_prefix == "[CLI] "
        assert settings.transform_display_name_prefix == "[CLI Display] "
        assert settings.v3_page_size_max == 200
        assert settings.max_concurrent_transforms_per_user == 10
        assert settings.allow_regenerating_oauth_keys is True
        assert settings.require_api_key is True
        assert settings.log_level == "DEBUG"
        assert settings.num_worker == 8
        assert settings.transform_runner == TransformRunnerType.ASYNC
        assert settings.scheduled_cleanup_seconds == 180
        assert settings.disclaimer == "https://cli.disclaimer.com"

    def test_v3_protocol_flags_are_not_server_settings(self, monkeypatch):
        monkeypatch.setenv("MALTEGO_SERVER_V3_ENABLED", "false")
        monkeypatch.setenv("MALTEGO_SERVER_V3_DISCOVERY", "false")
        monkeypatch.setattr(
            sys,
            "argv",
            ["test_program", "--no-v3-enabled", "--no-v3-discovery"],
        )

        settings = MaltegoServerSettings(
            server_name="AlwaysV3",
            v3_enabled=False,
            v3_discovery=False,
        )

        assert not hasattr(settings, "v3_enabled")
        assert not hasattr(settings, "v3_discovery")

    def test_env_takes_precedence_over_cli(self, monkeypatch):
        """Test that environment variables take precedence over CLI args"""
        # Set env var
        monkeypatch.setenv("MALTEGO_SERVER_SERVER_NAME", "EnvServer")
        # Set CLI arg
        test_args = ["test_program", "--server-name", "CLIServer"]
        monkeypatch.setattr(sys, "argv", test_args)

        settings = MaltegoServerSettings(server_name="CodeServer")

        # ENV should win over CLI
        assert settings.server_name == "EnvServer"


@pytest.mark.integration
class TestRunServerLogLevelNormalization:
    """Test log level normalization and precedence in run_server"""

    def test_explicit_log_level_is_normalized_without_settings(self, monkeypatch, server_module):
        """Test lowercase explicit log_level is normalized before logging setup"""
        captured = {}

        def fake_get_logging_config(level):
            captured["level"] = level
            return SimpleNamespace(model_dump=lambda: {"level": level})

        monkeypatch.setattr(server_module, "get_logging_config", fake_get_logging_config)
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", lambda *args, **kwargs: None)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda auth_settings: None)

        auth_settings = SimpleNamespace(
            enabled=False,
            mode=SimpleNamespace(value="disabled"),
            provider_type=None,
            provider_url=None,
        )

        # F21: default protocol is 'https'; pass ssl=False to use HTTP so that
        # use_ssl does not raise when no cert files are configured.
        server_module.run_server(log_level="warning", auth_settings=auth_settings, ssl=False)

        assert captured["level"] == "WARNING"

    def test_settings_log_level_wins_and_is_normalized(self, monkeypatch, server_module):
        """Test settings.log_level takes precedence and is normalized"""
        captured = {}

        def fake_get_logging_config(level):
            captured["level"] = level
            return SimpleNamespace(model_dump=lambda: {"level": level})

        monkeypatch.setattr(server_module, "get_logging_config", fake_get_logging_config)
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", lambda *args, **kwargs: None)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda auth_settings: None)

        auth_settings = SimpleNamespace(
            enabled=False,
            mode=SimpleNamespace(value="disabled"),
            provider_type=None,
            provider_url=None,
        )
        # F21: pass explicit protocol='http' via http_settings to avoid the use_ssl
        # ValueError that fires when protocol='https' (default) has no cert files.
        settings = MaltegoServerSettings(
            server_name="Test",
            log_level="warning",
            http_settings=ServerHTTPSettings(protocol="http"),
        )

        server_module.run_server(
            settings=settings,
            log_level="ERROR",
            auth_settings=auth_settings,
        )

        assert captured["level"] == "WARNING"


@pytest.mark.unit
class TestBindDefaultPRP8:
    """PRP-8: startup warning log + run_server host= override still reaches 0.0.0.0"""

    def _make_auth_settings(self):
        return SimpleNamespace(
            enabled=False,
            mode=SimpleNamespace(value="disabled"),
            provider_type=None,
            provider_url=None,
        )

    def test_startup_warning_fires_on_all_interfaces_bind(self, monkeypatch, server_module, caplog):
        """PRP-8: warning log emitted when server binds to 0.0.0.0"""
        captured_host = {}

        def fake_run_server(host, *args, **kwargs):
            captured_host["host"] = host

        monkeypatch.setattr(server_module, "get_logging_config",
                            lambda level: SimpleNamespace(model_dump=lambda: {}))
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", fake_run_server)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda s: None)

        with caplog.at_level(logging.WARNING, logger="maltego.server"):
            server_module.run_server(host="0.0.0.0", ssl=False, auth_settings=self._make_auth_settings())

        assert captured_host["host"] == "0.0.0.0"
        assert "0.0.0.0" in caplog.text
        assert "all interfaces" in caplog.text

    def test_no_startup_warning_on_loopback_bind(self, monkeypatch, server_module, caplog):
        """PRP-8: no all-interfaces warning when binding to 127.0.0.1"""
        monkeypatch.setattr(server_module, "get_logging_config",
                            lambda level: SimpleNamespace(model_dump=lambda: {}))
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", lambda *a, **kw: None)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda s: None)

        with caplog.at_level(logging.WARNING, logger="maltego.server"):
            server_module.run_server(host="127.0.0.1", ssl=False, auth_settings=self._make_auth_settings())

        assert "all interfaces" not in caplog.text

    def test_run_server_host_param_overrides_default(self, monkeypatch, server_module):
        """PRP-8: run_server(host='0.0.0.0') still passes 0.0.0.0 down to _server.run_server"""
        captured_host = {}

        def fake_run_server(host, *args, **kwargs):
            captured_host["host"] = host

        monkeypatch.setattr(server_module, "get_logging_config",
                            lambda level: SimpleNamespace(model_dump=lambda: {}))
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", fake_run_server)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda s: None)

        server_module.run_server(host="0.0.0.0", ssl=False, auth_settings=self._make_auth_settings())

        assert captured_host["host"] == "0.0.0.0"

    def test_settings_http_settings_override_reaches_all_interfaces(self, monkeypatch, server_module):
        """PRP-8: settings.http_settings.http_addr=0.0.0.0 reaches _server.run_server"""
        captured_host = {}

        def fake_run_server(host, *args, **kwargs):
            captured_host["host"] = host

        monkeypatch.setattr(server_module, "get_logging_config",
                            lambda level: SimpleNamespace(model_dump=lambda: {}))
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", fake_run_server)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda s: None)

        settings = MaltegoServerSettings(
            server_name="Test",
            http_settings=ServerHTTPSettings(http_addr="0.0.0.0", protocol="http"),
        )

        server_module.run_server(settings=settings, auth_settings=self._make_auth_settings())

        assert captured_host["host"] == "0.0.0.0"

    def test_env_var_override_reaches_all_interfaces(self, monkeypatch, server_module):
        """PRP-8: MALTEGO_SERVER_HTTP_ADDR=0.0.0.0 env var reaches _server.run_server"""
        captured_host = {}

        def fake_run_server(host, *args, **kwargs):
            captured_host["host"] = host

        monkeypatch.setenv("MALTEGO_SERVER_HTTP_ADDR", "0.0.0.0")
        monkeypatch.setattr(server_module, "get_logging_config",
                            lambda level: SimpleNamespace(model_dump=lambda: {}))
        monkeypatch.setattr(server_module._server, "setup", lambda settings: None)
        monkeypatch.setattr(server_module._server, "run_server", fake_run_server)
        monkeypatch.setattr(server_module, "set_auth_settings", lambda s: None)

        server_module.run_server(ssl=False, auth_settings=self._make_auth_settings())

        assert captured_host["host"] == "0.0.0.0"


class TestF52ConcurrencyCapOptIn:
    """F52: per-user concurrency cap is opt-in — unbounded (None) by default."""

    def test_max_concurrent_transforms_per_user_default_is_unbounded(self):
        settings = MaltegoServerSettings(server_name="test")
        assert settings.max_concurrent_transforms_per_user is None

    def test_max_concurrent_transforms_per_user_can_be_set(self):
        settings = MaltegoServerSettings(
            server_name="test",
            max_concurrent_transforms_per_user=5,
        )
        assert settings.max_concurrent_transforms_per_user == 5
