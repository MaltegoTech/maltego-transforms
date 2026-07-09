# Copyright (c) Maltego Technologies GmbH.
import inspect
import typing
from typing import Any, List, Literal, Type, Union

from maltego.model.entity import MaltegoEntity, MaltegoEntityMeta
from maltego.model.graph import MaltegoGraph
from maltego.util.collections_utils import flatten
from maltego.util.typing import is_any_union_type


class UnionFilters(typing.NamedTuple):
    entity_filter: typing.FrozenSet[Type[MaltegoEntity]]
    list_filters: typing.FrozenSet[typing.FrozenSet[Type[MaltegoEntity]]]

    @classmethod
    def from_sets(cls,
                  entity_filter: frozenset[Type[MaltegoEntity]] = frozenset(),
                  lists_filter: frozenset[typing.FrozenSet[Type[MaltegoEntity]]] = frozenset()) -> "UnionFilters":
        return cls(frozenset(entity_filter), frozenset(lists_filter))

    @classmethod
    def empty(cls) -> "UnionFilters":
        return cls(frozenset(), frozenset())


def get_union_annotation_type_filter(
        union_annotation: Type[Any],
        entities_only: bool = False
) -> UnionFilters:
    entity_filter = set()
    list_filters = set()

    origin = typing.get_origin(union_annotation)
    if not is_any_union_type(origin):
        return UnionFilters.empty()

    for type_arg in typing.get_args(union_annotation):
        # MaltegoEntity or Any
        if inspect.isclass(type_arg) and issubclass(type_arg, MaltegoEntity):
            entity_filter.add(type_arg)

        # List[MaltegoEntity | ...]
        if not entities_only:
            arg_origin = typing.get_origin(type_arg)
            if arg_origin is list:
                if list_filter := get_list_annotation_type_filter(type_arg):
                    list_filters.add(list_filter)

    return UnionFilters.from_sets(
        frozenset(entity_filter), frozenset(list_filters)
    )


def get_list_annotation_type_filter(
        list_annotation: typing.Type[List[Type[MaltegoEntity]]]
) -> typing.FrozenSet[typing.Type[MaltegoEntity]]:
    origin = typing.get_origin(list_annotation)

    if origin is not list:
        return frozenset()

    for type_arg in typing.get_args(list_annotation):
        arg_origin = typing.get_origin(type_arg)

        if is_any_union_type(arg_origin):
            return get_union_annotation_type_filter(type_arg, entities_only=True).entity_filter

        if inspect.isclass(type_arg) and issubclass(type_arg, MaltegoEntity):
            return frozenset({type_arg})

    return frozenset()


def annotation_filter_to_type_filter(
        entity_filter: typing.Iterable[Type[MaltegoEntity]],
) -> typing.Set[str]:
    type_filter = set()
    for entity in entity_filter:
        if entity.TYPE_NAME:
            type_filter.add(entity.TYPE_NAME)

    return type_filter


def entity_in_filter(entity: MaltegoEntity, entity_filter: typing.Set[str]) -> bool:
    genealogy = entity.base_entity_types()
    if entity.genealogy:
        genealogy.update(entity.genealogy)
    return len(genealogy.intersection(entity_filter)) > 0 or "maltego.Unknown" in entity_filter


def filter_by_entity_filter(
        entities: typing.Iterable[MaltegoEntity],
        entity_filter: typing.Iterable[Type[MaltegoEntity]]
) -> typing.Tuple[List[MaltegoEntity], List[MaltegoEntity]]:
    entity_filter_types = annotation_filter_to_type_filter(entity_filter)

    accepted, rejected = [], []
    for entity in entities:
        if entity_in_filter(entity, entity_filter_types):
            accepted.append(entity)
        else:
            rejected.append(entity)

    return accepted, rejected


def partition_by_union_filter(
        entities: list[MaltegoEntity],
        union_filter: UnionFilters
) -> typing.Generator[typing.Union[List[MaltegoEntity], MaltegoEntity], None, None]:
    remaining_entities = tuple(entities)
    for list_filter in union_filter.list_filters:
        accepted, rejected = filter_by_entity_filter(remaining_entities, list_filter)
        remaining_entities = tuple(rejected)

        yield accepted

    accepted, rejected = filter_by_entity_filter(entities, union_filter.entity_filter)
    yield from accepted


