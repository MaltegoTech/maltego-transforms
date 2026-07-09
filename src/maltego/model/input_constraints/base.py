# Copyright (c) Maltego Technologies GmbH.
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Sequence,
    TypeVar,
    Union,
    cast,
)

from pydantic import BaseModel

from maltego.model.entity import MaltegoEntity
from maltego.model.entity.property import (
    _MaltegoEntityProperty as MaltegoEntityProperty,
)
from maltego.model.graph import MaltegoGraph

InputConstraintType = TypeVar(
    "InputConstraintType",
    MaltegoEntity,
    MaltegoEntityProperty[Any],
    MaltegoGraph[Any],
)

# Core operations for composite constraints
none_fn: Callable[[Iterable[bool]], bool] = lambda xs: not any(xs)

ops: dict[str, Callable[[Iterable[bool]], bool]] = {
    "any": any,
    "all": all,
    "none": none_fn,  # NOT logic
}


def extract_comparable_value(value: Any) -> Any:
    """
    Extract a comparable value from a property value, handling entity-typed properties.
    For entity-typed properties, gets the main value from the nested entity.

    Args:
        value: The property value to extract from

    Returns:
        The extracted value (for entities, returns the main value; for primitives, returns as-is)
    """
    if value is None:
        return None

    if isinstance(value, MaltegoEntity):
        # For entity-typed properties, extract the main value
        return extract_comparable_value(value.value)

    return value


class ConstraintStringMatchType(str, Enum):
    """Used for selecting string matching operation."""

    CONTAINS = "contains"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"


@dataclass
class ConstraintResult:
    """Represents the result of evaluating a constraint with hierarchical details."""

    success: bool
    constraint_name: str
    message: str
    children: List["ConstraintResult"] = None

    def __post_init__(self):
        if self.children is None:
            self.children = []

    def add_child(self, child: "ConstraintResult"):
        if self.children is None:
            self.children = []
        self.children.append(child)

    def to_string(self, indent: int = 0) -> str:
        """Convert the result tree to a formatted string."""
        prefix = (
            (" |" * (indent - 1) + (" ✓ " if self.success else " ✗ "))
            if indent > 0
            else ""
        )
        result = (
            f"{prefix}{self.constraint_name} {'passed' if self.success else 'failed'}"
        )

        if self.message:
            result += f": {self.message}"

        if self.children:
            for child in self.children:
                result += f"\n{child.to_string(indent + 1)}"

        return result


