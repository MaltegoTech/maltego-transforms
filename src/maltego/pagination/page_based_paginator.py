# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Dict, Optional, List, Union
import logging
from httpx import Response
from maltego.pagination.pagination import (
    PaginatorWithLimit,
    T,
    PaginationState,
    AuthType,
    ResponseToItems,
    ResponseToTotalCnt
)
from maltego.util import IntegrationClient
from maltego.model.context import MaltegoContext

log = logging.getLogger(__name__)


class PageBasedPaginator(PaginatorWithLimit[T]):
    page_param_name: str
    page_start_num: int

    def __init__(
        self,
        client: IntegrationClient,
        response_to_items: ResponseToItems,
        page_size: int,
        page_size_param_name: str = "limit",
        min_page_fill: float = 1.0,
        request_extra_items_pct: int = 0,
        response_to_total_cnt: Optional[ResponseToTotalCnt] = None,
        max_pages: Optional[int] = None,
        page_param_name: str = "page",
        page_start_num: int = 1,
    ) -> None:
        super().__init__(
            client=client,
            response_to_items=response_to_items,
            page_size=page_size,
            page_size_param_name=page_size_param_name,
            min_page_fill=min_page_fill,
            request_extra_items_pct=request_extra_items_pct,
            response_to_total_cnt=response_to_total_cnt,
            max_pages=max_pages,
        )

        self.page_param_name = page_param_name
        self.page_start_num = page_start_num

    def get_pagination_state_for_next_page(
        self, previous_state: PaginationState, last_response: Optional[Response]
    ) -> PaginationState:
        new_pagination_state = (
            previous_state.get_safe_copy()
        )  # NB: Modifying the same params object causes issues in parallel requests

        # Update offset
        try:
            page = int(new_pagination_state.params[self.page_param_name])
        except ValueError:
            raise ValueError(
                "Could not get new offset page_param_name is not an int")

        new_pagination_state.params[self.page_param_name] = int(page + 1)
        return new_pagination_state

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
        params = params or {}
        if self.page_param_name in params:
            log.warning(
                f"The param '{self.page_param_name}' in the given params, will be overwritten by the paginator"
            )
        if self.page_size_param_name in params:
            log.warning(
                f"The param '{self.page_size_param_name}' in the given params, will be overwritten by the paginator"
            )

        # Set start pagination parameters
        params[self.page_param_name] = int(self.page_start_num)
        params[self.page_size_param_name] = int(
            self.get_effective_page_size(slider))
        return await super().fetch_all_items(
            slider, context, url, content, json, headers, params, auth, **kwargs
        )
