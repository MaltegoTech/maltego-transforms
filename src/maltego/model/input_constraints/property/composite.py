# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Literal, Sequence, Union

from maltego.model.entity.property import _MaltegoEntityProperty as MaltegoEntityProperty
from maltego.model.input_constraints.base import (
    CompositeInputConstraint,
    PropertyConstraint,
    ops,
    ConstraintResult
)


class CompositePropertyInputConstraint(
    PropertyConstraint,
    CompositeInputConstraint[MaltegoEntityProperty[Any]]
):
    """Composite Property constraint that applies logical operations (ALL, ANY, NONE)."""

    constraints: Sequence[PropertyConstraint]
    operation: Literal["any", "all", "none"]

    def evaluate(self, input_value: MaltegoEntityProperty[Any]) -> bool:
        """Applies logical operations (ALL, ANY, NONE) on the constraints."""
        return ops[self.operation]([c.evaluate(input_value) for c in self.constraints])

    def evaluate_with_hierarchy(self, input_value: MaltegoEntityProperty[Any]) -> ConstraintResult:
        """Applies logical operations and returns hierarchical results."""
        constraint_results = [c.evaluate_with_hierarchy(input_value) for c in self.constraints]
        
        success = ops[self.operation]([result.success for result in constraint_results])
        
        # Create composite result
        result = ConstraintResult(
            success=success,
            constraint_name=f"{self.__class__.__name__}",
            message=""
        )
        
        # Add all child results
        for child_result in constraint_results:
            result.add_child(child_result)
        
        return result


class PropertySatisfiesAll(CompositePropertyInputConstraint):
    type: Literal["property_satisfies_all"] = "property_satisfies_all"
    constraints: Sequence[Union[CompositePropertyInputConstraint,
                                PropertyConstraint]]
    operation: Literal["all"] = "all"


class PropertySatisfiesAny(CompositePropertyInputConstraint):
    type: Literal["property_satisfies_any"] = "property_satisfies_any"
    constraints: Sequence[Union[CompositePropertyInputConstraint,
                                PropertyConstraint]]
    operation: Literal["any"] = "any"


class PropertySatisfiesNone(CompositePropertyInputConstraint):
    type: Literal["property_satisfies_none"] = "property_satisfies_none"
    constraints: Sequence[Union[CompositePropertyInputConstraint,
                                PropertyConstraint]]
    operation: Literal["none"] = "none"
