# Copyright (c) Maltego Technologies GmbH.
from typing import Any, List

import pytest

from maltego.pagination import PageBasedPaginator, OffsetLimitPaginator
from maltego.pagination.pagination import PaginationState
from maltego.util import IntegrationClient


TEST_URL = "http://test.com"
TEST_PARAMS = {"filter": "name__icontains=test"}
TEST_HEADERS = {"Authorization": "Bearer XXXX"}
TEST_JSON = {"payload": True}


@pytest.fixture()
def pagination_state() -> PaginationState:
    return PaginationState(
        url=TEST_URL, params=TEST_PARAMS, headers=TEST_HEADERS, json=TEST_JSON
    )


@pytest.fixture()
def pagination_state_with_offset_limit() -> PaginationState:
    params = TEST_PARAMS.copy()
    params["offset"] = 0
    params["limit"] = 100
    return PaginationState(
        url=TEST_URL, params=params, headers=TEST_HEADERS, json=TEST_JSON
    )


@pytest.fixture()
def pagination_state_with_page() -> PaginationState:
    params = TEST_PARAMS.copy()
    params["page"] = 1
    params["limit"] = 100
    return PaginationState(
        url=TEST_URL, params=params, headers=TEST_HEADERS, json=TEST_JSON
    )


def response_to_items() -> List[Any]:
    return []


@pytest.fixture()
def offset_limit_paginator() -> OffsetLimitPaginator[Any]:
    client = IntegrationClient()
    return OffsetLimitPaginator(client, response_to_items, 100, max_pages=5)


@pytest.fixture()
def page_based_paginator() -> PageBasedPaginator[Any]:
    client = IntegrationClient()
    return PageBasedPaginator(client, response_to_items, 100, max_pages=5)
