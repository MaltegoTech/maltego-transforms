# Copyright (c) Maltego Technologies GmbH.
from typing import Literal

from maltego.model.entity import MaltegoEntity
from maltego.model.input_constraints.property import CompositePropertyInputConstraint
from maltego.model.input_constraints.base import EntityConstraint
from maltego.model.input_constraints.base import ConstraintResult


class EntityHasPropertySatisfying(EntityConstraint):
    type: Literal["entity_has_property_satisfying"] = "entity_has_property_satisfying"
    constraint: CompositePropertyInputConstraint

    def evaluate(self, entity: MaltegoEntity) -> bool:
        """Evaluates whether at least one property in the entity satisfies the given constraint."""
        return any(
            self.constraint.evaluate(prop)
            for key, prop in entity.get_properties().items()
        )

    def evaluate_with_hierarchy(self, entity: MaltegoEntity) -> ConstraintResult:
        """Evaluates whether at least one property satisfies the constraint with hierarchical reporting."""
        properties = entity.get_properties()

        # Extract the target property name from the constraint if possible
        target_property_name = None
        if self.constraint and self.constraint.constraints:
            for constraint in self.constraint.constraints:
                if (
                    constraint.type
                    and constraint
                    and constraint.type
                    in ["property_name_equals", "property_display_name_equals"]
                ):
                    target_property_name = constraint.value
                    break

        # Check if any property satisfies the constraint
        property_results = []
        any_passed = False
        target_property_result = None

        for key, prop in properties.items():
            prop_result = self.constraint.evaluate_with_hierarchy(prop)
            property_results.append(prop_result)
            if prop_result.success:
                any_passed = True
                # Store the first passing property result
                if target_property_result is None:
                    target_property_result = prop_result

        # Create result
        result = ConstraintResult(
            success=any_passed,
            constraint_name=self.__class__.__name__,
            message=f"Looking for property satisfying: {self.constraint.__class__.__name__}",
        )

        # Show the result for the target property if we found it
        if target_property_name and target_property_name in list(properties.keys()) + [
            prop.display_name for prop in properties.values()
        ]:
            target_prop = properties.get(target_property_name, None) or next(
                prop
                for prop in properties.values()
                if prop.display_name == target_property_name
            )
            target_result = self.constraint.evaluate_with_hierarchy(target_prop)
            result.add_child(target_result)
        elif target_property_result is not None:
            # Show the passing property result
            result.add_child(target_property_result)
        else:
            ambiguous_result = ConstraintResult(
                success=False,
                constraint_name=self.constraint.__class__.__name__,
                message="No specific property passed the constraint.",
            )
            result.add_child(ambiguous_result)

        return result
