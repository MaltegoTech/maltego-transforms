# Copyright (c) Maltego Technologies GmbH.
"""
Maltego authentication module.

Provides optional JWT/OIDC authentication for Maltego transform servers.
"""

from maltego.auth.dependency import close_validator, optional_auth, optional_bearer
from maltego.auth.identity import AuthContext, Identity
from maltego.auth.jwt_validator import JWTTokenValidator
from maltego.auth.oidc_validator import OIDCTokenValidator
from maltego.auth.saml_validator import SAMLTokenValidator
from maltego.auth.settings import (
    AuthMode,
    AuthProviderType,
    AuthTokenOrigin,
    AuthSettings,
    get_auth_settings,
    set_auth_settings,
    reset_auth_settings,
)
from maltego.auth.validator import AuthValidationFailure, AuthValidationSuccess, TokenValidator, ValidationErrorKind
from maltego.auth.problem import MaltegoAuthErrorCode, MaltegoAuthProblemDetail, AuthProblemException

__all__ = [
    # Dependencies
    "optional_auth",
    "optional_bearer",
    "close_validator",
    # Settings
    "AuthMode",
    "AuthProviderType",
    "AuthTokenOrigin",
    "AuthSettings",
    "get_auth_settings",
    "set_auth_settings",
    "reset_auth_settings",
    # Validation
    "AuthValidationFailure",
    "AuthValidationSuccess",
    "JWTTokenValidator",
    "SAMLTokenValidator",
    "TokenValidator",
    "OIDCTokenValidator",
    "ValidationErrorKind",
    "MaltegoAuthErrorCode",
    "MaltegoAuthProblemDetail",
    "AuthProblemException",
    "AuthContext",
    "Identity",
]
