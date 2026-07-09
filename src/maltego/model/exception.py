# Copyright (c) Maltego Technologies GmbH.
from typing import Optional

from httpx import Response
from pydantic import BaseModel, ConfigDict


class MaltegoTransformProblemDetail(BaseModel):
    """Reusable Maltego Transform RFC 9457 Problem Details response.

    RFC 9457 allows some members to be omitted, but SDK-generated problem
    responses emit the core members consistently. Specific problem types can
    subclass this model and add extension members.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    instance: str


class _ClassicStatusCodeAlias:
    classic_status_code: int

    @property
    def v2_status_code(self) -> int:
        return self.classic_status_code


class MaltegoWarning(_ClassicStatusCodeAlias, Exception):
    classic_status_code = 252

    def __init__(self, message: str = "") -> None:
        super().__init__()
        self.message = message


class MaltegoException(_ClassicStatusCodeAlias, Exception):
    status_code = 400
    classic_status_code = 250

    def __init__(self, message: str = "", code: int = 400, response: Optional[Response] = None) -> None:
        super().__init__()
        self.message = message
        self.code = code
        self.response = response


class MaltegoVersionNotSupported(MaltegoException):
    def __init__(self, detail: str = '', code: int = 400, response: Optional[Response] = None):
        super().__init__(message=detail, code=code, response=response)
        self.detail = detail


class MaltegoTransformTimeoutError(MaltegoException):
    """
    Used for timing out processes in transforms. (ex: prompts).
    """

    def __init__(self, detail: str = '', code: int = 410, response: Optional[Response] = None):
        super().__init__(message=detail, code=code, response=response)
        self.detail = detail

    status_code = 410
    classic_status_code = 246


class MaltegoUnsupportedCapabilityError(MaltegoException):
    """
    Used when a transform uses a capability that has not been
    declared by the transform flags (e.g., composite_entities).
    """

    classic_status_code = 247

    def __init__(self, capability: str, code: int = 400, detail: Optional[str] = None) -> None:
        message = detail or (
            f"Transform attempted to use unsupported capability '{capability}'. "
            f"Declare support for '{capability}' to use it in this transform."
        )
        super().__init__(message=message, code=code)
        self.capability = capability
        self.detail = message


class MaltegoHTTPError(MaltegoException):

    def __init__(self, detail: str = '', code: int = 400, response: Optional[Response] = None):
        super().__init__(message=detail, code=code, response=response)
        self.detail = detail


class MaltegoHTTPClientError(MaltegoHTTPError):
    """Default Maltego HTTP Error for client errors.
    Use this if you don't want the Maltego client to display an ugly error popup"""
    classic_status_code = 240


class MaltegoHTTPNotFound(MaltegoHTTPClientError):
    """
    Base exception for HTTP 404 Not Found errors.
    Used when a requested resource cannot be found.
    """
    status_code = 404
    classic_status_code = 245

    def __init__(self, detail: str = "Resource not found", response: Optional[Response] = None):
        super().__init__(detail=detail, code=self.status_code, response=response)


class MaltegoHTTPTransformNotFound(MaltegoHTTPNotFound):
    """Maltego HTTP error for transform name in request was not found"""
    classic_status_code = 241


class MaltegoHTTPDataProviderNotFound(MaltegoHTTPNotFound):
    """Maltego HTTP error for upstream API endpoint not found"""
    classic_status_code = 254


class MaltegoHTTPInputEntityMalformed(MaltegoHTTPClientError):
    """Maltego HTTP error for malformed input entities"""
    classic_status_code = 242


class MaltegoHTTPLicenseInvalid(MaltegoHTTPClientError):
    """Maltego HTTP error for invalid licenses"""
    classic_status_code = 243


class MaltegoHTTPUnauthorized(MaltegoHTTPClientError):
    """Maltego HTTP error for unauthorized requests"""
    status_code = 401
    classic_status_code = 244


class MaltegoPromptNotSupportedError(MaltegoHTTPClientError):
    """
    Raised when a transform tries to use the prompt capability
    in a context that does not support it (e.g., v2 transform requests).
    """

    status_code = 400
    classic_status_code = 248

    def __init__(self, detail: Optional[str] = None, code: int = 400) -> None:
        message = detail or (
            "Transform attempted to use the prompt capability in an unsupported context "
            "(e.g., v2 transform request)."
        )
        super().__init__(detail=message, code=code)
        self.detail = message


class MaltegoHTTPServerError(MaltegoHTTPError):
    """Default Maltego HTTP Error for server errors.
    Use this if you don't want the Maltego client to display an ugly error popup"""
    status_code = 500
    classic_status_code = 250


class MaltegoNoTransformExecutorError(MaltegoHTTPServerError):
    def __init__(self) -> None:
        super().__init__("No transform executor is available")


class MaltegoHTTPDataProviderUnavailable(MaltegoHTTPServerError):
    """Maltego HTTP error for errors in reaching the data provider"""
    classic_status_code = 251


class MaltegoHTTPDataProviderAPIKeyInvalid(MaltegoHTTPServerError):
    """Maltego HTTP error for invalid upstream API Keys"""
    classic_status_code = 252


class MaltegoHTTPDataProviderInvalidResponse(MaltegoHTTPServerError):
    """Maltego HTTP error for unparsable data providers responses"""
    classic_status_code = 253
