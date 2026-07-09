# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Generic, Optional
from urllib.parse import urlparse as _urlparse
from typing_extensions import Protocol
from httpx import Response
from maltego.pagination.pagination import Paginator, T, PaginationState


class ResponseToCursor(Protocol):
    def __call__(self, *response: Response) -> str: ...


class CursorBasedPaginator(Paginator[T], Generic[T]):
    response_to_cursor: ResponseToCursor

    def __init__(self, response_to_cursor: ResponseToCursor, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.response_to_cursor = response_to_cursor

    def get_pagination_state_for_next_page(
        self, previous_state: PaginationState, last_response: Optional[Response]
    ) -> PaginationState:
        new_pagination_state = (
            previous_state.get_safe_copy()
        )  # NB: Modifying the same params object causes issues in parallel requests

        if last_response is None:
            raise ValueError(
                "Last response must be populated in order for CursorBasedPaginator to work."
            )
        next_url = self.response_to_cursor(last_response)
        # Validate scheme/host of upstream-supplied next-page URL to prevent SSRF.
        _parsed = _urlparse(next_url)
        if _parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"CursorBasedPaginator: next-page URL has disallowed scheme "
                f"{_parsed.scheme!r}; only 'http' and 'https' are permitted."
            )
        if not _parsed.netloc:
            raise ValueError(
                "CursorBasedPaginator: next-page URL has no host/netloc; "
                "relative URLs are not permitted."
            )
        new_pagination_state.url = next_url
        return new_pagination_state

    def should_fetch_next_page(
        self,
        pages_fetched: int,
        pagination_state: PaginationState,
        slider: int,
        num_items_last_resp: int,
        num_items_all_resp: int
    ) -> bool:
        raise NotImplementedError
