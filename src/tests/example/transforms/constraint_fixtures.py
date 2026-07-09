from typing import Any, Literal

from maltego.model.entity.property import (
    _MaltegoEntityProperty as MaltegoEntityProperty,
)
from maltego.model.input_constraints import PropertyEquals
from maltego.model.input_constraints.base import ConstraintResult


class PropertyValueUnknownTest(PropertyEquals):
    type: Literal["property_value_unknown_test"] = "property_value_unknown_test"

    def evaluate(self, input_value) -> bool:
        pass

    def evaluate_with_hierarchy(
            self, input_value: MaltegoEntityProperty[Any]
    ) -> ConstraintResult:
        pass
