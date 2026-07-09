# Copyright (c) Maltego Technologies GmbH.
from typing import Literal

from maltego.model.entity import MaltegoEntity
from maltego.model.input_constraints.base import EntityConstraint
from maltego.model.input_constraints.base import ConstraintResult



class EntityTypeConstraint(EntityConstraint):
    type: Literal["entity_type_constraint"] = "entity_type_constraint"
    entity_type: str

    def _matches_type_or_parents(self, entity: MaltegoEntity) -> bool:
        return self.entity_type in entity.base_entity_types()

    def evaluate(self, entity: MaltegoEntity) -> bool:
        return self._matches_type_or_parents(entity)


    def evaluate_with_hierarchy(self, entity: MaltegoEntity) -> ConstraintResult:
        if self._matches_type_or_parents(entity):
            return ConstraintResult(
                success=True,
                constraint_name=self.__class__.__name__,
                message=(
                    f"Entity type '{entity.TYPE_NAME}' matches "
                    f"expected '{self.entity_type}'"
                ),
            )

        base_types = sorted(entity.base_entity_types())
        base_types_str = ", ".join(base_types) if base_types else "none"

        return ConstraintResult(
            success=False,
            constraint_name=self.__class__.__name__,
            message=(
                f"Expected entity type '{self.entity_type}', "
                f"got '{base_types_str}'"
            ),
        )
