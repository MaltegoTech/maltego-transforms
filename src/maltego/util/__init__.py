# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Awaitable, Dict, List, Optional, Tuple, Union, Callable
import asyncio
from asyncio.tasks import Task
import logging
from contextlib import suppress
from urllib.parse import urlparse
import inspect
import httpx
from httpx import Response, Headers
from httpx._types import ProxyTypes
from maltego.model.exception import (MaltegoException,
                                     MaltegoHTTPDataProviderAPIKeyInvalid,
                                     MaltegoHTTPDataProviderNotFound,
                                     MaltegoHTTPDataProviderUnavailable,
                                     MaltegoHTTPUnauthorized
                                     )
from maltego.model.context import MaltegoContext


log = logging.getLogger(__name__)
SemKeyType = Union[str, Tuple[Optional[str], Optional[str]]]


class Throttler:
    def __init__(
            self,
            max_concurrent_per_key: int,
            global_max_concurrent: int = 10000,
            user_concurrency_overrides: Optional[Dict[Optional[SemKeyType], int]] = None,
    ):
        if max_concurrent_per_key >= global_max_concurrent:
            log.warning(
                f"It's recommended that max_concurrent_per_key (={max_concurrent_per_key}) "
                f"be strictly smaller than global_max_concurrent (={global_max_concurrent})."
                f"An individual user's requests may block all other users."
            )
        self.semaphores_by_owner: Dict[Optional[SemKeyType], asyncio.BoundedSemaphore] = {}
        self._in_flight_by_owner: Dict[Optional[SemKeyType], int] = {}
        self.max_concurrent_per_key = max_concurrent_per_key
        self.global_max_concurrent = global_max_concurrent
        self.user_concurrency_overrides = {
        } if user_concurrency_overrides is None else user_concurrency_overrides
        # global limiter that balances between users
        self.global_sem: Optional[asyncio.BoundedSemaphore] = None

    async def _execute_for_owner(self, awaitable: Awaitable[Response], owner: SemKeyType) -> Response:
        # The order of semaphores matters! The per-key semaphore must be acquired first,
        # otherwise the user hogs the global semaphore
        if self.global_sem is None:
            self.global_sem = asyncio.BoundedSemaphore(self.global_max_concurrent)
        log.debug(f" (throttling) Trying to acquire semaphores for {owner}")
        owner_sem = await self._get_or_create_semaphore(owner)
        self._in_flight_by_owner[owner] = self._in_flight_by_owner.get(owner, 0) + 1
        res: Optional[Response] = None
        try:
            async with owner_sem:
                log.debug(f"Owner Semaphore Acquired, running awaitable for {owner}")
                async with self.global_sem:
                    log.debug(f"Global Semaphore Acquired, running awaitable for {owner}")
                    res = await awaitable
        finally:
            self._in_flight_by_owner[owner] -= 1
            if self._in_flight_by_owner[owner] == 0:
                self.semaphores_by_owner.pop(owner, None)
                self._in_flight_by_owner.pop(owner, None)
        return res

    async def _get_or_create_semaphore(self, owner: SemKeyType) -> asyncio.BoundedSemaphore:
        sem = self.semaphores_by_owner.get(owner, None)
        if sem is None:
            concurrency = self.user_concurrency_overrides.get(owner, self.max_concurrent_per_key)
            log.debug(f"Creating new bounded semaphore for {owner}, max concurrency: {concurrency}.")
            sem = asyncio.BoundedSemaphore(concurrency)
            self.semaphores_by_owner[owner] = sem
        return sem

    async def execute_throttled(
        self,
        awaitable: Awaitable[Response],
        on_behalf_of_key: SemKeyType
    ) -> Response:
        return await self._execute_for_owner(awaitable, on_behalf_of_key)


class AsyncLeakyBucket:

    def __init__(self, max_tasks: int, time_period: float = 60):
        self._delay_time = time_period
        self.max_tasks = max_tasks
        self._sem: Optional[asyncio.BoundedSemaphore] = None
        self._leak_started = False
        self._leak_task: Optional[Task[Any]] = None

    async def _leak_sem(self) -> None:
        """
        Background task that leaks semaphore releases based on the desired rate of tasks per time_period
        """
        if self._sem is None:
            self._sem = asyncio.BoundedSemaphore(self.max_tasks)
        await asyncio.sleep(self._delay_time)
        for _ in range(self.max_tasks):
            try:
                self._sem.release()
            except ValueError:
                pass
        self._leak_started = False

    async def __aenter__(self) -> None:
        if self._sem is None:
            self._sem = asyncio.BoundedSemaphore(self.max_tasks)
        await self._sem.acquire()
        if not self._leak_started:
            self._leak_started = True
            self._leak_task = asyncio.create_task(self._leak_sem())

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Not relevant since new semaphore released based on time periods
        pass


