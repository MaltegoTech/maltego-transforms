# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=protected-access
import inspect
import logging
import os
from unittest.mock import AsyncMock, patch

import fastapi
import pytest
from starlette.testclient import TestClient
from maltego.auth import (
    AuthMode,
    AuthProviderType,
    AuthSettings,
    optional_auth,
    reset_auth_settings,
    set_auth_settings,
)
from maltego.auth.problem import build_auth_problem
from maltego.auth.validator import ValidationErrorKind
from maltego.middlewares.user_concurrency_limit_middleware import UserConcurrencyLimitMiddleware
from maltego.model.transform import MaltegoTransform
from maltego.server import MaltegoTransformServer, MaltegoServerSettings
from maltego.server.etag_middleware import ETagMiddleware
from maltego.server.tracing_middleware import TraceparentMiddleware
from maltego.model.server import ServerHTTPSettings
from maltego.protocol.v3.discovery import V3AssetResponse
from maltego.protocol.v3.discovery.capability import V3SupportedCapabilitiesResponse
from maltego.protocol.v3.discovery.status import V3StatusResponse
from maltego.protocol.v3.discovery.transform import V3TransformDefinition, V3Transforms
from maltego.protocol.v3.execution.transform_run import (
    TransformRunResponse,
    TransformRunResultSummary,
)
import maltego.server

from tests.conftest import NAMESPACE, RichEntity, Phrase

pytestmark = pytest.mark.integration


def _v3_url(response):
    return response.json()["TransformApplications"][0]["V3URL"]


def _iter_registered_routes(routes):
    for route in routes:
        yield route
        child_routes = getattr(route, "routes", None)
        if child_routes:
            yield from _iter_registered_routes(child_routes)
            continue
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_registered_routes(original_router.routes)


def _seed_application(response):
    return response.json()["TransformApplications"][0]


def test_example_server(
    mock_server_example: MaltegoTransformServer,
) -> None:
    assert mock_server_example.v2server is None
    assert mock_server_example.v3server


