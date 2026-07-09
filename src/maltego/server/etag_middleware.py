import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ETagMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds an ETag header based on a random value generated at server startup.

    This is intentionally not content-based, the ETag is fixed for the lifetime
    of the server process and is only used to detect restarts for cache invalidation.
    """

    def __init__(self, app):
        super().__init__(app)
        self.etag = os.urandom(16).hex()

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["ETag"] = self.etag
        return response
