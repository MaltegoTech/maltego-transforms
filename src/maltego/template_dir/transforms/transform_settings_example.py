# Copyright (c) Maltego Technologies GmbH.
"""
Transform-settings reference example
=====================================

This module demonstrates ALL 13 TransformSetting types, required vs optional
settings, popup vs persistent settings, and global settings shared across
multiple transforms.

Setting types (TransformSetting.Types):
  Primitive  : str, int, float, boolean
  Date/time  : date, datetime, datetime_range
  Lists      : str_list, int_list, float_list, boolean_list, date_list

Run this file directly (``python transform_settings_example.py``) to start a
local server.  Or import it alongside the other example modules in ``project.py``.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from maltego.entities import Phrase
from maltego.model.context import MaltegoContext
from maltego.server import (
    MaltegoServerSettings,
    TransformSetting,
    daterange,
    register_transform,
    run_server,
)

# ---------------------------------------------------------------------------
# Module-level TransformSetting constants
# ---------------------------------------------------------------------------
# Defining settings as module-level constants lets you share and reuse them
# across multiple transforms without duplicating the definition.  This is the
# recommended pattern for any setting that appears on more than one transform.

# A global setting — one stored value shared across every transform in the
# same server namespace.  ``is_global=True`` means Maltego stores the value
# under ``global#{ns}.api_key`` and broadcasts it to every transform that
# declares it.
GLOBAL_API_KEY = TransformSetting(
    name="api_key",
    display_name="API Key",
    type=TransformSetting.Types.str,
    optional=False,   # required: the transform will not run without this value
    auth=True,        # marks the setting as authentication-related
    popup=True,       # enforce the popup dialog on every execution
    is_global=True,   # share one stored value across all transforms in the namespace
)

# A second global setting — also available to multiple transforms.  The
# ``is_global_setting=True`` flag is the *deprecated* predecessor of
# ``is_global=True`` (kept for compatibility with older client deployments).
# Do NOT use it in new code; prefer ``is_global=True``.
# LEGACY_GLOBAL = TransformSetting(
#     name="workspace_id",
#     display_name="Workspace",
#     is_global_setting=True,  # deprecated — use is_global=True for new code
# )

# ``use_raw_name=True`` skips all namespace prefixing and sends ``name``
# exactly as given.  Use this when you must match a pre-existing setting name
# already stored by the Maltego client (e.g. a setting distributed by an
# earlier version of your integration).
# RAW_NAMED = TransformSetting(
#     name="acme.legacy.token",
#     display_name="Legacy Token",
#     use_raw_name=True,
# )

# ``is_oauth=True`` identifies the token injected by the SDK's OAuth machinery.
# In normal usage you do NOT create this setting manually — the SDK creates it
# when you pass ``authenticator=`` to ``register_transform``.  It is shown here
# only for documentation purposes.
# OAUTH_TOKEN = TransformSetting(
#     name="<token-field-name>",
#     display_name="OAuth Token",
#     auth=True,
#     popup=False,
#     is_oauth=True,
# )

TRANSFORM_SET = "Settings Reference [New Maltego Integration]"


# ---------------------------------------------------------------------------
# B1 / B2 — All 13 setting types in one transform
# ---------------------------------------------------------------------------
@register_transform(
    display_name="All 13 Setting Types Demo [New Maltego Integration]",
    description=(
        "Demonstrates every TransformSetting type: "
        "str, int, float, boolean, date, datetime, datetime_range (absolute + relative), "
        "str_list, int_list, float_list, boolean_list, date_list."
    ),
    transform_set=TRANSFORM_SET,
    settings=[
        # ------------------------------------------------------------------ #
        # 1. str — free-text string
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="str_setting",
            display_name="Text Input",
            type=TransformSetting.Types.str,
            default_value="hello world",
            optional=True,   # optional: the transform still runs if the user leaves it blank
            popup=False,     # persistent: Maltego remembers the value between executions
        ),
        # ------------------------------------------------------------------ #
        # 2. int — integer number
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="int_setting",
            display_name="Max Results",
            type=TransformSetting.Types.int,
            default_value=25,
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 3. float — floating-point / double
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="float_setting",
            display_name="Confidence Threshold",
            type=TransformSetting.Types.float,
            default_value=0.75,
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 4. boolean — true / false toggle
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="boolean_setting",
            display_name="Include Archived",
            type=TransformSetting.Types.boolean,
            default_value=False,
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 5. date — calendar date (no time component)
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="date_setting",
            display_name="Reference Date",
            type=TransformSetting.Types.date,
            default_value=date(2024, 1, 1),
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 6. datetime — date + time (UTC)
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="datetime_setting",
            display_name="Start Timestamp",
            type=TransformSetting.Types.datetime,
            default_value=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 7. datetime_range — date/time range, relative OR absolute
        #
        # Relative range: pass ``date_range=daterange.Ranges.<member>``
        # Absolute range: pass ``start=`` and ``end=`` with date or datetime
        # objects (must both be set; mixing date and datetime is allowed).
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="relative_range_setting",
            display_name="Relative Time Window",
            type=TransformSetting.Types.datetime_range,
            # Relative: one of the 25 named daterange.Ranges members
            default_value=daterange(date_range=daterange.Ranges.last_7_days),
            optional=True,
            popup=True,   # popup: ask the user to confirm the value on every run
        ),
        TransformSetting(
            name="absolute_range_setting",
            display_name="Absolute Date Range",
            type=TransformSetting.Types.datetime_range,
            # Absolute: explicit start/end dates — set both or neither
            default_value=daterange(
                start=date(2024, 1, 1),
                end=date(2024, 3, 31),
            ),
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 8. str_list — list of strings
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="str_list_setting",
            display_name="Tags",
            type=TransformSetting.Types.str_list,
            default_value=["threat-intel", "osint"],
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 9. int_list — list of integers
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="int_list_setting",
            display_name="Port Numbers",
            type=TransformSetting.Types.int_list,
            default_value=[80, 443, 8080],
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 10. float_list — list of floats
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="float_list_setting",
            display_name="Score Thresholds",
            type=TransformSetting.Types.float_list,
            default_value=[0.5, 0.75, 0.9],
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 11. boolean_list — list of booleans
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="boolean_list_setting",
            display_name="Feature Flags",
            type=TransformSetting.Types.boolean_list,
            default_value=[True, False, True],
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 12. date_list — list of calendar dates
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="date_list_setting",
            display_name="Milestone Dates",
            type=TransformSetting.Types.date_list,
            default_value=[date(2024, 3, 15), date(2024, 6, 30)],
            optional=True,
            popup=False,
        ),
        # ------------------------------------------------------------------ #
        # 13. auth (str) — API key or password
        # ``auth=True`` tells the Maltego client to treat this field as a
        # credential (masked input, separate credential store).  Combine with
        # ``optional=False`` to make the credential mandatory.
        # ------------------------------------------------------------------ #
        TransformSetting(
            name="auth_token",
            display_name="Bearer Token",
            type=TransformSetting.Types.str,
            optional=False,  # required: without this the transform will not execute
            auth=True,       # authentication-related credential
            popup=True,      # always prompt the user to confirm/enter the value
        ),
    ],
)
async def all_setting_types_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    Demonstrates accessing every one of the 13 setting types at runtime.

    The ``settings`` dict is keyed by the **original** ``name`` you passed to
    ``TransformSetting``, regardless of how the name is serialized in the
    discovery payload.  Values are already deserialized to the appropriate
    Python type (str, int, float, bool, date, datetime, daterange, or list).
    """
    # Primitives
    text: Optional[str] = settings.get("str_setting")
    max_results: Optional[int] = settings.get("int_setting")
    threshold: Optional[float] = settings.get("float_setting")
    include_archived: Optional[bool] = settings.get("boolean_setting")

    # Date/time types
    ref_date: Optional[date] = settings.get("date_setting")
    start_ts: Optional[datetime] = settings.get("datetime_setting")
    rel_window: Optional[daterange] = settings.get("relative_range_setting")
    abs_window: Optional[daterange] = settings.get("absolute_range_setting")

    # List types
    tags: List[str] = settings.get("str_list_setting") or []
    ports: List[int] = settings.get("int_list_setting") or []
    scores: List[float] = settings.get("float_list_setting") or []
    flags: List[bool] = settings.get("boolean_list_setting") or []
    milestones: List[date] = settings.get("date_list_setting") or []

    # Required auth credential
    auth_token: Optional[str] = settings.get("auth_token")

    context.log.inform(
        f"text={text!r}  max_results={max_results}  threshold={threshold}  "
        f"include_archived={include_archived}  ref_date={ref_date}  "
        f"start_ts={start_ts}  rel_window={rel_window}  abs_window={abs_window}"
    )
    context.log.inform(
        f"tags={tags}  ports={ports}  scores={scores}  "
        f"flags={flags}  milestones={milestones}"
    )

    result = Phrase(f"Processed: {input_entity.value}")
    result.set_property("has_auth_token", str(bool(auth_token)), display_name="Has Auth Token")
    result.set_property("tag_count", str(len(tags)), display_name="Tag Count")
    result.set_property("port_count", str(len(ports)), display_name="Port Count")
    result.set_property(
        "rel_window",
        str(rel_window) if rel_window else "not set",
        display_name="Relative Window",
    )
    result.set_property(
        "abs_window",
        str(abs_window) if abs_window else "not set",
        display_name="Absolute Window",
    )
    return result