def test_health_endpoint(mock_server: MaltegoTransformServer) -> None:
    client = TestClient(mock_server.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_server_keeps_seed_bridge_without_classic_runner(
    mock_server: MaltegoTransformServer,
) -> None:
    client = TestClient(mock_server.app)

    assert mock_server.v2server is None
    seed_response = client.get("/pytest/seed", headers={"Accept": "application/json"})
    no_protocol_seed_response = client.get("/pytest/seed")
    assert seed_response.status_code == 200
    assert seed_response.json()["TransformApplications"][0]["URL"] == "https://maltoso.com/pytest"
    assert _v3_url(seed_response) == "https://maltoso.com/pytest"
    assert no_protocol_seed_response.status_code == 200
    assert no_protocol_seed_response.headers["content-type"].startswith(
        "application/json"
    )
    assert no_protocol_seed_response.headers["maltego-protocol-version"] == "3.1"
    assert no_protocol_seed_response.json()["TransformApplications"][0]["URL"] == "https://maltoso.com/pytest"
    assert _v3_url(no_protocol_seed_response) == "https://maltoso.com/pytest"
    assert client.get("/pytest/runner?Command=_TRANSFORMS").status_code == 404
    assert client.get("/pytest/runner?Command=_CONFIG").status_code == 404
    status_response = client.get("/pytest/status")
    assert status_response.status_code == 200
    assert status_response.json()["v2TransformCount"] == 0
    assert client.get("/pytest/api/v3/status").status_code == 200
    assert "maltoso.test.TestUnionTypeHint_0" not in (
        mock_server.paired_config.transform_sets["pytest"].transforms
    )


def test_default_server_no_prefix_advertises_and_serves_unversioned_latest_routes() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        full_host_url="https://maltoso.com/",
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        seed_response = client.get("/seed", headers={"Accept": "application/json"})
        assert seed_response.status_code == 200
        assert _v3_url(seed_response) == "https://maltoso.com"

        for route in ("/transforms", "/assets", "/status"):
            assert client.get(route).status_code == 200

        for route in ("/api/v3/transforms", "/api/v3/assets", "/api/v3/status"):
            assert client.get(route).status_code == 200
    finally:
        server.runner.shutdown()


def test_seed_bridge_uses_http_root_url_for_protocol_base_urls() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(root_url="https://api.example.com/base"),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get("/pytest/seed", headers={"Accept": "application/json"})

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "https://api.example.com/base/pytest"
        assert application["V3URL"] == "https://api.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_uses_http_domain_for_protocol_base_urls() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_HTTP_PORT": "443"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            http_settings=ServerHTTPSettings(
                domain="transforms.example.com",
                protocol="https",
            ),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get("/pytest/seed", headers={"Accept": "application/json"})

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "https://transforms.example.com/pytest"
        assert application["V3URL"] == "https://transforms.example.com/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_uses_trusted_forwarded_headers_for_protocol_base_urls() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        trust_forwarded_headers=True,
        http_settings=ServerHTTPSettings(forwarded_allow_ips="*"),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "public.example.com",
            },
        )

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "https://public.example.com/pytest"
        assert application["V3URL"] == "https://public.example.com/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_promotes_full_host_url_protocol_from_trusted_forwarded_headers() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            full_host_url="http://internal.example.com/base",
            trust_forwarded_headers=True,
            http_settings=ServerHTTPSettings(forwarded_allow_ips="*"),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "public.example.com",
            },
        )

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_promotes_root_url_protocol_from_trusted_forwarded_headers() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            trust_forwarded_headers=True,
            http_settings=ServerHTTPSettings(
                root_url="http://internal.example.com/base",
                forwarded_allow_ips="*",
            ),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "public.example.com",
            },
        )

        assert response.status_code == 200
        application = _seed_application(response)
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_promotes_full_host_url_protocol_from_https_server_protocol() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        full_host_url="http://internal.example.com/base",
        http_settings=ServerHTTPSettings(protocol="https"),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get("/pytest/seed", headers={"Accept": "application/json"})

        assert response.status_code == 200
        application = _seed_application(response)
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_promotes_root_url_protocol_from_https_server_protocol() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            root_url="http://internal.example.com/base",
            protocol="https",
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get("/pytest/seed", headers={"Accept": "application/json"})

        assert response.status_code == 200
        application = _seed_application(response)
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_keeps_http_full_host_url_for_http_server_without_trusted_https() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            full_host_url="http://internal.example.com/base",
            http_settings=ServerHTTPSettings(),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get("/pytest/seed", headers={"Accept": "application/json"})

        assert response.status_code == 200
        application = _seed_application(response)
        assert application["URL"] == "http://internal.example.com/base/pytest"
        assert application["V3URL"] == "http://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_does_not_promote_full_host_url_protocol_from_untrusted_forwarded_headers() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            full_host_url="http://internal.example.com/base",
            trust_forwarded_headers=True,
            http_settings=ServerHTTPSettings(
                forwarded_allow_ips="10.0.0.1",
            ),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "public.example.com",
            },
        )

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "http://internal.example.com/base/pytest"
        assert application["V3URL"] == "http://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_does_not_downgrade_root_url_protocol_from_forwarded_headers() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            trust_forwarded_headers=True,
            http_settings=ServerHTTPSettings(
                root_url="https://internal.example.com/base",
                forwarded_allow_ips="*",
            ),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "http",
            },
        )

        assert response.status_code == 200
        application = _seed_application(response)
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_seed_bridge_does_not_downgrade_full_host_url_protocol_from_forwarded_headers() -> None:
    with patch.dict(os.environ, {"MALTEGO_SERVER_PROTOCOL": "http"}):
        settings = MaltegoServerSettings(
            server_name=NAMESPACE,
            ns=NAMESPACE,
            author=NAMESPACE,
            api_prefix="pytest",
            full_host_url="https://internal.example.com/base",
            trust_forwarded_headers=True,
            http_settings=ServerHTTPSettings(forwarded_allow_ips="*"),
        )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    try:
        response = client.get(
            "/pytest/seed",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Proto": "http",
            },
        )

        assert response.status_code == 200
        application = response.json()["TransformApplications"][0]
        assert application["URL"] == "https://internal.example.com/base/pytest"
        assert application["V3URL"] == "https://internal.example.com/base/pytest"
    finally:
        server.runner.shutdown()


