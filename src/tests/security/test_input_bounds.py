# Copyright (c) Maltego Technologies GmbH.
"""
Tests for PRP 5 — Input bounds & resource limits.

Covers:
  F43 — unbounded date parsing (length cap in parse_str_type_to_value and coerce_property_type_from_value)
  F35 — concurrency middleware AssertionError → 500 (graceful None handling)
  F46 — ReDoS guard (input-length cap in PropertyMatchesRegex subclasses)

(F52 — per-user concurrency cap opt-in default — is a settings-field default,
 covered in unit/test_config.py.)
"""
import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from maltego.model.context import MaltegoContext
from maltego.model.entity import (
    _DATE_VALUE_MAX_LEN,
    _assert_date_str_len,
    coerce_property_type_from_value,
    parse_str_type_to_value,
)
from maltego.model.entity.property import _MaltegoEntityProperty
from maltego.model.graph import MaltegoGraph
from maltego.model.input_constraints.property.regex import (
    _REGEX_INPUT_MAX_LEN,
    PropertyValueMatchesRegex,
    PropertyDisplayNameMatchesRegex,
    PropertyNameMatchesRegex,
)
from maltego.middlewares.user_concurrency_limit_middleware import (
    BoundedSemaphoreWithMax,
    LimitExceededError,
    UserConcurrencyLimitMiddleware,
)
from maltego.model.types import daterange

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# F43 — date-value length cap
# ---------------------------------------------------------------------------

class TestF43DateLengthCap:

    def test_cap_constant_is_64(self):
        assert _DATE_VALUE_MAX_LEN == 64

    def test_assert_date_str_len_accepts_valid_length(self):
        # 64-char ISO string is fine
        value = "2024-01-15T12:00:00.000000"  # 26 chars — well within limit
        _assert_date_str_len(value, "DATE_TIME")  # should not raise

    def test_assert_date_str_len_rejects_overlong(self):
        value = "A" * 65
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            _assert_date_str_len(value, "DATE_TIME")

    def test_assert_date_str_len_accepts_exactly_64(self):
        # Exactly at limit should be accepted
        value = "A" * 64
        _assert_date_str_len(value, "DATE")  # should not raise

    def test_parse_str_type_to_value_datetime_overlong_rejected(self):
        overlong = "2024-01-15 " + "x" * 60  # > 64 chars
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            parse_str_type_to_value(overlong, "DATE_TIME")

    def test_parse_str_type_to_value_date_overlong_rejected(self):
        overlong = "2024-01-15 " + "x" * 60
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            parse_str_type_to_value(overlong, "DATE")

    def test_parse_str_type_to_value_daterange_overlong_rejected(self):
        overlong = "2024-01-01/" + "x" * 60
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            parse_str_type_to_value(overlong, "DATE_RANGE")

    def test_parse_str_type_to_value_datetime_valid_parses(self):
        result = parse_str_type_to_value("2024-01-15T12:00:00", "DATE_TIME")
        assert isinstance(result, datetime.datetime)

    def test_parse_str_type_to_value_date_valid_parses(self):
        result = parse_str_type_to_value("2024-01-15", "DATE")
        assert isinstance(result, datetime.date)

    def test_parse_str_type_to_value_list_items_each_bounded(self):
        overlong = "2024-01-15 " + "x" * 60
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            parse_str_type_to_value([overlong], "DATE_TIME")

    def test_coerce_datetime_overlong_rejected(self):
        overlong = "2024-01-15 " + "x" * 60
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            coerce_property_type_from_value(overlong, datetime.datetime)

    def test_coerce_date_overlong_rejected(self):
        overlong = "2024-01-15 " + "x" * 60
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            coerce_property_type_from_value(overlong, datetime.date)

    def test_coerce_datetime_valid_parses(self):
        result = coerce_property_type_from_value("2024-06-01T00:00:00", datetime.datetime)
        assert isinstance(result, datetime.datetime)

    def test_coerce_date_valid_parses(self):
        result = coerce_property_type_from_value("2024-06-01", datetime.date)
        assert isinstance(result, datetime.date)

    def test_pathological_dateutil_string_rejected(self):
        # dateutil.parser.parse is known to be slow on strings with many tokens
        # separated by ambiguous separators; ensure we cap before reaching it.
        pathological = ("Jan " * 20)[:65]  # > 64 chars
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            parse_str_type_to_value(pathological, "DATE_TIME")