# ---------------------------------------------------------------------------
# Required vs optional — dedicated example
# ---------------------------------------------------------------------------
# ``optional=False`` means the Maltego client will block execution if the user
# has not supplied a value.  ``optional=True`` (the default) allows the
# transform to run even when the value is absent; your code receives ``None``.
@register_transform(
    display_name="Required vs Optional Settings [New Maltego Integration]",
    description=(
        "Shows the difference between required (optional=False) "
        "and optional (optional=True) settings."
    ),
    transform_set=TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="required_query",
            display_name="Search Query",
            type=TransformSetting.Types.str,
            optional=False,  # required — Maltego won't run the transform without this
        ),
        TransformSetting(
            name="optional_limit",
            display_name="Result Limit",
            type=TransformSetting.Types.int,
            default_value=10,
            optional=True,   # optional — falls back to default_value if absent
        ),
    ],
)
async def required_vs_optional_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    required_query is guaranteed to be present (non-None) because
    optional=False blocks execution when it is absent.

    optional_limit may be None if the user clears the value; always provide
    a fallback when reading optional settings.
    """
    query: str = settings["required_query"]          # safe: guaranteed present
    limit: int = settings.get("optional_limit") or 10  # safe: provide fallback

    context.log.inform(f"query={query!r}  limit={limit}")
    return Phrase(f"Query: {query} (limit: {limit})")


# ---------------------------------------------------------------------------
# Popup vs persistent — dedicated example
# ---------------------------------------------------------------------------
# ``popup=True``  → Maltego opens the settings dialog on EVERY execution.
#                   Use for values that change run-to-run (time windows, queries).
# ``popup=False`` → Maltego remembers the last value; the dialog is skipped.
#                   Use for stable configuration (API keys stored in the
#                   credential store, server URLs, static filter flags).
@register_transform(
    display_name="Popup vs Persistent Settings [New Maltego Integration]",
    description=(
        "Illustrates popup=True (ask on every run) vs popup=False (remember value)."
    ),
    transform_set=TRANSFORM_SET,
    settings=[
        TransformSetting(
            name="search_window",
            display_name="Search Window",
            type=TransformSetting.Types.datetime_range,
            default_value=daterange(date_range=daterange.Ranges.last_24_hours),
            optional=True,
            popup=True,   # popup: user confirms the time window every time
        ),
        TransformSetting(
            name="api_endpoint",
            display_name="API Endpoint URL",
            type=TransformSetting.Types.str,
            default_value="https://api.example.com",
            optional=False,
            popup=False,  # persistent: stored once, reused silently on subsequent runs
        ),
    ],
)
async def popup_vs_persistent_demo(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    search_window pops up every execution so the user can adjust the time range.
    api_endpoint is entered once and silently reused on subsequent runs.
    """
    window: Optional[daterange] = settings.get("search_window")
    endpoint: Optional[str] = settings.get("api_endpoint")

    context.log.inform(f"window={window}  endpoint={endpoint}")
    return Phrase(
        f"Searching {endpoint} in window: {window if window else 'all time'}"
    )


