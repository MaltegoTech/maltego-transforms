"""
Decoupling authorization, auditing, and logging from transform business logic.

Where this sits in the request chain (outermost first):

1. Your reverse proxy / gateway / load balancer -- TLS termination, mTLS,
   WAF rules, rate limiting, and malformed-request rejection all happen here,
   before a request ever reaches this process. See the "Deployment" article.
2. ASGI/Starlette middleware (CORS preflight, tracing) and FastAPI routing.
3. The SDK's authentication layer (``AuthSettings``, configured below) --
   runs as a FastAPI route dependency *before* any transform is scheduled.
   By the time step 4 runs, ``context.identity`` and ``context.auth_claims``
   are already populated, or the request has already been rejected with
   401/403 and none of this file's code has run at all.
4. ``TransformMiddleware.before_transform`` / ``after_transform`` (this
   file) -- runs around the transform, once a caller is already
   authenticated. This is the right layer for per-transform authorization,
   audit trails, and end-of-run logging, because it has access to the
   transform, its input, and the identity resolved in step 3.
5. The transform function itself.

Keep the middlewares thin. Each one delegates to a small adapter class built
once at startup; swapping OPA/Kafka/whatever for something else later means
changing the adapter, not the middleware or the transforms.

Two things worth knowing before you copy this pattern:

- The generated project wires these middlewares into ``project.py``'s shared
  ``run_server()`` call, so they run for every registered transform, not
  just ``identity_echo_demo``.
- ``TransformMiddleware`` instances run in the order passed to
  ``transform_middlewares``, after the SDK's own built-in middlewares
  (``VerifyMetadataMiddleware`` and, if configured, ``OAuthMiddleware`` /
  ``UserConcurrencyLimitMiddleware``). If an earlier middleware's
  ``before_transform`` raises, later ones in the list -- including
  ``AuthorizationMiddleware`` here -- never run for that request.
"""

from typing import Any, Dict, List, Optional, Sequence, Union

from maltego.entities import Phrase
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.exception import MaltegoException
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.types import ExecutionState, MaltegoSettingTypes
from maltego.server import register_transform

TRANSFORM_SET = "New Maltego Integration"


class PolicyChecker:
    """
    Authorization adapter. Swap this for a client backed by OPA, your RBAC
    service, or anything else -- the middleware below never changes.
    """

    async def allowed(self, *, identity: Optional[Any], claims: Optional[Dict[str, Any]]) -> bool:
        # Default: allow everyone. Replace with a real policy check, e.g.
        # `return "transform-runner" in (claims or {}).get("groups", [])`.
        return True


class AuditWriter:
    """
    Audit sink adapter. Swap this for Kafka, Splunk, a database, etc. --
    the middleware below only depends on this interface.
    """

    async def record(self, *, identity: Optional[Any], transform_name: str, outcome: str) -> None:
        # Default: no-op. Replace with a call to your audit pipeline.
        pass


class AuthorizationMiddleware(TransformMiddleware):
    """
    Runs after authentication has already validated the caller. Denies here
    are business/policy decisions (can this identity run this transform),
    not identity checks (is this token valid) -- those belong in
    ``AuthSettings``, not here.
    """

    def __init__(self, policy: PolicyChecker) -> None:
        self.policy = policy

    async def before_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        properties: Dict[str, MaltegoSettingTypes],
        context: MaltegoContext,
        soft_limit: int,
        hard_limit: int,
    ) -> None:
        allowed = await self.policy.allowed(
            identity=context.identity,
            claims=context.auth_claims,
        )
        if not allowed:
            raise MaltegoException("Not authorised to run this transform")

    async def after_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        output_entities: List[MaltegoEntity],
        context: MaltegoContext,
        state: ExecutionState,
        exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        pass


class AuditMiddleware(TransformMiddleware):
    """
    Records an audit entry and a completion log line for every run,
    including failed ones (``call_on_failure = True``), so the audit trail
    reflects denials and errors, not just successes.
    """

    call_on_failure = True

    def __init__(self, audit: AuditWriter) -> None:
        self.audit = audit

    async def before_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        properties: Dict[str, MaltegoSettingTypes],
        context: MaltegoContext,
        soft_limit: int,
        hard_limit: int,
    ) -> None:
        pass

    async def after_transform(
        self,
        transform: MaltegoTransform,
        transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
        output_entities: List[MaltegoEntity],
        context: MaltegoContext,
        state: ExecutionState,
        exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        context.log.inform(f"{transform.display_name} finished with state {state}")
        await self.audit.record(
            identity=context.identity,
            transform_name=transform.display_name,
            outcome=state.value,
        )


@register_transform(
    display_name="Identity Echo [New Maltego Integration]",
    description="Shows the identity resolved by AuthSettings before this transform ran",
    transform_set=TRANSFORM_SET,
)
async def identity_echo_demo(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    """
    Reads ``context.identity``, which is only present because authentication
    already ran (as a route dependency) before this transform -- and before
    AuthorizationMiddleware/AuditMiddleware above -- were ever invoked. When
    run standalone (this file's own ``__main__`` block, below), auth is
    explicitly disabled, so ``context.identity`` is ``None`` here. When run
    via the generated project's ``project.py``, no ``auth_settings`` is
    passed explicitly, so the effective value comes from ``AuthSettings``'
    own defaults/environment instead (loaded via ``get_auth_settings()``).
    """
    if context.identity:
        return Phrase(f"Authenticated as: {context.identity.sub}")
    return Phrase("No identity: AuthSettings.enabled is False")


if __name__ == "__main__":
    from maltego.server import AuthMode, AuthSettings, MaltegoServerSettings, run_server

    server_settings = MaltegoServerSettings(
        server_name="Maltego Transform Server", ns="acme", author="Acme"
    )
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=False,
        settings=server_settings,
        log_level="INFO",
        # Disabled by default so this file runs standalone without a real
        # identity provider. Point provider_url at your OIDC/JWT/SAML
        # provider (e.g. Keycloak) to see identity_echo_demo populate.
        auth_settings=AuthSettings(enabled=False, mode=AuthMode.STRICT),
        transform_middlewares=[
            AuthorizationMiddleware(PolicyChecker()),
            AuditMiddleware(AuditWriter()),
        ],
    )
