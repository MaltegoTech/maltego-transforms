import asyncio
from typing import List

from maltego.entities import Phrase

from maltego.server import MaltegoContext, register_transform

TRANSFORM_SET = "New Maltego Integration"


@register_transform(
    display_name="Logging Demo [New Maltego Integration]",
    description="Demonstrates all four logging methods",
    transform_set=TRANSFORM_SET,
)
async def logging_demo(input_entity: Phrase, context: MaltegoContext) -> Phrase:
    """
    Demonstrates logging methods.
    """
    # Informational message - general status updates
    context.log.inform("Starting transform execution...")

    # Debug message - detailed technical information
    context.log.debug("Input entity value received; do not log raw user input")
    context.log.debug(f"Input entity type: {type(input_entity).__name__}")

    # Simulate some work with progress updates
    context.log.partial("Processing step 1 of 3...")
    await asyncio.sleep(0.5)

    context.log.partial("Processing step 2 of 3...")
    await asyncio.sleep(0.5)

    context.log.partial("Processing step 3 of 3...")
    await asyncio.sleep(0.5)

    context.log.inform("Transform completed successfully!")

    return Phrase(f"Processed: {input_entity.value}")


@register_transform(
    display_name="Progress Tracking [New Maltego Integration]",
    description="Shows how to report progress during batch processing",
    transform_set=TRANSFORM_SET,
)
async def progress_tracking_example(
    input_entity: Phrase, context: MaltegoContext
) -> List[Phrase]:
    """
    Demonstrates progress tracking for batch operations.
    """
    items_to_process = ["item1", "item2", "item3", "item4", "item5"]
    total = len(items_to_process)
    results = []

    context.log.inform(f"Processing {total} items...")

    for i, item in enumerate(items_to_process, 1):
        # Show progress percentage
        context.log.partial(f"Processing {item}... ({i}/{total} - {i * 100 // total}%)")

        # Simulate work
        await asyncio.sleep(0.3)
        results.append(Phrase(f"Result: {item}"))

    context.log.inform(f"Completed processing {total} items")

    return results


@register_transform(
    display_name="Error Logging Demo [New Maltego Integration]",
    description="Shows that fatal() logs errors but transform continues",
    transform_set=TRANSFORM_SET,
)
async def error_logging_demo(
    input_entity: Phrase, context: MaltegoContext
) -> List[Phrase]:
    """
    Demonstrates that fatal() logs errors but doesn't stop the transform.

    IMPORTANT: context.log.fatal() only logs an error message - it does NOT
    stop transform execution, you can still return entities after logging errors.

    Use fatal() to report errors while still returning partial results.
    """
    items = ["success1", "fail", "success2", "error", "success3"]
    results = []
    errors = 0

    context.log.inform(f"Processing {len(items)} items...")

    for item in items:
        if item in ("fail", "error"):
            # Log the error - but transform keeps running!
            context.log.fatal(f"Failed to process '{item}'")
            errors += 1
        else:
            results.append(Phrase(f"Processed: {item}"))

    # Even after fatal() calls, we still return successful results
    context.log.inform(f"Completed: {len(results)} succeeded, {errors} failed")

    return results  # Returns 3 entities despite 2 errors


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