class TransformInputAnnotation:
    annotation: Type[Any]

    def __init__(self, annotation: Any):
        self.annotation = annotation

    @property
    def input(self) -> Type[Any]:
        return self.annotation

    def apply_filter(
        self,
        entities: list[MaltegoEntity]
    ) -> typing.Iterable[Union[MaltegoEntity, list[MaltegoEntity], Type[MaltegoEntity]]]:
        if self.is_graph():
            yield from self.get_graph_filter()

        if self.is_entity():
            yield from self.apply_entity_filter(entities)

        if self.is_iterable():
            yield from self.apply_list_filter(entities)

        if self.is_union():
            yield from self.apply_union_filter(entities)
        raise ValueError(f"No valid filter for annotation {self}")

    def __get_flat_types(self) -> frozenset[Type[MaltegoEntity]]:
        if self.is_graph():
            entity_filter = self.get_graph_filter()
        elif self.is_entity():
            entity_filter = self.get_entity_filter()
        elif self.is_iterable():
            entity_filter = self.get_list_filter()
        elif self.is_union():
            union_filter = self.get_union_filter()
            entity_filter = frozenset({
                *flatten(union_filter.list_filters),
                *union_filter.entity_filter
            })
        else:
            raise ValueError(f"Unsupported Annotation {self.annotation}")
        return entity_filter

    def get_flat_entity_types(self) -> List[str]:
        entity_filter = self.__get_flat_types()

        return [e.TYPE_NAME for e in entity_filter if e.TYPE_NAME is not None]

    def get_entities_type_ids(self) -> List[str]:
        if self.annotation is None or (
            inspect.isclass(self.annotation)
            and typing.get_origin(self.annotation) is None
            and isinstance(None, self.annotation)
        ):
            return []
        if self.is_union() or self.is_graph() or self.is_iterable():
            args = typing.get_args(self.annotation)
            if len(args) == 1 and args[0] is typing.Any:
                return []
            result = []
            for arg in args:
                ann = TransformInputAnnotation(arg)
                result.extend(ann.get_entities_type_ids())
            return result
        if self.is_entity():
            if self.annotation.TYPE_NAME is None:
                raise RuntimeError(f"Annotated entity {self.annotation} has no TYPE_NAME")
            return [self.annotation.TYPE_NAME]
        raise ValueError(f"Could not infer entity type ids from annotation {self.annotation}")

    def is_valid(self) -> bool:
        return self.is_graph() or self.is_iterable() or self.is_union() or self.is_entity() or self.is_any_entity()

    def is_graph(self) -> bool:
        if self.annotation == MaltegoGraph or typing.get_origin(self.annotation) == MaltegoGraph:
            return True
        return any(
            arg == MaltegoGraph or typing.get_origin(arg) == MaltegoGraph for arg in typing.get_args(self.annotation)
        )

    def get_graph_filter(self) -> frozenset[Type[MaltegoEntity]]:
        assert self.is_graph()

        # MaltegoGraph
        args = None
        if typing.get_origin(self.annotation) == MaltegoGraph:
            args = typing.get_args(self.annotation)
        else:
            parent_args = typing.get_args(self.annotation)
            for parent_arg in parent_args:
                if typing.get_origin(self.annotation) == MaltegoGraph:
                    args = typing.get_args(parent_arg)

        if not args:
            return frozenset()

        # MaltegoGraph[...]
        # Generic MaltegoGraph can only have one arg
        if len(args) != 1:
            raise ValueError(f"Unsupported arguments {args}")

        generic_arg = args[0]

        # MaltegoGraph[MaltegoEntity]
        if inspect.isclass(generic_arg) and issubclass(generic_arg, MaltegoEntity):
            return frozenset({generic_arg})

        # MaltegoGraph[MaltegoEntity | ...]
        arg_origin = typing.get_origin(generic_arg)
        if is_any_union_type(arg_origin):
            return get_union_annotation_type_filter(generic_arg, entities_only=True).entity_filter

        if generic_arg == typing.Any:
            return frozenset()

        raise ValueError(f"Unsupported annotation {self.annotation}")

    def apply_graph_filter(self, entities: list[MaltegoEntity]) -> list[MaltegoEntity]:
        assert self.is_graph()
        return filter_by_entity_filter(entities, self.get_graph_filter())[0]

    def is_iterable(self) -> bool:
        if self.is_union():
            return False
        try:
            iter(self.annotation)  # type: ignore
            return True
        except TypeError:
            if typing.get_origin(self.annotation) is list:
                return True
            return False

    def get_list_filter(self) -> frozenset[typing.Type[MaltegoEntity]]:
        assert self.is_iterable()
        return get_list_annotation_type_filter(self.annotation)

    def apply_list_filter(
            self,
            entities: List[MaltegoEntity]
    ) -> List[MaltegoEntity]:
        assert self.is_iterable()
        accepted, _ = filter_by_entity_filter(entities, self.get_list_filter())
        return accepted

    def is_union(self) -> bool:
        return is_any_union_type(typing.get_origin(self.annotation))

    def get_union_filter(self, entities_only: bool = False) -> UnionFilters:
        assert self.is_union()
        return get_union_annotation_type_filter(self.annotation, entities_only)

    def apply_union_filter(
            self,
            entities: list[MaltegoEntity]
    ) -> typing.Generator[Union[List[MaltegoEntity], MaltegoEntity], None, None]:
        assert self.is_union()
        yield from partition_by_union_filter(entities, self.get_union_filter())

    def is_entity(self) -> bool:
        return inspect.isclass(self.annotation) and issubclass(self.annotation, MaltegoEntity)

    def get_entity_filter(self) -> frozenset[Type[MaltegoEntity]]:
        assert self.is_entity()
        return frozenset({self.annotation})

    def apply_entity_filter(self, entities: List[MaltegoEntity]) -> typing.Iterable[MaltegoEntity]:
        accepted, _ = filter_by_entity_filter(entities, self.get_entity_filter())
        return accepted

    def is_any_entity(self) -> bool:
        return (
            inspect.isclass(self.annotation) and typing.get_origin(self.annotation) is None
            and isinstance(None, self.annotation)
        ) or (
            self.annotation is None
        ) or (
            self.annotation is MaltegoEntity
        ) or (
            isinstance(self.annotation, MaltegoEntityMeta)
            and self.annotation.TYPE_NAME == 'maltego.Unknown'
        )

    def uses_graph_payload(self, direction: Literal["in", "out"] = 'in') -> bool:
        if direction == 'out':
            return self.is_graph()
        return self.is_graph() or self.is_iterable()

    def is_composed(self):
        """ Check if annotation has entities with entity-typed properties"""
        try:
            flat_entity_types = self.__get_flat_types()
        except ValueError:
            return False
        for ent in flat_entity_types:
            if isinstance(ent, MaltegoEntityMeta):
                if MaltegoEntity.has_entity_typed_field(ent):
                    return True
        return False