class InputConstraint(BaseModel, Generic[InputConstraintType]):
    """Base class for all input constraints in Maltego, supporting input filtering in transforms."""

    def eval(
        self,
        input_value: Union[
            MaltegoEntity,
            MaltegoEntityProperty[Any],
            List[MaltegoEntity],
            MaltegoGraph[Any],
        ],
    ) -> bool:
        """Generic evaluation that dynamically routes based on input type."""

        def do(v: object) -> bool:
            return self.evaluate(cast(InputConstraintType, v))

        if isinstance(input_value, MaltegoEntity):
            return do(input_value)
        if isinstance(input_value, MaltegoEntityProperty):
            return do(input_value)
        if isinstance(input_value, list):
            return all(do(e) for e in input_value)
        if isinstance(input_value, MaltegoGraph):
            return all(do(e) for e in input_value.entities)

        raise TypeError(f"Unsupported input type: {type(input_value)}")

    def eval_with_hierarchy(
        self,
        input_value: Union[
            MaltegoEntity,
            MaltegoEntityProperty[Any],
            List[MaltegoEntity],
            MaltegoGraph[Any],
        ],
    ) -> ConstraintResult:
        """Generic evaluation that returns hierarchical constraint results."""

        def do(v: object) -> ConstraintResult:
            return self.evaluate_with_hierarchy(cast(InputConstraintType, v))

        if isinstance(input_value, MaltegoEntity):
            return do(input_value)
        if isinstance(input_value, MaltegoEntityProperty):
            return do(input_value)
        if isinstance(input_value, list):
            all_results = [do(e) for e in input_value]
            success = all(result.success for result in all_results)

            # Create a composite result for lists
            result = ConstraintResult(
                success=success,
                constraint_name="ListEvaluation",
                message=f"Evaluated {len(input_value)} entities",
            )

            for i, child_result in enumerate(all_results):
                result.add_child(child_result)

            return result

        if isinstance(input_value, MaltegoGraph):
            all_results = [do(e) for e in input_value.entities]
            success = all(result.success for result in all_results)

            result = ConstraintResult(
                success=success,
                constraint_name="GraphEvaluation",
                message=f"Evaluated {len(input_value.entities)} entities in graph",
            )

            for child_result in all_results:
                result.add_child(child_result)

            return result

        raise TypeError(f"Unsupported input type: {type(input_value)}")

    def evaluate(
        self,
        input_value: InputConstraintType,
    ) -> bool:
        """Default evaluation logic. Must be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement evaluate()")

    def evaluate_with_hierarchy(
        self,
        input_value: InputConstraintType,
    ) -> ConstraintResult:
        """Default evaluation logic with hierarchical results. Must be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement evaluate_with_hierarchy()")

    def to_v3_model(self) -> Dict[Any, Any]:
        """Default implementation: Dumps the model as a dictionary, including nested constraints."""
        data = self.model_dump(mode="json")

        constraint = getattr(self, "constraint", None)
        if isinstance(constraint, InputConstraint):
            return constraint.to_v3_model()

        constraints = getattr(self, "constraints", None)
        if isinstance(constraints, list) and all(
            isinstance(c, InputConstraint) for c in constraints
        ):
            data["constraints"] = [c.to_v3_model() for c in constraints]

        return data


class EntityConstraint(InputConstraint[MaltegoEntity], ABC):
    """Base class for all entity constraints in Maltego."""

    pass


class PropertyConstraint(InputConstraint[MaltegoEntityProperty[Any]], ABC):
    """Base class for all property constraints in Maltego."""

    pass


class CompositeInputConstraint(InputConstraint[InputConstraintType]):
    """Composite constraint that applies logical operations (ALL, ANY, NONE)."""

    constraints: Sequence[InputConstraint[InputConstraintType]]
    operation: Literal["any", "all", "none"]

    def evaluate(
        self,
        input_value: InputConstraintType,
    ) -> bool:
        """Applies logical operations (ALL, ANY, NONE) on the constraints."""
        return ops[self.operation]([c.evaluate(input_value) for c in self.constraints])

    def evaluate_with_hierarchy(
        self,
        input_value: InputConstraintType,
    ) -> ConstraintResult:
        """Applies logical operations and returns hierarchical results."""
        constraint_results = [
            c.evaluate_with_hierarchy(input_value) for c in self.constraints
        ]

        # Determine overall success based on operation
        if self.operation == "all":
            success = all(result.success for result in constraint_results)
        elif self.operation == "any":
            success = any(result.success for result in constraint_results)
        elif self.operation == "none":
            success = not any(result.success for result in constraint_results)

        # Create composite result
        result = ConstraintResult(
            success=success,
            constraint_name=f"{self.__class__.__name__}({self.operation})",
            message="",
        )

        # Add child results based on operation type
        if self.operation == "all":
            # For "all", show all results (but EntityHasPropertySatisfying will only show relevant ones)
            for child_result in constraint_results:
                result.add_child(child_result)
        elif self.operation == "any":
            # For "any", show all results
            for child_result in constraint_results:
                result.add_child(child_result)
        elif self.operation == "none":
            # For "none", only show constraints that unexpectedly passed
            # This avoids showing all the failures that are expected
            for child_result in constraint_results:
                if child_result.success:
                    # This constraint passed when it shouldn't have
                    result.add_child(child_result)

        return result
