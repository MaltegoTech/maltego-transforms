# Copyright (c) Maltego Technologies GmbH.
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import Field

from maltego.model.entity.property import (
    _MaltegoEntityProperty as MaltegoEntityProperty,
)
from maltego.model.input_constraints import ConstraintStringMatchType
from maltego.model.input_constraints.base import ConstraintResult, PropertyConstraint, extract_comparable_value


class PropertyStringMatch(PropertyConstraint, ABC):
    """Base class for substring, prefix, and suffix matching."""

    type: str = Field(..., frozen=True)
    match_type: ConstraintStringMatchType = ConstraintStringMatchType.CONTAINS
    value: str
    ignore_case: bool = False

    @abstractmethod
    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        pass


class PropertyValueStringMatch(PropertyStringMatch):
    type: Literal["property_value_string_match"] = "property_value_string_match"

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the value against the property value. For entity-typed properties, extracts the main value."""
        value = self.value
        raw_value = input_value.value

        # Extract comparable value for entity-typed properties
        extracted = extract_comparable_value(raw_value)
        compare_value = str(extracted) if extracted is not None else None

        if compare_value is None or not isinstance(compare_value, str):
            return False

        if not isinstance(value, str):
            return False

        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            return compare_value.startswith(value)
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            return compare_value.endswith(value)
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            return value in compare_value

        return False

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the value against the property value with hierarchical reporting. For entity-typed properties, extracts the main value."""
        value = self.value
        raw_value = input_value.value

        # Extract comparable value for entity-typed properties
        extracted = extract_comparable_value(raw_value)
        compare_value = str(extracted) if extracted is not None else None

        if compare_value is None or not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property value is not a string (got {type(raw_value).__name__})",
            )

        if not isinstance(value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Match value is not a string (got {type(value).__name__})",
            )

        # Store original for display
        original_compare = compare_value
        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            if compare_value.startswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property value '{original_compare}' starts with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property value '{original_compare}' does not start with '{self.value}'",
            )
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            if compare_value.endswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property value '{original_compare}' ends with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property value '{original_compare}' does not end with '{self.value}'",
                )
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            if value in compare_value:
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property value '{original_compare}' contains '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property value '{original_compare}' does not contain '{self.value}'",
            )

        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Unknown match type: {self.match_type}",
        )


class PropertyDisplayNameStringMatch(PropertyStringMatch):
    type: Literal["property_display_name_string_match"] = (
        "property_display_name_string_match"
    )

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the value against the property display name."""
        value = self.value
        compare_value = input_value.display_name

        if not isinstance(compare_value, str):
            return False

        if not isinstance(value, str):
            return False

        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            return compare_value.startswith(value)
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            return compare_value.endswith(value)
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            return value in compare_value

        return False

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the value against the property display name with hierarchical reporting."""
        value = self.value
        compare_value = input_value.display_name

        if not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name is not a string (got {type(compare_value).__name__})",
            )

        if not isinstance(value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Match value is not a string (got {type(value).__name__})",
            )

        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            if compare_value.startswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property display name '{input_value.display_name}' starts with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{input_value.display_name}' does not start with '{self.value}'",
            )
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            if compare_value.endswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property display name '{input_value.display_name}' ends with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{input_value.display_name}' does not end with '{self.value}'",
            )
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            if value in compare_value:
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property display name '{input_value.display_name}' contains '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{input_value.display_name}' does not contain '{self.value}'",
            )

        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Unknown match type: {self.match_type}",
        )


class PropertyNameStringMatch(PropertyStringMatch):
    type: Literal["property_name_string_match"] = "property_name_string_match"

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the value against the property name."""
        value = self.value
        compare_value = input_value.name

        if not isinstance(compare_value, str):
            return False

        if not isinstance(value, str):
            return False

        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            return compare_value.startswith(value)
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            return compare_value.endswith(value)
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            return value in compare_value

        return False

    def evaluate_with_hierarchy(
        self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the value against the property name with hierarchical reporting."""
        value = self.value
        compare_value = input_value.name

        if not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name is not a string (got {type(compare_value).__name__})",
            )

        if not isinstance(value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Match value is not a string (got {type(value).__name__})",
            )

        if self.ignore_case:
            compare_value = compare_value.lower()
            value = value.lower()

        if self.match_type == ConstraintStringMatchType.STARTSWITH:
            if compare_value.startswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property name '{input_value.name}' starts with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{input_value.name}' does not start with '{self.value}'",
            )
        if self.match_type == ConstraintStringMatchType.ENDSWITH:
            if compare_value.endswith(value):
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property name '{input_value.name}' ends with '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{input_value.name}' does not end with '{self.value}'",
            )
        if self.match_type == ConstraintStringMatchType.CONTAINS:
            if value in compare_value:
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property name '{input_value.name}' contains '{self.value}'",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{input_value.name}' does not contain '{self.value}'",
            )

        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Unknown match type: {self.match_type}",
        )