def test_concat_server_includes_protocol_extension_routers() -> None:
    main_settings = MaltegoServerSettings(
        server_name="main",
        ns="main",
        author="maltoso",
    )
    other_settings = MaltegoServerSettings(
        server_name="extra",
        ns="extra",
        author="maltoso",
        api_prefix="extra",
    )
    main_server = MaltegoTransformServer(settings=main_settings)
    other_server = MaltegoTransformServer(settings=other_settings)
    extension_router = fastapi.APIRouter()

    @extension_router.get("/extra/extension")
    async def extension_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    other_server.setup(other_settings)
    other_server.add_protocol_router(extension_router)
    main_server.setup(main_settings)
    main_server.concat_server(other_server)

    client = TestClient(main_server.app)
    try:
        assert client.get("/extra/transforms").status_code == 200
        response = client.get("/extra/extension")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        main_server.runner.shutdown()
        other_server.runner.shutdown()


def test_settings_env() -> None:
    os.environ["api_prefix"] = "environ"
    mock_server_settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        full_host_url="https://maltoso.com/",
    )
    mock_server = MaltegoTransformServer(
        settings=mock_server_settings
    )

    mock_server.setup(mock_server_settings)
    assert mock_server._settings.api_prefix == "environ"
    del os.environ["api_prefix"]
    mock_server.runner.shutdown()


def test_allow_regenerating_oauth_keys_setting(mock_server: MaltegoTransformServer) -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author="maltoso",
        allow_regenerating_oauth_keys=True,
    )
    mock_server.set_settings(settings)
    mock_server.setup(settings)


def test_max_concurrent_transforms_per_user_setting(mock_server: MaltegoTransformServer) -> None:
    # The cap is opt-in: with no value configured the limiter middleware is not
    # installed; configuring a value adds it at the front of the chain.
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        author="maltoso",
        max_concurrent_transforms_per_user=1
    )
    assert len(mock_server.runner.middlewares) == 1
    mock_server.set_settings(settings)
    mock_server.setup(settings)
    assert len(mock_server.runner.middlewares) == 2
    assert isinstance(
        mock_server.runner.middlewares[0], UserConcurrencyLimitMiddleware)


def test_transform_prefix_setting(mock_server: MaltegoTransformServer) -> None:
    assert mock_server.v3server
    original_transform = mock_server.v3server.transforms.get(
        f'{NAMESPACE}.Test')

    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author="maltoso",
        transform_prefix=True,
        transform_name_prefix="foo",
        transform_app_name_prefix="bar",
        transform_display_name_prefix="baz"
    )
    mock_server.set_settings(settings)
    mock_server.setup(settings)

    assert mock_server.v3server
    transform = mock_server.v3server.transforms.get(f'{NAMESPACE}.Test')
    new = mock_server.v3server.transforms.get(f'foo.{NAMESPACE}.Test')
    assert isinstance(new, MaltegoTransform)
    assert isinstance(original_transform, MaltegoTransform)
    assert transform is None


def test_transform_registration(mock_server: MaltegoTransformServer) -> None:
    assert mock_server.v3server
    available_transforms = mock_server.v3server.transforms.items()
    assert len(available_transforms) == 13
    for name, transform in available_transforms:
        in_types = transform.annotation.input.get_entities_type_ids()
        assert len(in_types) >= 1 and (
            "maltego.Phrase" in in_types or "maltego.Person" in in_types)
        if name == "dummy_transform_1_args":
            assert transform.annotation.output.get_entities_type_ids() == [
                "maltego.Person"]


