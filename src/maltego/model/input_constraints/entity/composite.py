# Copyright (c) Maltego Technologies GmbH.
from typing import Literal, Sequence, Union

from maltego.model.entity import MaltegoEntity
from maltego.model.input_constraints.base import CompositeInputConstraint, EntityConstraint, ops
from maltego.model.input_constraints.base import ConstraintResult

class CompositeEntityInputConstraint(
    EntityConstraint,
    CompositeInputConstraint[MaltegoEntity]
):
    """Composite Entity constraint that applies logical operations (ALL, ANY, NONE)."""

    constraints: Sequence[EntityConstraint]
    operation: Literal["any", "all", "none"]

    def evaluate(self, input_value: MaltegoEntity) -> bool:
        """Applies logical operations (ALL, ANY, NONE) on the constraints."""
        return ops[self.operation]([c.evaluate(input_value) for c in self.constraints])

    def evaluate_with_hierarchy(self, input_value: MaltegoEntity) -> ConstraintResult:
        """Applies logical operations and returns hierarchical results."""
        constraint_results = [c.evaluate_with_hierarchy(input_value) for c in self.constraints]
        
        # Determine overall success based on operation
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


class EntitySatisfiesAll(CompositeEntityInputConstraint):
    type: Literal["entity_satisfies_all"] = "entity_satisfies_all"
    constraints: Sequence[Union[EntityConstraint,
                                CompositeEntityInputConstraint]]
    operation: Literal["all"] = "all"


class EntitySatisfiesAny(CompositeEntityInputConstraint):
    type: Literal["entity_satisfies_any"] = "entity_satisfies_any"
    constraints: Sequence[Union[EntityConstraint,
                                CompositeEntityInputConstraint]]
    operation: Literal["any"] = "any"


class EntitySatisfiesNone(CompositeEntityInputConstraint):
    type: Literal["entity_satisfies_none"] = "entity_satisfies_none"
    constraints: Sequence[Union[EntityConstraint,
                                CompositeEntityInputConstraint]]
    operation: Literal["none"] = "none"
