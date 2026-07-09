from html import escape
from typing import Any, Dict, List, Optional, Union

from httpx import Response
from maltego.entities import Image, Phrase

from maltego.model.context import MaltegoContext
from maltego.pagination import OffsetLimitPaginator, PageBasedPaginator
from maltego.server import (
    IntegrationClient,
    MaltegoServerSettings,
    register_transform,
    run_server,
)


def html_table(data: Dict[str, Any], title: Optional[str] = None) -> str:
    """
    Build an HTML table from a dictionary.

    Args:
        data: Dictionary of key-value pairs to display
        title: Optional title shown above the table

    Returns:
        HTML string with styled table
    """
    rows = []
    for key, value in data.items():
        if value is None or value == "":
            continue

        safe_key = escape(str(key))
        safe_value = escape(str(value))
        rows.append(
            f"<tr><td><strong>{safe_key}</strong></td><td>{safe_value}</td></tr>"
        )

    table_html = f'<table style="border-collapse: collapse; width: 100%;">{"".join(rows)}</table>'

    if title:
        return f"<h3>{escape(title)}</h3>{table_html}"
    return table_html


def html_link(url: str, text: Optional[str] = None) -> str:
    """
    Create a clickable HTML link.

    Args:
        url: The URL to link to
        text: Display text (defaults to URL if not provided)

    Returns:
        HTML anchor tag
    """
    safe_url = escape(url)
    safe_text = escape(text or url)
    return f'<a href="{safe_url}" target="_blank">{safe_text}</a>'


def html_list(items: List[Union[str, Dict[str, Any]]], ordered: bool = False) -> str:
    """
    Build an HTML list from items.

    Args:
        items: List of strings or dicts (dicts are converted to nested tables)
        ordered: Use ordered list (ol) if True, unordered (ul) if False

    Returns:
        HTML list string
    """
    tag = "ol" if ordered else "ul"
    list_items = []
    for item in items:
        if isinstance(item, dict):
            list_items.append(f"<li>{html_table(item)}</li>")
        else:
            list_items.append(f"<li>{escape(str(item))}</li>")
    return f"<{tag}>{''.join(list_items)}</{tag}>"


TRANSFORM_SET = "New Maltego Integration"

# Create a shared IntegrationClient for all transforms
client = IntegrationClient(
    max_concurrent=50,
    max_concurrent_per_key=6,
    max_calls_per_period=25,
    period_length_seconds=1.0,
    timeout=30,
)


def parse_dummyjson_products(
    response: Response, **kwargs: Any
) -> Optional[List[Dict[str, Any]]]:
    """Parse products from DummyJSON API."""
    try:
        data = response.json()
        return data.get("products", [])
    except Exception:
        return None


def parse_dummyjson_total(response: Response) -> int:
    """Get total product count from DummyJSON API."""
    try:
        data = response.json()
        return data.get("total", 0)
    except Exception:
        return 0


def parse_artic_artworks(
    response: Response, **kwargs: Any
) -> Optional[List[Dict[str, Any]]]:
    """Parse artworks from Art Institute of Chicago API."""
    try:
        data = response.json()
        return data.get("data", [])
    except Exception:
        return None


def parse_artic_total(response: Response) -> int:
    """Get total artwork count from Art Institute of Chicago API."""
    try:
        data = response.json()
        return data.get("pagination", {}).get("total", 0)
    except Exception:
        return 0


@register_transform(
    display_name="Fetch Products (Offset Pagination) [New Maltego Integration]",
    description="Fetch products from DummyJSON API using offset/limit pagination",
    transform_set=TRANSFORM_SET,
)
async def fetch_dummyjson_products(
    input_entity: Phrase,
    slider: int,
    context: MaltegoContext,
) -> List[Phrase]:
    """
    Fetch products from DummyJSON using offset/limit pagination.

    API: https://dummyjson.com/products?skip=0&limit=10

    DummyJSON uses 'skip' instead of 'offset', demonstrating how to
    customize parameter names for different APIs.
    """
    paginator: OffsetLimitPaginator[Dict[str, Any]] = OffsetLimitPaginator(
        client=client,
        response_to_items=parse_dummyjson_products,
        page_size=10,
        page_size_param_name="limit",
        offset_param_name="skip",  # DummyJSON uses 'skip' not 'offset'
        response_to_total_cnt=parse_dummyjson_total,
        max_pages=10,
    )

    context.log.inform(f"Fetching products from DummyJSON (max {slider} items)...")

    items = await paginator.fetch_all_items(
        slider=slider,
        context=context,
        url="https://dummyjson.com/products",
    )

    context.log.inform(f"Fetched {len(items)} products")

    # Convert to entities - truncate to slider limit for safety
    # (paginator may return slightly more than slider due to page boundaries)
    return [
        Phrase(f"{item.get('title', 'Unknown')} - ${item.get('price', 0)}")
        for item in items[:slider]
    ]


