# Copyright (c) Maltego Technologies GmbH.
import logging
from abc import abstractmethod
from typing import Any, AsyncIterator, Dict, Generic, List, Optional, Tuple, TypeVar, Union
from urllib.parse import urlparse as _urlparse, urlunparse as _urlunparse

import asyncio
from httpx import Response
from typing_extensions import Protocol

from maltego.model.context import MaltegoContext
from maltego.model.exception import MaltegoException
from maltego.util import IntegrationClient

log = logging.getLogger()
T = TypeVar("T")
AuthType = Optional[Tuple[Union[str, bytes], Union[str, bytes]]]


def _redact_url(url: Optional[str]) -> str:
    """Strip query string and fragment from a URL before logging.

    Upstream pagination URLs frequently carry API keys/tokens in the query
    string; logging them verbatim leaks secrets into log aggregation systems.
    """
    parsed = _urlparse(url or "")
    return _urlunparse(parsed._replace(query="", fragment=""))


class ResponseToItems(Protocol):
    def __call__(
        self,
        response: Response,
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Optional[List[T]]: ...


class ResponseToTotalCnt(Protocol):
    def __call__(self, response: Response) -> int: ...


class PaginationState:
    """
    Internal data container only.

    Used for bundling request kwargs together into a single object.
    """

    url: str
    params: Dict[str, Union[str, int]]
    headers: Dict[str, str]
    json: Optional[Dict[str, Any]]
    content: Optional[str]
    auth: AuthType

    def __init__(
            self,
            url: str,
            params: Optional[Dict[str, Union[str, int]]] = None,
            headers: Optional[Dict[str, str]] = None,
            json: Optional[Dict[str, Any]] = None,
            content: Optional[str] = None,
            auth: AuthType = None
    ) -> None:
        self.url = url
        self.params = params or {}
        self.headers = headers or {}
        self.json = json
        self.content = content
        self.auth = auth

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "params": self.params,
            "headers": self.headers,
            "json": self.json,
            "content": self.content,
            "auth": self.auth,
        }

    def get_safe_copy(self) -> "PaginationState":
        """
        When running pagination in parallel, we cannot be modifying the same objects (params, json)
        as then all requests will be made with params in the final state.
        """
        return PaginationState(
            url=self.url,
            params=self.params.copy(),
            headers=self.headers.copy(),
            json=self.json.copy() if self.json else None,
            content=self.content,
            auth=self.auth,
        )