# ---------------------------------------------------------------------------
# F35 — concurrency middleware graceful handling (no AssertionError → 500)
# ---------------------------------------------------------------------------

class TestF35ConcurrencyMiddlewareGraceful:

    def _make_context(self, remote_ip: str = "1.2.3.4", api_key: str = "key") -> MaltegoContext:
        request = Request({"type": "http", "headers": []})
        ctx = MaltegoContext(graph=MaltegoGraph(), request=request)
        ctx.remote_ip = remote_ip
        ctx.api_key = api_key
        return ctx

    @pytest.mark.asyncio
    async def test_middleware_acquire_and_release_no_error(self):
        """Normal acquire/release cycle completes without exception."""
        middleware = UserConcurrencyLimitMiddleware(max_concurrent_transforms=2)
        ctx = self._make_context()

        await middleware.before_transform(
            transform=None, transform_input=None, properties=None,
            context=ctx, soft_limit=None, hard_limit=None
        )
        await middleware.after_transform(
            transform=None, transform_input=None, output_entities=[],
            context=ctx, state=None, exceptions=None
        )

    @pytest.mark.asyncio
    async def test_after_transform_with_no_semaphore_does_not_500(self):
        """after_transform with missing semaphore should log and return, not raise."""
        middleware = UserConcurrencyLimitMiddleware(max_concurrent_transforms=2)
        ctx = self._make_context(remote_ip="9.9.9.9")
        # Do NOT call before_transform — no semaphore exists for this key.
        # Should not raise AssertionError or KeyError.
        await middleware.after_transform(
            transform=None, transform_input=None, output_entities=[],
            context=ctx, state=None, exceptions=None
        )

    @pytest.mark.asyncio
    async def test_after_transform_with_our_concurrency_exception_returns_gracefully(self):
        """ConcurrencyLimitException from this middleware skips release without crashing."""
        middleware = UserConcurrencyLimitMiddleware(max_concurrent_transforms=1)
        ctx = self._make_context()
        limit_key = f"{ctx.remote_ip}_{ctx.api_key}"

        exc = middleware.ConcurrencyLimitException(
            limiter_id=middleware._id, limitee=limit_key
        )
        # Should not raise
        await middleware.after_transform(
            transform=None, transform_input=None, output_entities=[],
            context=ctx, state=None, exceptions=[exc]
        )

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self):
        """A third concurrent request beyond the limit raises ConcurrencyLimitException."""
        middleware = UserConcurrencyLimitMiddleware(max_concurrent_transforms=1)
        ctx = self._make_context()

        # Acquire once (fills the semaphore)
        await middleware.before_transform(
            transform=None, transform_input=None, properties=None,
            context=ctx, soft_limit=None, hard_limit=None
        )
        # Second attempt should raise
        with pytest.raises(middleware.ConcurrencyLimitException):
            await middleware.before_transform(
                transform=None, transform_input=None, properties=None,
                context=ctx, soft_limit=None, hard_limit=None
            )

        # Clean up
        await middleware.after_transform(
            transform=None, transform_input=None, output_entities=[],
            context=ctx, state=None, exceptions=None
        )

    @pytest.mark.asyncio
    async def test_bounded_semaphore_none_waiters_no_assertion_error(self):
        """BoundedSemaphoreWithMax.acquire() must not raise AssertionError when _waiters is None."""
        sem = BoundedSemaphoreWithMax(value=2, max_waiters=0)
        # Simulate _waiters being None (as it is before any contention)
        sem._waiters = None  # type: ignore[attr-defined]
        # Should not raise AssertionError — just a normal acquire on an un-locked semaphore
        await sem.acquire()
        sem.release()

    @pytest.mark.asyncio
    async def test_bounded_semaphore_locked_with_none_waiters_raises_limit_error(self):
        """With max_waiters=0, a locked semaphore with _waiters=None must raise LimitExceededError, not hang."""
        sem = BoundedSemaphoreWithMax(value=1, max_waiters=0)
        # Drain the semaphore manually so it's locked but _waiters is still None
        sem._value = 0  # type: ignore[attr-defined]
        sem._waiters = None  # type: ignore[attr-defined]
        with pytest.raises(LimitExceededError):
            await sem.acquire()