def test_apply_settings(mock_server: MaltegoTransformServer, mock_server_settings_reverse: MaltegoServerSettings) -> None:
    # Check Original Namespace
    assert mock_server._settings.ns == 'maltoso.test'
    mock_server.set_settings(mock_server_settings_reverse)
    # Check modified Namespace
    assert mock_server._settings.ns == 'osotlam'


def test_register_transform(mock_server: MaltegoTransformServer) -> None:
    assert mock_server.v3server
    assert len(mock_server.v3server.transforms) == 13

    transform: MaltegoTransform = mock_server.v3server.transforms['maltoso.test.Test']
    assert transform.name == "Test"
    assert transform.annotation.input.get_entities_type_ids() == [
        "maltego.Phrase"]
    assert transform.annotation.output.get_entities_type_ids() == [
        "maltego.Phrase"]


def test_register_entity(mock_server: MaltegoTransformServer) -> None:
    entities = mock_server.paired_config.entities
    assert len(entities) == 2
    assert issubclass(list(entities.values())[0], Phrase)


def test_every_type_instantiation_and_registration(mock_server: MaltegoTransformServer) -> None:
    assert RichEntity in mock_server.paired_config.entities.values()


def test_cors_preflight_disabled_by_default(mock_server: MaltegoTransformServer) -> None:
    client = TestClient(mock_server.app)
    response = client.options(
        "/pytest/seed",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None
    assert response.headers.get("access-control-allow-credentials") is None


def test_auth_problem_exception_handler_returns_direct_problem_details() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
    )
    server = MaltegoTransformServer(settings=settings)

    @server.app.get("/protected")
    async def protected_route():
        raise build_auth_problem(
            ValidationErrorKind.EXPIRED_TOKEN,
            "raw validator message",
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="oidc",
                provider_url="https://id.example/realms/customer",
            ),
            None,
        )

    client = TestClient(server.app)
    response = client.get(
        "/protected",
        headers={"Accept": "application/json, application/problem+json"},
    )
    server.runner.shutdown()

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "urn:maltego-transforms:problem:auth:token-expired",
        "title": "Authentication token expired",
        "status": 401,
        "detail": "The authentication token has expired. Obtain a fresh SSO credential and retry the request.",
        "instance": "",
        "error_code": "auth.token_expired",
        "auth_origin": "sso",
        "provider_type": "oidc",
        "reason": "expired",
        "refresh_required": True,
        "retryable": False,
    }


def test_auth_problem_exception_handler_returns_problem_details_without_problem_accept() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
    )
    server = MaltegoTransformServer(settings=settings)

    @server.app.get("/protected")
    async def protected_route():
        raise build_auth_problem(
            ValidationErrorKind.EXPIRED_TOKEN,
            "raw validator message",
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="oidc",
                provider_url="https://id.example/realms/customer",
            ),
            None,
        )

    client = TestClient(server.app)
    response = client.get("/protected", headers={"Accept": "application/json"})
    server.runner.shutdown()

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:maltego-transforms:problem:auth:token-expired"
    assert response.json()["error_code"] == "auth.token_expired"


def test_auth_dependency_unexpected_validator_error_returns_problem_details() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
    )
    server = MaltegoTransformServer(settings=settings)

    @server.app.get("/protected")
    async def protected_route(_=fastapi.Depends(optional_auth)):
        return {"ok": True}

    mock_validator = AsyncMock()
    mock_validator.validate_token.side_effect = RuntimeError("validator internals")
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        )
    )

    client = TestClient(server.app)
    try:
        with patch("maltego.auth.dependency._get_validator", return_value=mock_validator):
            response = client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer some-token",
                    # SSO-origin bearer tokens require an upstream-identity-method
                    # header; without it the request is rejected before the
                    # validator runs, so the unexpected-error path is never reached.
                    "maltego-upstream-identity-method": "oidc",
                    "Accept": "application/json",
                },
            )
    finally:
        server.runner.shutdown()
        reset_auth_settings()

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:maltego-transforms:problem:auth:internal-error"
    assert response.json()["error_code"] == "auth.internal_error"
    assert "validator internals" not in response.json()["detail"]