class Paginator(Generic[T]):
    client: IntegrationClient

    max_pages: Optional[int]

    response_to_items: ResponseToItems
    response_to_total_cnt: Optional[ResponseToTotalCnt]

    def __init__(
            self,
            # No optional kwargs. Optional kwargs with default value should by terminal child class
            client: IntegrationClient,
            response_to_items: ResponseToItems,
            response_to_total_cnt: Optional[ResponseToTotalCnt],
            max_pages: Optional[int],
    ):
        self.client = client
        self.response_to_items = response_to_items
        self.response_to_total_cnt = response_to_total_cnt

        self.max_pages = max_pages

    @abstractmethod
    def should_fetch_next_page(
            self,
            pages_fetched: int,
            pagination_state: PaginationState,
            slider: int,
            num_items_last_resp: int,
            num_items_all_resp: int,
    ) -> bool:
        pass

    @abstractmethod
    def should_fetch_next_page_in_parallel(
            self,
            pages_fetched: int,
            pagination_state: PaginationState,
            slider: int,
            total_cnt: int,
    ) -> bool:
        pass

    @abstractmethod
    def get_pagination_state_for_next_page(
            self, previous_state: PaginationState, last_response: Optional[Response]
    ) -> PaginationState:
        pass

    async def make_request_to_api(
            self, pagination_state: PaginationState, context: MaltegoContext
    ) -> Response:
        """
        Determines how the paginator sends the request via the integration client.

        Override this method if the default GET and POST request logic isn't sufficient.
        """
        client_call_kwargs = pagination_state.to_dict()
        url = client_call_kwargs.pop("url")
        if pagination_state.json or pagination_state.content:
            return await self.client.post(url, context, **client_call_kwargs)
        return await self.client.get(url, context, **client_call_kwargs)

    async def make_request_to_api_with_exception_handling(
            self, pagination_state: PaginationState, context: MaltegoContext
    ) -> Optional[Response]:
        """
        Logic for failing requests is handled here.

        Default implementation, is that if the request fails then the paginator still returns a list of items.

        This is so that if we have 4 successful pages, and a 5th fail, then the initial results are still returned.
        """
        try:
            return await self.make_request_to_api(pagination_state, context)
        except MaltegoException as exception:
            log.error(f"Paginator Caught Exception: {exception}")
            context.log.partial(
                "An error occurred, whilst paginating the API. Results may be incomplete."
            )
            return None

    async def fetch_subsequent_items_in_parallel(
            self,
            slider: int,
            context: MaltegoContext,
            pagination_state_initial: PaginationState,
            pages_fetched_initial: int,
            total_cnt: int,
            **kwargs: Dict[str, Any],
    ) -> List[T]:
        pending_responses = []
        all_items: List[T] = []
        pages_fetched = pages_fetched_initial
        pagination_state = pagination_state_initial
        should_fetch_next_page_in_parallel = self.should_fetch_next_page_in_parallel(
            pages_fetched, pagination_state, slider, total_cnt
        )

        while should_fetch_next_page_in_parallel:
            log.info(
                "Fire parallel page request: %s, params=<redacted>",
                _redact_url(pagination_state.url),
            )
            pending_responses.append(
                self.make_request_to_api_with_exception_handling(
                    pagination_state, context
                )
            )
            pages_fetched += 1
            should_fetch_next_page_in_parallel = (
                self.should_fetch_next_page_in_parallel(
                    pages_fetched, pagination_state, slider, total_cnt
                )
            )
            pagination_state = self.get_pagination_state_for_next_page(
                pagination_state, None
            )

        if pending_responses:
            response_to_be_parsed = await asyncio.gather(*pending_responses)
            for response in response_to_be_parsed:
                if response:  # Failing requests will return None
                    items: Optional[List[T]] = None
                    if kwargs:
                        items = self.response_to_items(response, **kwargs)
                    else:
                        items = self.response_to_items(response)
                    all_items += items if items is not None else []

        return all_items

    def parse_response(self, response_to_be_parsed: List[Response], kwargs: Any) -> List[T]:
        all_items: List[T] = []
        for response in response_to_be_parsed:
            if response:  # Failing requests will return None
                items: Optional[List[T]] = None
                if kwargs:
                    items = self.response_to_items(response, **kwargs)
                else:
                    items = self.response_to_items(response)
                all_items += items if items is not None else []
        return all_items

    async def fetch_subsequent_items_in_parallel_unsafe(
            self,
            slider: int,
            context: MaltegoContext,
            pagination_state_initial: PaginationState,
            pages_fetched_initial: int,
            total_cnt: int,
            **kwargs: Dict[str, Any],
    ) -> List[T]:
        pending_responses = []
        pages_fetched = pages_fetched_initial
        pagination_state = pagination_state_initial
        should_fetch_next_page_in_parallel = self.should_fetch_next_page_in_parallel(
            pages_fetched, pagination_state, slider, total_cnt
        )

        while should_fetch_next_page_in_parallel:
            log.info(
                "Fire parallel page request: %s, params=<redacted>",
                _redact_url(pagination_state.url),
            )
            pending_responses.append(
                self.make_request_to_api(
                    pagination_state, context
                )
            )
            pages_fetched += 1
            should_fetch_next_page_in_parallel = (
                self.should_fetch_next_page_in_parallel(
                    pages_fetched, pagination_state, slider, total_cnt
                )
            )
            pagination_state = self.get_pagination_state_for_next_page(
                pagination_state, None
            )

        if pending_responses:
            response_to_be_parsed = await asyncio.gather(*pending_responses)
            return self.parse_response(response_to_be_parsed, kwargs)

        return []

    def get_init_pagination_state(
            self,
            url: str,
            slider: int,  # pylint: disable=unused-argument
            params: Optional[Dict[str, Union[str, int]]] = None,
            headers: Optional[Dict[str, str]] = None,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            auth: AuthType = None,
    ) -> PaginationState:
        return PaginationState(
            url, params=params, headers=headers, content=content, json=json, auth=auth
        )

    async def fetch_all_items(
            self,
            slider: int,
            context: MaltegoContext,
            url: str,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Union[str, int]]] = None,
            auth: AuthType = None,
            **kwargs: Dict[str, Any],
    ) -> List[T]:
        start_pagination_state = self.get_init_pagination_state(
            url, slider, params=params, headers=headers, content=content, json=json, auth=auth
        )
        pages_fetched = 0
        total_cnt = None

        all_items = []
        pagination_state = start_pagination_state
        should_fetch_next_page = True
        log.debug("Paginator: Fetch all items for url '%s'", _redact_url(url))  # redact query string from URL before logging
        while should_fetch_next_page and total_cnt is None:
            items, pagination_state, total_cnt = await self.fetch_items_step(context, pagination_state, **kwargs)
            if items:
                if not isinstance(items, list):
                    log.error(
                        "Paginator fetch_items_step did not return a list. Stopping")
                    break
                all_items += items
                log.debug(
                    f"Paginator: Fetched '{len(items)}' items. Total: {len(all_items)}")

                should_fetch_next_page = self.should_fetch_next_page(
                    pages_fetched, pagination_state, slider, len(
                        items), len(all_items)
                )
                pages_fetched += 1
            else:
                log.debug(
                    "Paginator: fetch_items_step returned None. Stopping pagination")
                break  # Stop paginating if a request to the API fails

        # Only continue if we don't already have enough elements
        if total_cnt and len(all_items) < slider:
            all_items += await self.fetch_subsequent_items_in_parallel(
                slider, context, pagination_state, pages_fetched, total_cnt, **kwargs
            )
        return all_items

    async def _stream_all_items(
            self,
            slider: int,
            context: MaltegoContext,
            url: str,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Union[str, int]]] = None,
            auth: AuthType = None,
            safe: Optional[bool] = True,
            **kwargs: Dict[str, Any],
    ) -> AsyncIterator[List[T]]:
        start_pagination_state = self.get_init_pagination_state(
            url, slider, params=params, headers=headers, content=content, json=json, auth=auth
        )
        if safe:
            fetch_items_step = self.fetch_items_step
            fetch_subsequent_items_in_parallel = self.fetch_subsequent_items_in_parallel
        else:
            fetch_items_step = self.fetch_items_step_unsafe
            fetch_subsequent_items_in_parallel = self.fetch_subsequent_items_in_parallel_unsafe

        pages_fetched = 0
        all_items_count = 0
        total_cnt = None
        pagination_state = start_pagination_state
        should_fetch_next_page = True
        log.debug("Paginator: Fetch all items for url '%s'", _redact_url(url))  # redact query string from URL before logging
        while should_fetch_next_page and total_cnt is None:
            (
                items,
                pagination_state,
                total_cnt,
            ) = await fetch_items_step(
                context,
                pagination_state,
                **kwargs,
            )
            if items:
                if not isinstance(items, list):
                    log.error(
                        "Paginator did not return a list. Stopping",
                    )
                    break
                all_items_count += len(items)
                log.debug(
                    "Paginator: Fetched '%s' items. Total: %s",
                    len(items),
                    all_items_count,
                )

                should_fetch_next_page = self.should_fetch_next_page(
                    pages_fetched,
                    pagination_state,
                    slider,
                    len(
                        items,
                    ),
                    all_items_count,
                )
                pages_fetched += 1
                yield items
            else:
                log.debug(
                    "Paginator: returned None. Stopping pagination",
                )
                break  # Stop paginating if a request to the API fails

        # Only continue if we don't already have enough elements
        if total_cnt and all_items_count < slider:
            yield await fetch_subsequent_items_in_parallel(
                slider, context, pagination_state, pages_fetched, total_cnt, **kwargs
            )

    async def stream_all_items(
            self,
            slider: int,
            context: MaltegoContext,
            url: str,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Union[str, int]]] = None,
            auth: AuthType = None,
            **kwargs: Dict[str, Any],
    ) -> AsyncIterator[List[T]]:
        """
        Stream all items, page by page
        """
        async for page in self._stream_all_items(slider=slider,
                                                 context=context,
                                                 url=url,
                                                 content=content,
                                                 json=json,
                                                 headers=headers,
                                                 params=params,
                                                 auth=auth,
                                                 safe=True,
                                                 ** kwargs):
            yield page

    async def fetch_items_step(
            self,
            context: MaltegoContext,
            pagination_state: PaginationState,
            **kwargs: Dict[str, Any]
    ) -> Tuple[Optional[List[T]], PaginationState, Optional[int]]:
        response = await self.make_request_to_api_with_exception_handling(
            pagination_state, context
        )
        items: Optional[List[T]] = None
        total_cnt = None
        if response:
            if kwargs:
                items = self.response_to_items(response, **kwargs)
            else:
                items = self.response_to_items(response)
            if items is None:
                log.debug(
                    "Paginator response_to_items returned None. Stop paginating")

            pagination_state = self.get_pagination_state_for_next_page(
                pagination_state, response
            )
            if self.response_to_total_cnt:
                # Allow parallelization if we have total_cnt
                total_cnt = self.response_to_total_cnt(
                    response
                )  # Will exit while loop

        return items, pagination_state, total_cnt

    async def fetch_all_items_unsafe(
            self,
            slider: int,
            context: MaltegoContext,
            url: str,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Union[str, int]]] = None,
            auth: AuthType = None,
            **kwargs: Dict[str, Any],
    ) -> List[T]:
        start_pagination_state = self.get_init_pagination_state(
            url, slider, params=params, headers=headers, content=content, json=json, auth=auth
        )
        pages_fetched = 0
        total_cnt = None

        all_items = []
        pagination_state = start_pagination_state
        should_fetch_next_page = True
        log.debug("Paginator: Fetch all items for url '%s'", _redact_url(url))  # redact query string from URL before logging
        while should_fetch_next_page and total_cnt is None:
            items, pagination_state, total_cnt = await self.fetch_items_step_unsafe(context, pagination_state, **kwargs)
            if items:
                if not isinstance(items, list):
                    log.error(
                        "Paginator fetch_items_step_unsafe did not return a list. Stopping")
                    break
                all_items += items
                log.debug(
                    f"Paginator: Fetched '{len(items)}' items. Total: {len(all_items)}")

                should_fetch_next_page = self.should_fetch_next_page(
                    pages_fetched, pagination_state, slider, len(
                        items), len(all_items)
                )
                pages_fetched += 1
            else:
                log.debug(
                    "Paginator: fetch_items_step_unsafe returned None. Stopping pagination")
                break  # Stop paginating if a request to the API fails

        # Only continue if we don't already have enough elements
        if total_cnt and len(all_items) < slider:
            all_items += await self.fetch_subsequent_items_in_parallel_unsafe(
                slider, context, pagination_state, pages_fetched, total_cnt, **kwargs
            )
        return all_items

    async def stream_all_items_unsafe(
            self,
            slider: int,
            context: MaltegoContext,
            url: str,
            content: Optional[str] = None,
            json: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Union[str, int]]] = None,
            auth: AuthType = None,
            **kwargs: Dict[str, Any],
    ) -> AsyncIterator[List[T]]:
        """
         Stream all items, page by page
         """
        async for page in self._stream_all_items(slider=slider,
                                                 context=context,
                                                 url=url,
                                                 content=content,
                                                 json=json,
                                                 headers=headers,
                                                 params=params,
                                                 auth=auth,
                                                 safe=False,
                                                 **kwargs):
            yield page

    async def fetch_items_step_unsafe(
            self,
            context: MaltegoContext,
            pagination_state: PaginationState,
            **kwargs: Dict[str, Any]
    ) -> Tuple[Optional[List[T]], PaginationState, Optional[int]]:
        response = await self.make_request_to_api(
            pagination_state, context
        )
        items: Optional[List[T]] = None
        total_cnt = None
        if response:
            if kwargs:
                items = self.response_to_items(response, **kwargs)
            else:
                items = self.response_to_items(response)
            if items is None:
                log.debug(
                    "Paginator response_to_items returned None. Stop paginating")

            pagination_state = self.get_pagination_state_for_next_page(
                pagination_state, response
            )
            if self.response_to_total_cnt:
                # Allow parallelization if we have total_cnt
                total_cnt = self.response_to_total_cnt(
                    response
                )  # Will exit while loop

        return items, pagination_state, total_cnt