class IntegrationClient:
    """
    Client used to interact with external APIs providing data for Maltego transforms.
    """

    def __init__(
            self,
            # Concurrency throttler
            max_concurrent: int = 50,
            max_concurrent_per_key: int = 6,
            # Rate throttler
            max_calls_per_period: int = 25,
            period_length_seconds: float = 1.0,
            # httpx AsyncClient settings
            timeout: int = 30,
            verify_ssl: bool = True,
            use_api_key_for_throttling: bool = True,
            use_client_ip_for_throttling: bool = False,
            proxies: Optional[ProxyTypes] = None,
            trust_env: bool = True,
            response_hooks: Optional[
                List[Callable[..., Any]]
            ] = None
    ) -> None:
        self.concurrency_overrides: Dict[Optional[SemKeyType], int] = {}
        self.connection_throttler = Throttler(
            global_max_concurrent=max_concurrent,
            max_concurrent_per_key=max_concurrent_per_key,
            user_concurrency_overrides=self.concurrency_overrides
        )
        self.rate_throttler = AsyncLeakyBucket(
            max_tasks=max_calls_per_period, time_period=period_length_seconds
        )
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._proxies = proxies
        self._trust_env = trust_env
        self.httpx_client = self._build_httpx_client(proxies=proxies, trust_env=trust_env)
        self.use_api_key_for_throttling = use_api_key_for_throttling
        self.use_client_ip_for_throttling = use_client_ip_for_throttling
        self.response_hooks = response_hooks or []
        self._closed = False

    async def aclose(self) -> None:
        """Close the underlying HTTP client and cancel internal background tasks.

        This method is idempotent — calling it multiple times is safe.
        Any coroutines already past the closed guard and blocked on the
        rate-throttler semaphore are unblocked so they can fail fast on the
        closed httpx client instead of hanging until the event loop shuts down.
        """
        if self._closed:
            return
        self._closed = True
        with suppress(Exception):
            await self.httpx_client.aclose()
        # Drain the rate-throttler semaphore before cancelling _leak_task so
        # that coroutines already past the _closed guard and blocked inside
        # AsyncLeakyBucket.__aenter__ are unblocked immediately.
        if self.rate_throttler._sem is not None:
            for _ in range(self.rate_throttler.max_tasks):
                try:
                    self.rate_throttler._sem.release()
                except ValueError:
                    break
        if self.rate_throttler._leak_task is not None:
            self.rate_throttler._leak_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self.rate_throttler._leak_task
            self.rate_throttler._leak_task = None
            self.rate_throttler._leak_started = False

    async def __aenter__(self) -> "IntegrationClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc: Optional[BaseException],
        tb: Optional[Any],
    ) -> None:
        await self.aclose()

    def _build_httpx_client(
        self,
        proxies: Optional[ProxyTypes] = None,
        trust_env: bool = True,
    ) -> httpx.AsyncClient:
        client_kwargs: Dict[str, Any] = {
            "timeout": self.timeout,
            "verify": self.verify_ssl,
            "trust_env": trust_env,
            # Explicit SDK-level guarantee (not just httpx's default): never
            # auto-follow redirects. Silently following a redirect could be
            # abused to retarget an outbound request at an internal/unintended
            # host (SSRF via redirect) using credentials/headers meant for the
            # original destination.
            "follow_redirects": False,
        }
        if proxies is not None:
            if "proxy" in inspect.signature(httpx.AsyncClient.__init__).parameters:
                client_kwargs["proxy"] = proxies
            else:
                client_kwargs["proxies"] = proxies
        return httpx.AsyncClient(**client_kwargs)

    async def __response_hook(
        self,
        response: Optional[httpx.Response],
        context: MaltegoContext,
        **kwargs: Any
    ) -> None:
        for hook in self.response_hooks:
            try:
                hook(response, context, **kwargs)
            except SystemExit as e:
                raise e
            except KeyboardInterrupt as e:
                raise e
            except MaltegoException as e:
                # Preserve the specific MaltegoException subclass type
                raise e
            except BaseException as e:
                raise MaltegoException(f"Error. Unhandled exception in request hook {hook}") from e

    def override_concurrency_limit_for(
        self,
        context: MaltegoContext,
        new_limit: int,
        client_identifier: Optional[str] = None
    ) -> None:
        self.concurrency_overrides[self.get_identifier(
            context, client_identifier)] = new_limit

    def get_identifier(self, context: MaltegoContext, client_identifier: Optional[str]) -> SemKeyType:
        if client_identifier is None:
            # Prefer the validated identity key; fall back to the legacy api_key
            # only when no validated identity is available.
            if self.use_api_key_for_throttling:
                throttle_key = context.rate_limit_key or context.api_key
            else:
                throttle_key = None
            return (
                throttle_key,
                context.remote_ip if self.use_client_ip_for_throttling else None
            )
        return client_identifier

    async def run_rate_throttled(self, awaitable: Awaitable[Response]) -> Response:
        async with self.rate_throttler:
            return await awaitable

    async def run_concurrency_throttled(
        self,
        awaitable: Awaitable[Response],
        context: MaltegoContext,
        client_identifier: Optional[str] = None
    ) -> Response:
        return await self.connection_throttler.execute_throttled(
            awaitable, self.get_identifier(context, client_identifier)
        )

    async def run_throttled(
        self,
        awaitable: Awaitable[Response],
        context: MaltegoContext,
        client_identifier: Optional[str] = None
    ) -> Response:
        if self._closed:
            raise MaltegoException("IntegrationClient has been closed and cannot accept new requests.")
        # throttler order: we first make the user acquire a "connection" slot
        # (i.e. the right to make another parallel request)
        # after that, we execute that request only after acquiring the global rate throttler.
        # (I think awaiting throttlers in the other order could cause problems, but I'm not 100% sure that's the case)
        return await self.run_concurrency_throttled(
            self.run_rate_throttled(awaitable), context, client_identifier=client_identifier
        )

    async def _reset_client(self) -> None:
        if self._closed:
            raise MaltegoHTTPDataProviderUnavailable("Failed to connect to API, try again later.")
        with suppress(Exception):
            await self.httpx_client.aclose()
        self.httpx_client = self._build_httpx_client(proxies=self._proxies, trust_env=self._trust_env)
        raise MaltegoHTTPDataProviderUnavailable("Failed to connect to API, try again later.")

    async def _client_call_retrying_if_reset(
        self,
        *args: Any,
        **kwargs: Any
    ) -> Optional[Response]:
        # makes a request, trying a connection re-establish in case of a HTTP error (but not otherwise)
        # If it's a CloseError, we assume the connection just got dropped by the remote, and we retry the request.
        # All other transport errors propagate to _call_httpx_method where they are mapped specifically.
        response = None
        try:
            response = await self.httpx_client.request(*args, **kwargs)
        except httpx.CloseError:
            log.exception(
                "Connection appears to have been dropped, retrying request once")
            try:
                response = await self.httpx_client.request(*args, **kwargs)
            except httpx.HTTPError:
                log.exception(
                    "Unknown connection error, resetting client (will not retry the request again)")
                await self._reset_client()
        return response

    async def _call_httpx_method(
        self,
        method: str,
        url: str,
        context: MaltegoContext,
        **kwargs: Any
    ) -> Response:
        url_obj = urlparse(url)
        url_netloc = url_obj.netloc

        try:
            res = await self._client_call_retrying_if_reset(
                method=method, url=url, **kwargs,
            )
            await self.__response_hook(res, context)
            if res is None:
                log.error(f"Upstream API: Could not successfully contact {url_netloc} API (no response).")
                exc = MaltegoHTTPDataProviderUnavailable(
                    f"Upstream API: Could not successfully contact {url_netloc} API.",
                )
                context.upstream_exceptions.append(exc)
                raise exc

            if httpx.codes.OK <= res.status_code < 300:
                return res

            if res.status_code == httpx.codes.UNAUTHORIZED:
                log.error(f"Upstream API: {url_netloc} API key invalid ({httpx.codes.UNAUTHORIZED}).")
                exc = MaltegoHTTPDataProviderAPIKeyInvalid(
                    f"Upstream API: {url_netloc} API key invalid ({httpx.codes.UNAUTHORIZED}).", response=res
                )
                context.upstream_exceptions.append(exc)
                raise exc
            elif res.status_code == httpx.codes.FORBIDDEN:
                log.error(f"Upstream API: {url_netloc} API unauthorized ({httpx.codes.FORBIDDEN}).")
                exc = MaltegoHTTPUnauthorized(
                    f"Upstream API: {url_netloc} API unauthorized ({httpx.codes.FORBIDDEN}).", response=res
                )
                context.upstream_exceptions.append(exc)
                raise exc
            elif res.status_code == httpx.codes.NOT_FOUND:
                log.error(f"Upstream API: {url_netloc} API resource not found ({httpx.codes.NOT_FOUND}).")
                exc = MaltegoHTTPDataProviderNotFound(
                    f"Upstream API: {url_netloc} API resource not found ({httpx.codes.NOT_FOUND}).", response=res
                )
                context.upstream_exceptions.append(exc)
                raise exc
            elif httpx.codes.INTERNAL_SERVER_ERROR <= res.status_code < 600:
                log.error(f"Upstream API: {url_netloc} API unavailable ({res.status_code}).")
                exc = MaltegoHTTPDataProviderUnavailable(
                    f"Upstream API: {url_netloc} API unavailable ({res.status_code}).", response=res
                )
                context.upstream_exceptions.append(exc)
                raise exc
            else:
                log.error(f"Upstream API: {url_netloc} API returned a non-2xx code ({res.status_code}).")
                exc = MaltegoException(
                    f"Upstream API: {url_netloc} API returned a non-2xx code ({res.status_code}).", response=res
                )
                context.upstream_exceptions.append(exc)
                raise exc
        except httpx.ConnectError as exception:
            log.warning(f"Connection error for url: {url} - {exception}")
            exc = MaltegoHTTPDataProviderUnavailable(
                f"Upstream API: Could not connect to {url_netloc} API (connection failed).", response=None
            )
            context.upstream_exceptions.append(exc)
            raise exc
        except httpx.ReadTimeout as exception:
            log.warning(f"Read timeout for url: {url} - {exception}")
            exc = MaltegoHTTPDataProviderUnavailable(
                f"Upstream API: Timeout reading from {url_netloc} API.", response=None
            )
            context.upstream_exceptions.append(exc)
            raise exc
        except httpx.TimeoutException as exception:
            log.warning(f"Timeout for url: {url} - {exception}")
            exc = MaltegoHTTPDataProviderUnavailable(
                f"Upstream API: Timeout waiting for {url_netloc} API.", response=None
            )
            context.upstream_exceptions.append(exc)
            raise exc
        except httpx.RemoteProtocolError as exception:
            log.warning(f"Remote protocol error for url: {url} - {exception}")
            exc = MaltegoHTTPDataProviderUnavailable(
                f"Upstream API: {url_netloc} API disconnected unexpectedly.", response=None
            )
            context.upstream_exceptions.append(exc)
            raise exc
        except httpx.HTTPError as exception:
            log.warning(f"HTTP error for url: {url} - {exception}")
            exc = MaltegoHTTPDataProviderUnavailable(
                f"Upstream API: Could not successfully contact {url_netloc} API.", response=None
            )
            context.upstream_exceptions.append(exc)
            raise exc
        except MaltegoException as exception:
            if exception not in context.upstream_exceptions:
                context.upstream_exceptions.append(exception)
            raise exception
        except Exception as exception:
            log.error(exception, exc_info=True)
            exc = MaltegoException(
                f"Upstream API: Could not successfully contact {url_netloc} API.", code=500
            )
            context.upstream_exceptions.append(exc)
            raise exc

    async def get(
        self,
        url: str,
        context: MaltegoContext,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "GET", url, context=context,
            headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )

    async def post(
        self,
        url: str,
        context: MaltegoContext,
        content: Optional[Union[str, bytes]] = None,
        json: Optional[Any] = None,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "POST", url, context=context,
            content=content, json=json, headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )

    async def request(
        self,
        method: str,
        url: str,
        context: MaltegoContext,
        content: Optional[Union[str, bytes]] = None,
        json: Optional[Any] = None,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        """Make an HTTP request using any method, applying throttling and error mapping.

        This is the single entry point for all HTTP calls. ``get``, ``post``, ``put``,
        ``patch``, ``delete``, and ``head`` are all convenience wrappers around this method.
        The ``method`` string is passed through to httpx unchanged; standard HTTP verbs
        are typically uppercase (``GET``, ``POST``, etc.).
        """
        if self._closed:
            raise MaltegoException("IntegrationClient has been closed and cannot accept new requests.")
        return await self.run_throttled(
            self._call_httpx_method(
                method,
                url,
                params=params,
                headers=headers,
                content=content,
                context=context,
                json=json,
                **kwargs
            ),
            context=context,
            client_identifier=client_identifier
        )

    async def put(
        self,
        url: str,
        context: MaltegoContext,
        content: Optional[Union[str, bytes]] = None,
        json: Optional[Any] = None,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "PUT", url, context=context,
            content=content, json=json, headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )

    async def patch(
        self,
        url: str,
        context: MaltegoContext,
        content: Optional[Union[str, bytes]] = None,
        json: Optional[Any] = None,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "PATCH", url, context=context,
            content=content, json=json, headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )

    async def delete(
        self,
        url: str,
        context: MaltegoContext,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "DELETE", url, context=context,
            headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )

    async def head(
        self,
        url: str,
        context: MaltegoContext,
        headers: Optional[Headers] = None,
        params: Optional[Dict[str, Any]] = None,
        client_identifier: Optional[str] = None,
        **kwargs: Any
    ) -> Response:
        return await self.request(
            "HEAD", url, context=context,
            headers=headers, params=params,
            client_identifier=client_identifier, **kwargs
        )
