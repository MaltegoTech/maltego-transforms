# Copyright (c) Maltego Technologies GmbH.
from unittest.mock import MagicMock

import httpx
import pytest

from maltego.model.context import MaltegoContext
from maltego.model.exception import MaltegoException
from maltego.model.graph import MaltegoGraph
from maltego.util import IntegrationClient
from maltego.pagination.offset_limit_paginator import OffsetLimitPaginator

from tests.conftest import TEST_URL, TEST_PARAMS, TEST_HEADERS, TEST_JSON

pytestmark = pytest.mark.unit


def create_pagination_context() -> MaltegoContext:
    request = MagicMock()
    request.headers = {}
    return MaltegoContext(MaltegoGraph(), request)


def response_to_json_items(response):
    return response.json()


class EmptyPagePaginator(OffsetLimitPaginator):
    def __init__(self):
        super().__init__(
            client=IntegrationClient(),
            response_to_items=response_to_json_items,
            page_size=100,
        )
        self.request_count = 0

    async def make_request_to_api(self, pagination_state, context):
        self.request_count += 1
        return httpx.Response(200, json=[])


class FailingPaginator(OffsetLimitPaginator):
    def __init__(self):
        super().__init__(
            client=IntegrationClient(),
            response_to_items=response_to_json_items,
            page_size=100,
        )

    async def make_request_to_api(self, pagination_state, context):
        raise MaltegoException("upstream failed")


def test_pagination_state_to_dict(pagination_state):
    # Given a pagination state
    # When calling to_dict
    pag_dct = pagination_state.to_dict()
    # Then all properties are returned
    assert pag_dct["url"] == TEST_URL
    assert pag_dct["params"] == TEST_PARAMS
    assert pag_dct["headers"] == TEST_HEADERS
    assert pag_dct["json"] == TEST_JSON


def test_pagination_sate_get_safe_copy(pagination_state):
    # Given a pagination state
    # When calling get_safe_copy
    page_state = pagination_state.get_safe_copy()
    # Then new object references are set for the new pagination state
    assert id(page_state.url) == id(TEST_URL)
    assert id(page_state.params) != id(TEST_PARAMS)
    assert id(page_state.headers) != id(TEST_HEADERS)
    assert id(page_state.json) != id(TEST_JSON)


@pytest.mark.asyncio
async def test_fetch_all_items_stops_on_empty_page_even_when_next_page_available():
    paginator = EmptyPagePaginator()

    items = await paginator.fetch_all_items(
        slider=255,
        context=create_pagination_context(),
        url=TEST_URL,
    )

    assert items == []
    assert paginator.request_count == 1


@pytest.mark.asyncio
async def test_stream_all_items_stops_on_empty_page():
    paginator = EmptyPagePaginator()

    pages = [
        page async for page in paginator.stream_all_items(
            slider=255,
            context=create_pagination_context(),
            url=TEST_URL,
        )
    ]

    assert pages == []
    assert paginator.request_count == 1


@pytest.mark.asyncio
async def test_fetch_all_items_swallows_maltego_exception():
    paginator = FailingPaginator()
    context = create_pagination_context()

    items = await paginator.fetch_all_items(
        slider=255,
        context=context,
        url=TEST_URL,
    )

    assert items == []
    assert context.log.log_messages == [
        (
            "PartialError",
            "An error occurred, whilst paginating the API. Results may be incomplete.",
        )
    ]


@pytest.mark.asyncio
async def test_fetch_all_items_unsafe_raises_maltego_exception():
    paginator = FailingPaginator()

    with pytest.raises(MaltegoException) as exc_info:
        await paginator.fetch_all_items_unsafe(
            slider=255,
            context=create_pagination_context(),
            url=TEST_URL,
        )
    assert exc_info.value.message == "upstream failed"


def test_fetch_next_page_parallel(
    offset_limit_paginator, pagination_state_with_offset_limit
):
    # Given a paginator with more results available
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = (
        offset_limit_paginator.should_fetch_next_page_in_parallel(
            1, pagination_state_with_offset_limit, 255, 300
        )
    )
    # Then true is returned
    assert should_fetch_next_page_parallel

    # Given a paginator with no more results available
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = (
        offset_limit_paginator.should_fetch_next_page_in_parallel(
            1, pagination_state_with_offset_limit, 255, 30
        )
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel

    # Given a paginator, where the current results are greater than the slider
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = (
        offset_limit_paginator.should_fetch_next_page_in_parallel(
            3, pagination_state_with_offset_limit, 255, 300
        )
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel

    # Given a paginator, where the max_pages is exceeded
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = (
        offset_limit_paginator.should_fetch_next_page_in_parallel(
            6, pagination_state_with_offset_limit, 3000, 3000
        )
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel


def test_should_fetch_next_page(
    offset_limit_paginator, pagination_state_with_offset_limit
):
    # Given a paginator with more results available
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = offset_limit_paginator.should_fetch_next_page(
        1, pagination_state_with_offset_limit, 255, 100, 100
    )
    # Then true is returned
    assert should_fetch_next_page_parallel

    # Given a paginator with no more results available
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = offset_limit_paginator.should_fetch_next_page(
        1, pagination_state_with_offset_limit, 255, 3, 100
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel

    # Given a paginator, where the current results are greater than the slider
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = offset_limit_paginator.should_fetch_next_page(
        3, pagination_state_with_offset_limit, 255, 100, 300
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel

    # Given a paginator, where the max_pages is exceeded
    # When deciding to fetch the next page
    should_fetch_next_page_parallel = offset_limit_paginator.should_fetch_next_page(
        6, pagination_state_with_offset_limit, 255, 100, 100
    )
    # Then False is returned
    assert not should_fetch_next_page_parallel


def test_get_effective_page_size():
    offset_limit_paginator = OffsetLimitPaginator(
        IntegrationClient(), lambda x: [], 100, request_extra_items_pct=0.3
    )
    # Given an request_extra_items_pct of 0.3, but slider greater than page size
    # When getting the effective page size
    # Then the page size is returned
    assert offset_limit_paginator.get_effective_page_size(255) == 100

    # Given an request_extra_items_pct of 0.3, and a slider of 10
    # When getting the effective page sie
    # Then the correct result is returned
    assert offset_limit_paginator.get_effective_page_size(10) == 13


def test_offset_limit_get_pagination_state_for_next(
    offset_limit_paginator, pagination_state_with_offset_limit
):
    # Given an unused paginator
    # When getting pagination state for next page
    next_page_state = offset_limit_paginator.get_pagination_state_for_next_page(
        pagination_state_with_offset_limit, None
    )
    # Then the params are updated as expected
    assert next_page_state.params[
        offset_limit_paginator.offset_param_name
    ] == offset_limit_paginator.page_size


def test_page_based_get_pagination_state_for_next(
    page_based_paginator, pagination_state_with_page
):
    # Given an unused paginator
    # When getting pagination state for next page
    next_page_state = page_based_paginator.get_pagination_state_for_next_page(
        pagination_state_with_page, None
    )
    # Then the params are updated as expected
    assert next_page_state.params[page_based_paginator.page_param_name] == 2
    assert next_page_state.params[
        page_based_paginator.page_size_param_name
    ] == page_based_paginator.page_size