@register_transform(
    display_name="Fetch Artworks (Page Pagination) [New Maltego Integration]",
    description="Fetch artworks from Art Institute of Chicago API using page-based pagination",
    transform_set=TRANSFORM_SET,
)
async def fetch_artic_artworks(
    input_entity: Phrase,
    slider: int,
    context: MaltegoContext,
) -> List[Image]:
    """
    Fetch artworks from Art Institute of Chicago API using page-based pagination.

    API: https://api.artic.edu/api/v1/artworks?page=1&limit=12

    The Art Institute API supports page numbers and custom page sizes.
    Returns Image entities
    """
    paginator: PageBasedPaginator[Dict[str, Any]] = PageBasedPaginator(
        client=client,
        response_to_items=parse_artic_artworks,
        page_size=12,
        page_size_param_name="limit",
        page_param_name="page",
        page_start_num=1,
        response_to_total_cnt=parse_artic_total,
        max_pages=10,
    )

    context.log.inform("Fetching artworks from Art Institute of Chicago API...")

    items = await paginator.fetch_all_items(
        slider=slider,
        context=context,
        url="https://api.artic.edu/api/v1/artworks",
    )

    context.log.inform(f"Fetched {len(items)} artworks")

    # Convert to Image entities - truncate to slider limit for safety
    results = []
    for item in items[:slider]:
        image_id = item.get("image_id")
        if not image_id:
            continue

        title = item.get("title", "Untitled")
        artist = item.get("artist_display", "Unknown")

        # Full resolution image URL
        full_url = f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg"

        img = Image(title)
        img.url = full_url

        # Set basic properties
        img.set_property("artist", artist, display_name="Artist")
        img.set_property("date", item.get("date_display", ""), display_name="Date")
        img.set_property(
            "medium", item.get("medium_display", ""), display_name="Medium"
        )

        # Build HTML display field with artwork details
        details = {
            "Title": title,
            "Artist": artist,
            "Date": item.get("date_display"),
            "Medium": item.get("medium_display"),
            "Dimensions": item.get("dimensions"),
            "Department": item.get("department_title"),
            "Artwork Type": item.get("artwork_type_title"),
            "Credit Line": item.get("credit_line"),
        }

        html_content = ""
        html_content += html_table(details)
        html_content += f"<p>{html_link(full_url, 'View Image')}</p>"

        description = item.get("description")
        if description:
            # Escape API-sourced description before interpolating into HTML
            # to prevent stored XSS from untrusted response data.
            html_content += f"<h4>Description</h4>{escape(str(description))}"

        img.add_display_field_html("Artwork Details", html_content)
        results.append(img)

    return results


@register_transform(
    display_name="Stream Products (Pagination) [New Maltego Integration]",
    description="Stream products page-by-page for real-time feedback",
    transform_set=TRANSFORM_SET,
)
async def stream_dummyjson_products(
    input_entity: Phrase,
    slider: int,
    context: MaltegoContext,
):
    """
    Stream products from DummyJSON page-by-page using async generator.

    Note: The paginator yields full pages, so we track yielded count
    to respect the slider limit exactly.
    """
    paginator: OffsetLimitPaginator[Dict[str, Any]] = OffsetLimitPaginator(
        client=client,
        response_to_items=parse_dummyjson_products,
        page_size=10,
        page_size_param_name="limit",
        offset_param_name="skip",
        response_to_total_cnt=None,  # Sequential fetching for streaming
        max_pages=5,
    )

    page_num = 0
    yielded_count = 0  # Track how many entities we've yielded

    async for page_items in paginator.stream_all_items(
        slider=slider,
        context=context,
        url="https://dummyjson.com/products",
    ):
        page_num += 1
        context.log.inform(f"Page {page_num}: {len(page_items)} products")

        for item in page_items:
            if yielded_count >= slider:
                return  # Stop once we've hit the slider limit
            yield Phrase(f"{item.get('title', 'Unknown')} - ${item.get('price', 0)}")
            yielded_count += 1


if __name__ == "__main__":
    server_settings = MaltegoServerSettings(
        server_name="Maltego Transform Server", ns="acme", author="Acme"
    )
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=False,
        settings=server_settings,
        log_level="INFO",
    )
