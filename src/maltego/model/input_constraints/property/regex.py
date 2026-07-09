# Copyright (c) Maltego Technologies GmbH.
import re
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import Field, PrivateAttr

from maltego.model.entity.property import (
    _MaltegoEntityProperty as MaltegoEntityProperty,
)
from maltego.model.input_constraints.base import ConstraintResult, PropertyConstraint, extract_comparable_value

# ReDoS guard
# ─────────────────────────────────────────────────────────────────────────────
# Python's ``re`` module has no built-in match timeout, which means a
# pathological attacker-supplied *value* matched against a developer-authored
# pattern can spin indefinitely (ReDoS).  We apply an input-length cap as the
# primary defence: values longer than _REGEX_INPUT_MAX_LEN characters are
# rejected before the regex engine ever sees them.  This eliminates the attack
# surface for all patterns where the catastrophic back-tracking requires a
# long input string (the common case).
#
# Pattern authors should still write anchored, possessive-quantifier patterns
# where possible and avoid nested quantifiers over large character classes.
# The cap is enforced by PropertyMatchesRegex.evaluate() / evaluate_with_hierarchy()
# and applies uniformly to all three subclasses (value / display-name / name).
_REGEX_INPUT_MAX_LEN = 1024


class PropertyMatchesRegex(PropertyConstraint, ABC):
    """Base class for regex-based property constraints."""

    _compiled_regex: re.Pattern[str] = PrivateAttr()

    type: str = Field(..., frozen=True)
    regex: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        # Precompile regex
        self._compiled_regex = re.compile(self.regex)

    @staticmethod
    def _check_input_length(value: str) -> bool:
        """Return True if the value is within the safe length limit, False otherwise.

        Callers should treat False as a non-match (constraint not satisfied)
        rather than raising, to preserve existing API semantics.
        """
        return len(value) <= _REGEX_INPUT_MAX_LEN

    @abstractmethod
    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        pass


class PropertyValueMatchesRegex(PropertyMatchesRegex):
    type: Literal["property_value_matches_regex"] = "property_value_matches_regex"
    regex: str

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the regex against the property value. For entity-typed properties, extracts the main value."""
        raw_value = input_value.value
        if raw_value is None:
            return False

        # Extract comparable value for entity-typed properties
        extracted = extract_comparable_value(raw_value)
        compare_value = str(extracted) if extracted is not None else ""
        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(compare_value):
            return False
        return bool(self._compiled_regex.match(compare_value))

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the regex against the property value with hierarchical reporting. For entity-typed properties, extracts the main value."""
        raw_value = input_value.value

        if raw_value is None:
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message="Property value is None",
            )

        # Extract comparable value for entity-typed properties
        extracted = extract_comparable_value(raw_value)
        compare_value = str(extracted) if extracted is not None else ""

        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(compare_value):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property value exceeds maximum allowed length of {_REGEX_INPUT_MAX_LEN} characters.",
            )

        if self._compiled_regex.match(compare_value):
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property value '{compare_value}' matches regex pattern '{self.regex}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property value '{compare_value}' does not match regex pattern '{self.regex}'",
        )


class PropertyDisplayNameMatchesRegex(PropertyMatchesRegex):
    type: Literal["property_display_name_matches_regex"] = (
        "property_display_name_matches_regex"
    )
    regex: str

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the regex against the property display name."""
        compare_value = input_value.display_name
        if not compare_value:
            return False

        str_value = str(compare_value)
        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(str_value):
            return False
        return bool(self._compiled_regex.match(str_value))

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the regex against the property display name with hierarchical reporting."""
        compare_value = input_value.display_name

        if not compare_value:
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message="Property display name is empty or None",
            )

        str_value = str(compare_value)
        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(str_value):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name exceeds maximum allowed length of {_REGEX_INPUT_MAX_LEN} characters.",
            )

        if self._compiled_regex.match(str_value):
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{compare_value}' matches regex pattern '{self.regex}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property display name '{compare_value}' does not match regex pattern '{self.regex}'",
        )


class PropertyNameMatchesRegex(PropertyMatchesRegex):
    type: Literal["property_name_matches_regex"] = "property_name_matches_regex"
    regex: str

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the regex against the property name."""
        compare_value = input_value.name
        if not compare_value:
            return False

        str_value = str(compare_value)
        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(str_value):
            return False
        return bool(self._compiled_regex.match(str_value))

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the regex against the property name with hierarchical reporting."""
        compare_value = input_value.name

        if not compare_value:
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message="Property name is empty or None",
            )

        str_value = str(compare_value)
        # Reject inputs that exceed the safe length cap to prevent ReDoS
        if not self._check_input_length(str_value):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name exceeds maximum allowed length of {_REGEX_INPUT_MAX_LEN} characters.",
            )

        if self._compiled_regex.match(str_value):
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{compare_value}' matches regex pattern '{self.regex}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property name '{compare_value}' does not match regex pattern '{self.regex}'",
        )
