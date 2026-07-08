import asyncio
from typing import Optional

from maltego.entities import Phrase

from maltego.model.exception import (
    MaltegoException,
    MaltegoHTTPDataProviderAPIKeyInvalid,
    MaltegoHTTPDataProviderNotFound,
    MaltegoHTTPDataProviderUnavailable,
    MaltegoHTTPUnauthorized,
    MaltegoTransformTimeoutError,
)
from maltego.server import IntegrationClient, MaltegoContext, register_transform

TRANSFORM_SET = "New Maltego Integration"

# Shared client for API calls
client = IntegrationClient()


@register_transform(
    display_name="MaltegoException Demo [New Maltego Integration]",
    description="Shows how to raise user-visible errors with MaltegoException",
    transform_set=TRANSFORM_SET,
)
async def maltego_exception_demo(
    input_entity: Phrase, context: MaltegoContext
) -> Phrase:
    """
    Demonstrates MaltegoException for user-visible error messages.
    """
    context.log.inform("Validating input...")

    # Example: Validate that input is numeric
    if not input_entity.value.isnumeric():
        raise MaltegoException(
            "Invalid input: Expected a numeric value. "
            f"Got '{input_entity.value}' instead."
        )

    return Phrase(f"Valid number: {input_entity.value}")


@register_transform(
    display_name="Timeout Error Demo [New Maltego Integration]",
    description="Shows how to handle and raise timeout errors",
    transform_set=TRANSFORM_SET,
)
async def timeout_error_demo(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    """
    Demonstrates MaltegoTransformTimeoutError for timeout situations.

    Use MaltegoTransformTimeoutError when:
    - An external API call times out
    - A long-running operation exceeds limits
    - You want to indicate a timeout-specific failure
    """
    context.log.inform("Simulating a long operation...")

    # Simulate timeout condition
    if input_entity.value.lower() == "slow":
        context.log.partial("Operation taking too long...")
        await asyncio.sleep(1)
        raise MaltegoTransformTimeoutError(
            "Operation timed out after waiting too long. "
            "Try again with a smaller dataset."
        )

    return Phrase(f"Completed: {input_entity.value}")


@register_transform(
    display_name="API Error Handling [New Maltego Integration]",
    description="Shows how to handle API errors",
    transform_set=TRANSFORM_SET,
)
async def api_error_handling_demo(
    input_entity: Phrase, context: MaltegoContext
) -> Optional[Phrase]:
    """
    Demonstrates error handling for API calls.
    """
    url = f"https://httpbin.org/status/{input_entity.value}"

    context.log.inform("Making API request to test error handling...")
    context.log.debug("Prepared test API request")

    try:
        response = await client.get(url, context)
        return Phrase(f"Success: Status {response.status_code}")

    except MaltegoHTTPDataProviderNotFound:
        # 404 - Resource not found (silent failure, just return nothing)
        context.log.inform("Resource not found")
        return None

    except MaltegoHTTPDataProviderAPIKeyInvalid:
        # 401 Unauthorized - Re-raise to preserve exception type
        raise

    except MaltegoHTTPUnauthorized:
        # 403 Forbidden - Re-raise to preserve exception type
        raise

    except MaltegoHTTPDataProviderUnavailable:
        # 5xx, timeouts, connection failures - re-raise
        raise

    except MaltegoException as e:
        # Catch-all for other errors (400, 429, etc.)
        # Re-raise with user-friendly message, or return None for silent failure
        context.log.fatal(f"Error: {e.message}")
        return None


@register_transform(
    display_name="Graceful Degradation [New Maltego Integration]",
    description="Shows how to handle errors while still returning partial results",
    transform_set=TRANSFORM_SET,
)
async def graceful_degradation_demo(
    input_entity: Phrase, context: MaltegoContext
) -> list[Phrase]:
    """
    Demonstrates returning partial results when some operations fail.

    Best practice: Don't fail the entire transform if only some
    operations fail. Log errors and return what you can.
    """
    urls = [
        "https://httpbin.org/get",
        "https://httpbin.org/status/404",  # Will fail
        "https://httpbin.org/ip",
        "https://invalid.example.test",  # Will fail
    ]

    results = []
    errors = []

    for i, url in enumerate(urls, 1):
        context.log.partial(f"Fetching {i}/{len(urls)}...")

        try:
            response = await client.get(url, context)
            results.append(Phrase(f"Success: request {i}"))
        except MaltegoException as e:
            errors.append(i)
            context.log.debug(f"Failed to fetch request {i}: {e.message}")

    if errors:
        context.log.fatal(f"Failed to fetch {len(errors)} requests")

    context.log.inform(
        f"Completed with {len(results)} successes, {len(errors)} failures"
    )

    return results


@register_transform(
    display_name="Unhandled Exception Demo [New Maltego Integration]",
    description="Shows what happens with unhandled exceptions",
    transform_set=TRANSFORM_SET,
)
async def unhandled_exception_demo(
    input_entity: Phrase, context: MaltegoContext
) -> Phrase:
    """
    Demonstrates unhandled exceptions.

    Unhandled exceptions (like ValueError, KeyError, etc.)
    will show a generic error message to the user, hiding the actual
    error details for security reasons.

    Always catch exceptions and raise MaltegoException with a
    user-friendly message if you want users to see the error.
    """
    context.log.inform("This transform will raise an unhandled exception...")

    # This will show a generic message to users
    # The actual error is logged server-side but not shown to users
    if input_entity.value == "crash":
        # BAD: Generic error message shown to user
        raise ValueError("This is an internal error the user won't see")

    # GOOD: User-friendly error message
    if input_entity.value == "error":
        raise MaltegoException("Something went wrong. Please try again later.")

    return Phrase(input_entity.value)


if __name__ == "__main__":
    from maltego.server import MaltegoServerSettings, run_server

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