# ---------------------------------------------------------------------------
# Global settings shared across two transforms
# ---------------------------------------------------------------------------
# GLOBAL_API_KEY is defined once at module level (above).  Both transforms
# below declare it, so the Maltego client stores ONE value under
# ``global#{ns}.api_key`` and presents the same credential to both.
@register_transform(
    display_name="Global Setting — Transform A [New Maltego Integration]",
    description="First transform that uses the shared global API key.",
    transform_set=TRANSFORM_SET,
    settings=[GLOBAL_API_KEY],
)
async def global_setting_transform_a(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    Reads the shared api_key.  The SDK strips the ``global#…`` prefix during
    execution, so we always read via the original ``name`` ("api_key").
    """
    api_key: Optional[str] = settings.get("api_key")
    return Phrase(f"Transform A — has key: {bool(api_key)} — input: {input_entity.value}")


@register_transform(
    display_name="Global Setting — Transform B [New Maltego Integration]",
    description="Second transform that reuses the same global API key.",
    transform_set=TRANSFORM_SET,
    settings=[GLOBAL_API_KEY],
)
async def global_setting_transform_b(
    input_entity: Phrase,
    settings: Dict[str, Any],
    context: MaltegoContext,
) -> Phrase:
    """
    Same GLOBAL_API_KEY constant — the user enters the credential once and
    both transforms share it automatically.
    """
    api_key: Optional[str] = settings.get("api_key")
    return Phrase(f"Transform B — has key: {bool(api_key)} — input: {input_entity.value}")


if __name__ == "__main__":
    server_settings = MaltegoServerSettings(
        server_name="Settings Reference Server",
        ns="acme",
        author="Acme",
    )
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=False,
        settings=server_settings,
        log_level="INFO",
    )