def test_auth_protects_json_discovery_endpoints() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        )
    )

    client = TestClient(server.app)
    try:
        responses = [
            client.get("/pytest/seed", headers={"Accept": "application/json"}),
            client.get("/pytest/transforms", headers={"Accept": "application/json"}),
            client.get("/pytest/status", headers={"Accept": "application/json"}),
            client.get("/pytest/api/v3/status", headers={"Accept": "application/json"}),
        ]
        classic_runner_response = client.get(
            "/pytest/runner?Command=_TRANSFORMS",
            headers={"Accept": "application/json"},
        )
    finally:
        server.runner.shutdown()
        reset_auth_settings()

    assert classic_runner_response.status_code == 404
    for response in responses:
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["type"] == "urn:maltego-transforms:problem:auth:credentials-missing"
        assert response.json()["error_code"] == "auth.credentials_missing"


def test_cors_preflight_allowed_origin() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(cors_allowed_origins=["https://app.example.com"]),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)
    response = client.options(
        "/pytest/seed",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_allowed_origin_with_auth_enabled() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(cors_allowed_origins=["https://app.example.com"]),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        )
    )
    client = TestClient(server.app)
    try:
        response = client.options(
            "/pytest/seed",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    finally:
        server.runner.shutdown()
        reset_auth_settings()

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_rejects_unknown_origin() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(cors_allowed_origins=["https://app.example.com"]),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)
    response = client.options(
        "/pytest/seed",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    server.runner.shutdown()
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_allowed_by_regex() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(cors_allowed_origin_regex=r"^https://.*\.example\.com$"),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)
    response = client.options(
        "/pytest/seed",
        headers={
            "Origin": "https://tenant.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://tenant.example.com"


def test_cors_middleware_setup_is_idempotent() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        http_settings=ServerHTTPSettings(cors_allowed_origins=["https://app.example.com"]),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    server.setup(settings)
    cors_middleware_count = sum(
        1 for middleware in server.app.user_middleware if middleware.cls.__name__ == "CORSMiddleware"
    )
    server.runner.shutdown()
    assert cors_middleware_count == 1


def test_response_compression_disabled_by_default(
    mock_server: MaltegoTransformServer,
) -> None:
    client = TestClient(mock_server.app)

    response = client.get(
        "/pytest/transforms",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None
    assert response.headers["maltego-protocol-version"] == "3.1"
    assert response.headers["maltego-transform-supported-oauth-formats"] == "jwe"


def test_response_compression_gzips_large_json_when_enabled() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=1,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    response = client.get(
        "/pytest/transforms",
        headers={"Accept-Encoding": "gzip"},
    )

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in response.headers.get("vary", "").lower()
    assert response.headers["maltego-protocol-version"] == "3.1"
    assert response.headers["maltego-transform-supported-oauth-formats"] == "jwe"


def test_response_compression_preserves_cors_headers_when_enabled() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            cors_allowed_origins=["https://app.example.com"],
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=1,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    response = client.get(
        "/pytest/transforms",
        headers={
            "Accept-Encoding": "gzip",
            "Origin": "https://app.example.com",
        },
    )

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert "accept-encoding" in response.headers.get("vary", "").lower()
    assert "origin" in response.headers.get("vary", "").lower()


def test_response_compression_respects_accept_encoding_identity() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=1,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    response = client.get(
        "/pytest/transforms",
        headers={"Accept-Encoding": "identity"},
    )

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None
    assert response.headers["maltego-protocol-version"] == "3.1"
    assert response.headers["maltego-transform-supported-oauth-formats"] == "jwe"


def test_response_compression_does_not_compress_without_accept_encoding_header() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=1,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)
    request = client.build_request("GET", "/pytest/transforms")
    request.headers.pop("accept-encoding", None)

    response = client.send(request)

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None
    assert response.headers["maltego-protocol-version"] == "3.1"
    assert response.headers["maltego-transform-supported-oauth-formats"] == "jwe"


def test_response_compression_preserves_etag_in_run_server_middleware_stack() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=1,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    server.app.add_middleware(TraceparentMiddleware)
    server.app.add_middleware(ETagMiddleware)
    client = TestClient(server.app)

    response = client.get(
        "/pytest/transforms",
        headers={"Accept-Encoding": "gzip"},
    )

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.headers.get("etag") is not None
    assert "accept-encoding" in response.headers.get("vary", "").lower()


def test_response_compression_respects_minimum_size() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix="pytest",
        http_settings=ServerHTTPSettings(
            http_response_compression_enabled=True,
            http_response_compression_minimum_size=500,
        ),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    response = client.get(
        "/health",
        headers={"Accept-Encoding": "gzip"},
    )

    server.runner.shutdown()
    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None


def test_response_compression_setup_is_idempotent() -> None:
    settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        http_settings=ServerHTTPSettings(http_response_compression_enabled=True),
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    server.setup(settings)

    gzip_middleware_count = sum(
        1 for middleware in server.app.user_middleware if middleware.cls.__name__ == "GZipMiddleware"
    )

    server.runner.shutdown()
    assert gzip_middleware_count == 1


def test_openapi_spec_endpoint(mock_server: MaltegoTransformServer) -> None:
    client = TestClient(mock_server.app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"].startswith("3.")
    assert "/pytest/seed" in payload["paths"]
    assert "/pytest/transforms" in payload["paths"]
    assert "/pytest/assets" in payload["paths"]
    assert "/pytest/status" in payload["paths"]
    assert "/pytest/api/v3/transforms" not in payload["paths"]
    assert "/pytest/api/v3/assets" not in payload["paths"]
    assert "/pytest/api/v3/status" not in payload["paths"]


def test_swagger_endpoint(mock_server: MaltegoTransformServer) -> None:
    client = TestClient(mock_server.app)
    response = client.get("/swagger")

    assert response.status_code == 200
    assert "Swagger UI" in response.text
    assert "/openapi.json" in response.text
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_swagger_disabled_returns_404(mock_server: MaltegoTransformServer) -> None:
    settings = MaltegoServerSettings(
        server_name=mock_server._settings.server_name,
        ns=mock_server._settings.ns,
        swagger_enabled=False,
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app)

    assert client.get("/swagger").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404

    server.runner.shutdown()


def test_swagger_and_openapi_require_auth_when_auth_enabled() -> None:
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
        )
    )
    settings = MaltegoServerSettings(server_name="Test", ns="test", swagger_enabled=True)
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    client = TestClient(server.app, raise_server_exceptions=False)

    # Both endpoints must reject unauthenticated requests
    assert client.get("/swagger").status_code == 401
    assert client.get("/openapi.json").status_code == 401

    server.runner.shutdown()
    reset_auth_settings()


def test_registered_route_urls_include_advertised_app_endpoints(mock_server: MaltegoTransformServer) -> None:
    @mock_server.app.get("/custom/api/v3/diagnostics")
    async def custom_route_with_api_v3_segments() -> dict[str, str]:
        return {"status": "ok"}

    route_urls = mock_server.get_registered_route_urls("http", "0.0.0.0", 3000)

    assert "GET http://127.0.0.1:3000/health" in route_urls
    assert "GET http://127.0.0.1:3000/pytest/seed" in route_urls
    assert "GET http://127.0.0.1:3000/custom/api/v3/diagnostics" in route_urls
    assert (
        "POST http://127.0.0.1:3000/pytest/transforms/{transform_id}/run"
        in route_urls
    )
    assert (
        "POST http://127.0.0.1:3000/pytest/api/v3/transforms/{transform_id}/run"
        not in route_urls
    )
    assert "GET http://127.0.0.1:3000/openapi.json" in route_urls
    assert "GET http://127.0.0.1:3000/swagger" in route_urls
    assert "GET http://127.0.0.1:3000/docs" not in route_urls
    assert "GET http://127.0.0.1:3000/redoc" not in route_urls


def test_registered_route_urls_hide_swagger_routes_when_disabled() -> None:
    settings = MaltegoServerSettings(
        server_name="Test Server",
        ns="test",
        swagger_enabled=False,
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)

    route_urls = server.get_registered_route_urls("http", "0.0.0.0", 3000)

    assert "GET http://127.0.0.1:3000/openapi.json" not in route_urls
    assert "GET http://127.0.0.1:3000/swagger" not in route_urls
    assert "GET http://127.0.0.1:3000/docs" not in route_urls
    assert "GET http://127.0.0.1:3000/redoc" not in route_urls

    server.runner.shutdown()


def test_startup_logs_seed_url_configuration_once(monkeypatch, caplog) -> None:
    class FakeUvicornServer:
        def __init__(self, config):
            self.config = config

        async def serve(self):
            return None

    settings = MaltegoServerSettings(
        server_name="Test Server",
        ns="test",
        author="test@example.com",
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    monkeypatch.setattr(maltego.server.uvicorn, "Server", FakeUvicornServer)

    try:
        with caplog.at_level(logging.INFO, logger="maltego.server"):
            server.run_server("127.0.0.1", 3000, ssl=False)
    finally:
        server.runner.shutdown()

    startup_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "maltego.server"
    ]
    assert startup_messages.count(
        "Seed URL configuration: full_host_url=None trust_forwarded_headers=False"
    ) == 1
    assert "TRUST_FORWARDED_HEADERS=False" not in startup_messages


def test_v3_json_routes_keep_pydantic_return_annotations(
    mock_server: MaltegoTransformServer,
) -> None:
    expected = {
        ("GET", "/pytest/assets"): V3AssetResponse,
        ("GET", "/pytest/transforms"): V3Transforms,
        ("GET", "/pytest/transforms/{transform_id}"): V3TransformDefinition,
        ("POST", "/pytest/transforms/{transform_id}/run"): TransformRunResponse,
        ("DELETE", "/pytest/transforms/{transform_id}/run/{run_id}"): TransformRunResultSummary,
        ("GET", "/pytest/transforms/{transform_id}/run/{run_id}/status"): TransformRunResponse,
        ("GET", "/pytest/transforms/{transform_id}/run/{run_id}/results"): TransformRunResponse,
        ("GET", "/pytest/status"): V3StatusResponse,
        ("GET", "/pytest/.well-known/supported_capabilities"): V3SupportedCapabilitiesResponse,
    }
    routes_by_method_path = {
        (method, route.path): route
        for route in _iter_registered_routes(mock_server.app.routes)
        for method in (getattr(route, "methods", None) or set())
        if method != "HEAD"
    }

    assert set(expected).issubset(routes_by_method_path)
    for route_key, return_type in expected.items():
        endpoint = routes_by_method_path[route_key].endpoint
        annotation = inspect.signature(endpoint).return_annotation
        assert annotation is return_type
        assert annotation is not fastapi.Response
        assert routes_by_method_path[route_key].response_model is not None


def test_uvicorn_config_does_not_apply_proxy_headers_directly() -> None:
    settings = MaltegoServerSettings(
        server_name="Test Server",
        ns="test",
        author="test@example.com",
        trust_forwarded_headers=True,
        http_settings=ServerHTTPSettings(forwarded_allow_ips="10.0.0.1"),
    )
    server = MaltegoTransformServer(settings)

    config = server._MaltegoTransformServer__get_config(  # pylint: disable=protected-access
        ssl=False,
        ssl_cert_file=None,
        ssl_key_file=None,
        host="127.0.0.1",
        port=3000,
    )

    assert config.proxy_headers is False
