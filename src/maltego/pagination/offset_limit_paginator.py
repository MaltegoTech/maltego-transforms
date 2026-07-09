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


class OffsetLimitPaginator(PaginatorWithLimit[T]):
    offset_param_name: str

    def __init__(
        self,
        client: IntegrationClient,
        response_to_items: ResponseToItems,
        page_size: int,
        page_size_param_name: str = "limit",
        min_page_fill: float = 1.0,
        request_extra_items_pct: float = 0.0,
        response_to_total_cnt: Optional[ResponseToTotalCnt] = None,
        max_pages: Optional[int] = None,
        offset_param_name: str = "offset",
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

        self.offset_param_name = offset_param_name

    def get_pagination_state_for_next_page(
        self, previous_state: PaginationState, last_response: Optional[Response]
    ) -> PaginationState:
        new_pagination_state = (
            previous_state.get_safe_copy()
        )  # NB: Modifying the same params object causes issues in parallel requests

        # Update offset
        page_size_in_params = new_pagination_state.params[self.page_size_param_name]
        new_pagination_state.params[self.offset_param_name] = (
            int(new_pagination_state.params[self.offset_param_name]
                ) + int(page_size_in_params)
        )

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
        if self.offset_param_name in params:
            log.warning(
                f"The param '{self.offset_param_name}' in the given params, will be overwritten by the paginator"
            )
        if self.page_size_param_name in params:
            log.warning(
                f"The param '{self.page_size_param_name}' in the given params, will be overwritten by the paginator"
            )

        # Set start pagination parameters
        params[self.offset_param_name] = int(0)
        params[self.page_size_param_name] = int(
            self.get_effective_page_size(slider))
        return await super().fetch_all_items(
            slider, context, url, content, json, headers, params, auth, **kwargs
        )

    def get_init_pagination_state(
        self,
        url: str,
        slider: int,
        params: Optional[Dict[str, Union[str, int]]] = None,
        headers: Optional[Dict[str, str]] = None,
        content: Optional[str] = None,
        json: Optional[Dict[str, Any]] = None,
        auth: AuthType = None,
    ) -> PaginationState:
        params = params or {}
        if self.offset_param_name in params:
            log.warning(
                f"The param '{self.offset_param_name}' in the given params, will be overwritten by the paginator"
            )
        if self.page_size_param_name in params:
            log.warning(
                f"The param '{self.page_size_param_name}' in the given params, will be overwritten by the paginator"
            )

        # Set start pagination parameters
        params[self.offset_param_name] = int(0)
        params[self.page_size_param_name] = int(
            self.get_effective_page_size(slider))
        return PaginationState(
            url, params=params, headers=headers, content=content, json=json, auth=auth
        )