# ---------------------------------------------------------------------------
# F46 — ReDoS guard (input-length cap)
# ---------------------------------------------------------------------------

def _make_prop(value: Any = None, display_name: str = "", name: str = "") -> _MaltegoEntityProperty:
    prop = MagicMock(spec=_MaltegoEntityProperty)
    prop.value = value
    prop.display_name = display_name
    prop.name = name
    return prop


class TestF46RegexInputLengthCap:

    def test_cap_constant_is_1024(self):
        assert _REGEX_INPUT_MAX_LEN == 1024

    # PropertyValueMatchesRegex

    def test_value_regex_evaluate_short_matches(self):
        c = PropertyValueMatchesRegex(regex=r"^hello$")
        prop = _make_prop(value="hello")
        assert c.evaluate(prop) is True

    def test_value_regex_evaluate_overlong_rejected_false(self):
        c = PropertyValueMatchesRegex(regex=r".*")
        prop = _make_prop(value="A" * 1025)
        # Should return False, not hang or raise
        assert c.evaluate(prop) is False

    def test_value_regex_evaluate_with_hierarchy_overlong_returns_failure(self):
        c = PropertyValueMatchesRegex(regex=r".*")
        prop = _make_prop(value="A" * 1025)
        result = c.evaluate_with_hierarchy(prop)
        assert result.success is False
        assert "maximum allowed length" in result.message

    def test_value_regex_evaluate_with_hierarchy_short_matches(self):
        c = PropertyValueMatchesRegex(regex=r"^test$")
        prop = _make_prop(value="test")
        result = c.evaluate_with_hierarchy(prop)
        assert result.success is True

    def test_value_regex_evaluate_exactly_at_limit_passes_to_regex(self):
        # 1024-char string starting with 'A' against /^A/ — should match
        c = PropertyValueMatchesRegex(regex=r"^A")
        prop = _make_prop(value="A" * 1024)
        assert c.evaluate(prop) is True

    # PropertyDisplayNameMatchesRegex

    def test_display_name_regex_evaluate_overlong_rejected(self):
        c = PropertyDisplayNameMatchesRegex(regex=r".*")
        prop = _make_prop(display_name="B" * 1025)
        assert c.evaluate(prop) is False

    def test_display_name_regex_evaluate_with_hierarchy_overlong_failure(self):
        c = PropertyDisplayNameMatchesRegex(regex=r".*")
        prop = _make_prop(display_name="B" * 1025)
        result = c.evaluate_with_hierarchy(prop)
        assert result.success is False
        assert "maximum allowed length" in result.message

    def test_display_name_regex_evaluate_short_matches(self):
        c = PropertyDisplayNameMatchesRegex(regex=r"^Name$")
        prop = _make_prop(display_name="Name")
        assert c.evaluate(prop) is True

    # PropertyNameMatchesRegex

    def test_property_name_regex_evaluate_overlong_rejected(self):
        c = PropertyNameMatchesRegex(regex=r".*")
        prop = _make_prop(name="C" * 1025)
        assert c.evaluate(prop) is False

    def test_property_name_regex_evaluate_with_hierarchy_overlong_failure(self):
        c = PropertyNameMatchesRegex(regex=r".*")
        prop = _make_prop(name="C" * 1025)
        result = c.evaluate_with_hierarchy(prop)
        assert result.success is False
        assert "maximum allowed length" in result.message

    def test_property_name_regex_evaluate_short_matches(self):
        c = PropertyNameMatchesRegex(regex=r"^prop_name$")
        prop = _make_prop(name="prop_name")
        assert c.evaluate(prop) is True

    def test_pathological_redos_input_bounded(self):
        # Classic catastrophic backtracking pattern: (a+)+ against "aaa...!".
        # Without the length cap this would be extremely slow on long inputs.
        c = PropertyValueMatchesRegex(regex=r"^(a+)+$")
        # Pathological input (1025 chars) — must return quickly, not hang
        prop = _make_prop(value="a" * 1024 + "!")
        # The input is 1025 chars so it's beyond the cap — should return False fast
        result = c.evaluate(prop)
        assert result is False
