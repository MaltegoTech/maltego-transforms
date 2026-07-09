# Ensure transforms are discovered
from transforms.quickstart_example import *  # Core examples + entity definitions
from transforms.error_handling_example import *
from transforms.input_constraints_example import *
from transforms.logging_example import *
from transforms.pagination_example import *
from transforms.prompts_example import *
from transforms.entity_features_example import *
from transforms.transform_settings_example import *  # All 13 setting types reference
from transforms.middleware_example import *  # Decoupled authorization/audit middleware

from maltego.server import MaltegoServerSettings, ServerHTTPSettings, run_server

if __name__ == "__main__":
    settings = MaltegoServerSettings(
        server_name="New Maltego Integration",
        ns="acme.new_maltego_integration",  # choose acme.* here
        author="Acme Corp",
        http_settings=ServerHTTPSettings(
            protocol="http",
            cors_allowed_origins=["https://app.maltego.com"]
        ),
    )

    run_server(
        settings=settings,
        # PolicyChecker/AuditWriter are inert by default (allow everyone, log
        # nothing). Swap them for real adapters (OPA, Kafka, ...) without
        # touching the middlewares or transforms. See middleware_example.py.
        transform_middlewares=[
            AuthorizationMiddleware(PolicyChecker()),
            AuditMiddleware(AuditWriter()),
        ],
    )