class PaginatorWithLimit(Paginator[T]):
    """
    Internal only class used to share logic between PageBasedPaginator and OffsetLimitPaginator.

    Offset and Page paginator have logic based around the limit param and number of results returned in the latest page
    """

    page_size_param_name: str
    page_size: int
    request_extra_items_pct: float
    min_page_fill: float

    def __init__(
            self,
            # No optional kwargs. Optional kwargs with default value should by terminal child class
            client: IntegrationClient,
            response_to_items: ResponseToItems,
            page_size: int,
            page_size_param_name: str,
            min_page_fill: float,
            request_extra_items_pct: float,
            response_to_total_cnt: Optional[ResponseToTotalCnt],
            max_pages: Optional[int],
    ):
        super().__init__(
            client=client,
            response_to_items=response_to_items,
            response_to_total_cnt=response_to_total_cnt,
            max_pages=max_pages,
        )
        self.page_size_param_name = page_size_param_name
        self.min_page_fill = min_page_fill
        self.page_size = page_size
        self.request_extra_items_pct = request_extra_items_pct

    def should_fetch_next_page_in_parallel(
            self,
            pages_fetched: int,
            pagination_state: PaginationState,
            slider: int,
            total_cnt: int,
    ) -> bool:
        is_below_max_pages = self.max_pages is None or pages_fetched < self.max_pages
        try:
            page_size = int(pagination_state.params[self.page_size_param_name])
        except ValueError:
            raise ValueError("page_size is not set")
        is_below_total_cnt = pages_fetched * page_size < total_cnt

        is_below_slider = pages_fetched * page_size < slider

        return is_below_slider and is_below_max_pages and is_below_total_cnt

    def should_fetch_next_page(
            self,
            pages_fetched: int,
            pagination_state: PaginationState,
            slider: int,
            num_items_last_resp: int,
            num_items_all_resp: int,
    ) -> bool:
        is_below_max_pages = self.max_pages is None or pages_fetched < self.max_pages

        try:
            page_size = int(pagination_state.params[self.page_size_param_name])
        except ValueError:
            raise ValueError("page_size is not set")

        min_number_of_results_required = page_size * self.min_page_fill
        num_results_in_last_resp = num_items_last_resp
        is_latest_response_full = (
            num_results_in_last_resp >= min_number_of_results_required
        )

        is_below_slider = num_items_all_resp < slider

        return is_below_max_pages and is_latest_response_full and is_below_slider

    def get_effective_page_size(self, slider: int) -> int:
        # Adjust the page size down, for low slider values
        slider_multiplier = 1 + self.request_extra_items_pct
        return min(round(slider * slider_multiplier), self.page_size)

    def get_pagination_state_for_next_page(
            self,
            previous_state: PaginationState,
            last_response: Optional[Response]
    ) -> PaginationState:
        raise NotImplementedError
