# Copyright (c) Maltego Technologies GmbH.
import datetime as _dt
from abc import ABC, abstractmethod
from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from maltego.model import MaltegoEntity
from maltego.model.entity.property import (
    _MaltegoEntityProperty as MaltegoEntityProperty,
)
from maltego.model.input_constraints.base import ConstraintResult, PropertyConstraint, extract_comparable_value
from maltego.model.types import daterange as _dr, v3_property_types


class PropertyEquals(PropertyConstraint, ABC):
    """Base class for equals constraints."""

    type: str = Field(..., frozen=True)
    value: Any
    ignore_case: bool = False

    @abstractmethod
    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        pass


class PropertyValueEquals(PropertyEquals):
    """
    Unsupported types are DATE, DATETIME, DATERANGE, MaltegoEntity (composition)
    """
    type: Literal["property_value_equals"] = "property_value_equals"

    @staticmethod
    def _equals(a: str, b: str, ignore_case: bool) -> bool:
        return a.lower() == b.lower() if ignore_case else a == b

    @staticmethod
    def _canon(value: Any) -> Optional[str]:
        """
          - str -> as-is
          - bool -> 'true' / 'false'
          - date/datetime -> unsupported
          - daterange -> unsupported
          - MaltegoEntity -> extract main value property
          - everything else -> str(value)
        """
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (_dt.datetime, _dt.date)):
            raise TypeError("PropertyValueEquals does not support DATE/DATETIME values.")

        if isinstance(value, _dr):
            raise TypeError("PropertyValueEquals does not support DATERANGE values.")

        if isinstance(value, MaltegoEntity):
            # For entity-typed properties, extract the main value
            extracted = extract_comparable_value(value)
            return PropertyValueEquals._canon(extracted)

        return str(value)

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value_to_string_for_protocol(cls, v):
        # If a list is desired, the dev should add one PropertyValueEquals per element
        if isinstance(v, (list, tuple)):
            raise ValueError(
                "PropertyValueEquals.value must be a single value. "
                "For list-typed properties, add a separate PropertyValueEquals "
                "constraint for each required element."
            )
        # Reject MaltegoEntity instances during constraint initialization
        # (entity-typed properties are supported during evaluation, not as constraint values)
        if isinstance(v, MaltegoEntity):
            raise TypeError(
                "PropertyValueEquals.value cannot be a MaltegoEntity. "
                "Entity-typed properties are automatically extracted during evaluation."
            )
        canon = cls._canon(v)
        if canon is None:
            raise ValueError("PropertyValueEquals.value cannot be None")
        return canon

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """
        Compare the constraint to the property value.
        For entity-typed properties, extracts the main value from the entity.
        """
        v = input_value.value

        if isinstance(v, (list, tuple)):
            for el in v:
                try:
                    s = self._canon(el)  # may raise TypeError; we skip those elements
                except TypeError:
                    continue
                if s is not None and self._equals(s, self.value, self.ignore_case):
                    return True
            return False

        try:
            property_value = self._canon(v)  # may raise TypeError
        except TypeError:
            return False
        return property_value is not None and self._equals(
            property_value, self.value, self.ignore_case
        )

    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """
        Evaluate with hierarchical results.
        For entity-typed properties, extracts the main value from the entity.
        """
        v = input_value.value
        ci = " (case-insensitive)" if self.ignore_case else ""

        if isinstance(v, (list, tuple)):
            ok = False
            for el in v:
                try:
                    s = self._canon(el)  # may raise TypeError; skip unsupported
                except TypeError:
                    continue
                if s is not None and self._equals(s, self.value, self.ignore_case):
                    ok = True
                    break

            return ConstraintResult(
                success=ok,
                constraint_name=self.__class__.__name__,
                message=(
                    f"Property {'matches' if ok else 'does not match'} "
                    f"expected '{self.value}'{ci}."
                ),
            )

        try:
            property_value = self._canon(v)  # may raise TypeError
        except TypeError:
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property does not match expected '{self.value}'{ci}.",
            )

        if property_value is None:
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property does not match expected '{self.value}'{ci}.",
            )

        ok = self._equals(property_value, self.value, self.ignore_case)
        return ConstraintResult(
            success=ok,
            constraint_name=self.__class__.__name__,
            message=(
                f"Property value '{property_value}' "
                f"{'matches' if ok else 'does not match'} '{self.value}'{ci}."
            ),
        )


class PropertyDisplayNameEquals(PropertyEquals):
    type: Literal["property_display_name_equals"] = "property_display_name_equals"

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the value against the property display name."""
        compare_value = input_value.display_name

        if not isinstance(compare_value, str):
            return False

        if self.ignore_case:
            return compare_value.lower() == self.value.lower()
        return compare_value == self.value

    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the value against the property display name with hierarchical reporting."""
        compare_value = input_value.display_name

        if not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name is not a string (got {type(compare_value).__name__})",
            )

        if self.ignore_case:
            if compare_value.lower() == self.value.lower():
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property display name '{compare_value}' matches '{self.value}' (case-insensitive)",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{compare_value}' does not match '{self.value}' (case-insensitive)",
            )

        if compare_value == self.value:
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property display name '{compare_value}' matches '{self.value}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property display name '{compare_value}' does not match '{self.value}'",
        )


class PropertyNameEquals(PropertyEquals):
    type: Literal["property_name_equals"] = "property_name_equals"

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the value against the property name."""
        compare_value = input_value.name

        if not isinstance(compare_value, str):
            return False

        if self.ignore_case:
            return compare_value.lower() == self.value.lower()
        return compare_value == self.value

    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the value against the property name with hierarchical reporting."""
        compare_value = input_value.name

        if not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name is not a string (got {type(compare_value).__name__})",
            )

        if self.ignore_case:
            if compare_value.lower() == self.value.lower():
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property name '{compare_value}' matches '{self.value}' (case-insensitive)",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{compare_value}' does not match '{self.value}' (case-insensitive)",
            )

        if compare_value == self.value:
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property name '{compare_value}' matches '{self.value}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property name '{compare_value}' does not match '{self.value}'",
        )


class PropertyTypeEquals(PropertyEquals):
    type: Literal["property_type_equals"] = "property_type_equals"

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Matches the input_value against the property type."""
        compare_value = v3_property_types[input_value.primitive_type]

        if not isinstance(compare_value, str):
            return False

        if self.ignore_case:
            return compare_value.lower() == self.value.lower()
        return compare_value == self.value

    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        """Matches the input_value against the property type with hierarchical reporting."""
        compare_value = v3_property_types[input_value.primitive_type]

        if not isinstance(compare_value, str):
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property type is not a string (got {type(compare_value).__name__})",
            )

        if self.ignore_case:
            if compare_value.lower() == self.value.lower():
                return ConstraintResult(
                    success=True,
                    constraint_name=self.__class__.__name__,
                    message=f"Property type '{compare_value}' matches '{self.value}' (case-insensitive)",
                )
            return ConstraintResult(
                success=False,
                constraint_name=self.__class__.__name__,
                message=f"Property type '{compare_value}' does not match '{self.value}' (case-insensitive)",
            )

        if compare_value == self.value:
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=f"Property type '{compare_value}' matches '{self.value}'",
            )
        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=f"Property type '{compare_value}' does not match '{self.value}'",
        )
