# Copyright (c) Maltego Technologies GmbH.
from __future__ import annotations
from typing import Any, Optional, Dict, List, TypeVar, Union, Type, Tuple, Set, TypeGuard

import inspect
import builtins
import datetime
import logging
import sys
import typing
import dateutil.parser
import markdown
import nh3

# Allow-list for display-field HTML sanitization.
# Covers everything the markdown extensions we use can produce plus the
# explicit HTML helpers in the pagination example template.
# Scripts, inline event handlers (on*) and javascript:/data: URLs are stripped
# by nh3's defaults; we only need to enumerate the tags/attrs we WANT to keep.
_DISPLAY_HTML_ALLOWED_TAGS: frozenset[str] = frozenset({
    # headings
    "h1", "h2", "h3", "h4", "h5", "h6",
    # paragraphs / block
    "p", "br", "hr", "blockquote", "pre", "div",
    # inline
    "span", "strong", "em", "b", "i", "u", "s", "del", "ins", "mark",
    "small", "sup", "sub", "abbr", "cite", "q",
    # code
    "code",
    # lists
    "ul", "ol", "li", "dl", "dt", "dd",
    # links & images (href/src sanitized by nh3 – javascript:/data: stripped)
    "a", "img",
    # tables (produced by the 'tables' markdown extension)
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
})
_DISPLAY_HTML_ALLOWED_ATTRS: dict[str, set[str]] = {
    # allow href on links but NOT javascript:/data: (nh3 strips those by default)
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height"},
    # allow colspan/rowspan on table cells for rendered markdown tables
    "th": {"colspan", "rowspan", "align"},
    "td": {"colspan", "rowspan", "align"},
    # allow style only on table/div/span where the HTML helpers use it
    "table": {"style", "border", "cellpadding", "cellspacing"},
    "div": {"style"},
    "span": {"style"},
    "p": {"style"},
    "h1": {"style"}, "h2": {"style"}, "h3": {"style"},
    "h4": {"style"}, "h5": {"style"}, "h6": {"style"},
}
from maltego.model.entity.config import (
    MaltegoEntityConfig, merge_maltego_entity_config, RESERVED_ENTITY_ATTRIBUTES,
    MaltegoEntityAction, MaltegoActionType, MaltegoEntityRegexConverter
)
from maltego.model.entity.constants import (
    OverlayPositions,
    OverlayTypes,
    Overlay,
    PossiblePropertyTypes,
    ensure_enum_val
)
from maltego.model.entity.display_info import _DisplayInformationItem, DisplayLabel, DisplayField
from maltego.model.entity.property import (
    _MaltegoEntityProperty,
    generate_default_property_name,
    mef_from_value,
    mef_from_simple_annotation,
    MaltegoEntityProperty,
    MEF
)
from maltego._helper import create_maltego_id
from maltego.model.exception import MaltegoHTTPInputEntityMalformed, MaltegoHTTPServerError
from maltego.model.link import MaltegoLinkProperty
from maltego.model.observer import Observable
from maltego.model.types import (
    MATCHING_RULE_LOOSE,
    EntityPropertyTypePrimitive,
    EntityPropertyType,
    EntityPropertyTypeMeta,
    EntityPropertyTypeUnion,
    Url,
    Color,
    daterange,
    LinkColor,
    LinkStyle,
    LinkThickness,
    MatchingRule,
)
from maltego.protocol.v3.discovery.entity import (
    V3EntityAction, V3EntityDefinition, V3EntityField, V3EntityOverlay,
    V3EntityProperties, V3EntityRegexConverter
)
from maltego.protocol.v3.execution.entity import TransformRunEntity, Bookmark

ALL_ENTITY_TYPES = "maltego.Unknown"

COMPOSITE_ATTR = "__maltego_is_composite__"

log = logging.getLogger(__name__)

def _has_union(t) -> bool:
    return typing.get_origin(t) is Union

def _contains_union(t) -> bool:
    origin = typing.get_origin(t)
    if origin is Union:
        return True
    if origin is list:
        inner, = typing.get_args(t) or (None,)
        return _contains_union(inner) if inner is not None else False
    return False


def _namespace_annotations(dct: Dict[str, Any]) -> Dict[str, Any]:
    """Read class-body annotations from a metaclass namespace across Python versions.

    On Python < 3.14 the class namespace carries a materialized ``__annotations__``
    mapping. On Python >= 3.14 (PEP 649/749) annotations are lazy: the namespace
    instead exposes an ``__annotate_func__`` callable and ``__annotations__`` is no
    longer present during ``__new__``. We evaluate that function in VALUE format,
    which reproduces the pre-3.14 default (real type objects where resolvable, and
    string literals for forward refs). ``mef_from_simple_annotation`` downstream
    accepts both real types and string literals, and the discovery/transform-run
    payloads were verified byte-identical across 3.12/3.14, so the format VALUE
    returns here does not affect emitted entity property types.
    """
    if "__annotations__" in dct:
        return dct["__annotations__"]
    annotate = dct.get("__annotate_func__")
    if annotate is None:
        return {}
    # The lazy ``__annotate_func__`` path only exists on Python 3.14+ (PEP 649/749).
    # Guard the import explicitly so a stray ``__annotate_func__`` on an older
    # interpreter (e.g. injected by a third-party metaclass) degrades to "no
    # annotations" rather than raising ModuleNotFoundError on ``annotationlib``.
    if sys.version_info >= (3, 14):
        import annotationlib  # Python 3.14+ only; reached solely on the lazy path.
        return annotationlib.call_annotate_function(annotate, annotationlib.Format.VALUE)
    return {}


def is_entity_property_list(val: List[Any]) -> TypeGuard[List[_MaltegoEntityProperty[Any]]]:
    """Determines whether all objects in the list are strings"""
    return all(isinstance(x, _MaltegoEntityProperty) for x in val)


def is_link_property_list(val: List[Any]) -> TypeGuard[List[MaltegoLinkProperty[Any]]]:
    """Determines whether all objects in the list are strings"""
    return all(isinstance(x, MaltegoLinkProperty) for x in val)


def _schema_expectations(ann_type: typing.Optional[type]) -> tuple[bool, bool]:
    """Return (expected_is_entity, allow_list) from annotated type."""
    if ann_type is None:
        return (False, False)
    origin = typing.get_origin(ann_type)
    if origin is list:
        inner = typing.get_args(ann_type)[0]
        return (isinstance(inner, MaltegoEntityMeta), True)
    return (isinstance(ann_type, MaltegoEntityMeta), False)


def _is_valid_property_type_schema_aware(
    name: str,
    value: EntityPropertyType,
    expected_is_entity: bool,
    allow_list: bool,
) -> bool:
    """Non-destructive validation against schema expectations."""
    if isinstance(value, list):
        if not allow_list:
            log.warning(f"Property {name} is not a list but got list")
            return False
        if not value:
            return True
        if expected_is_entity:
            return all(isinstance(v, MaltegoEntity) for v in value)
        return all(isinstance(v, EntityPropertyTypePrimitive) for v in value)  # type: ignore

    if expected_is_entity:
        return isinstance(value, MaltegoEntity)
    return isinstance(value, EntityPropertyTypePrimitive)  # type: ignore

# Maximum length for date/date-time/date-range string values before parsing.
# dateutil.parser.parse() has superlinear CPU behaviour on certain inputs; reject
# anything longer than this constant BEFORE calling parse() to bound the worst case.
_DATE_VALUE_MAX_LEN = 64


def _assert_date_str_len(value: str, property_type: str) -> None:
    """Raise ValueError fast if a date string exceeds the safe length cap."""
    if len(value) > _DATE_VALUE_MAX_LEN:
        raise ValueError(
            f"Date value for property type '{property_type}' exceeds maximum "
            f"allowed length of {_DATE_VALUE_MAX_LEN} characters."
        )


def parse_str_type_to_value(property_value: Any, property_type: str) -> Any:
    if isinstance(property_value, list):
        return [parse_str_type_to_value(value, property_type) for value in property_value]
    if property_type == 'DATE_TIME' and property_value:
        _assert_date_str_len(property_value, property_type)
        return dateutil.parser.parse(property_value)
    if property_type == 'DATE_RANGE' and property_value:
        _assert_date_str_len(property_value, property_type)
        return daterange.fromstring_v3(property_value)
    if property_type == 'DATE' and property_value:
        _assert_date_str_len(property_value, property_type)
        return dateutil.parser.parse(property_value).date()
    return property_value


__all__ = [
    "MaltegoEntityProperty",
    "MaltegoEntity",
    "MEF",
    "OverlayPositions",
    "OverlayTypes",
    "Overlay",
    "MaltegoEntityConfig",
    "PossiblePropertyTypes",
    "MaltegoEntityConfig",
    "Bookmark",
    "MaltegoEntityAction",
    "MaltegoActionType",
    "MaltegoEntityRegexConverter"
]


MaltegoEntityType = TypeVar("MaltegoEntityType", bound="MaltegoEntityMeta")


def enforce_annotated_type(
        value: Any,
        defined_property_type: Type[EntityPropertyTypeUnion],
        return_converted: bool = False
) -> Any:
    """
    Make sure that 'value' matches its type hint:
        - None is always acceptable
        - A direct subclass is acceptable
        - If the type is a mismatch, 'coerce_property_type_from_value(value, defined_property_type)' is called
        - In case of a List type, the first element is always checked
        - If return_converted is set, then all list elements are checked and type-coerced
    :param value:
    :param defined_property_type:
    :param return_converted:
    :return:
    """
    if value is None or defined_property_type is None:
        return None
    actual_type = type(value)
    # check if property value is Entity-typed, if so, only enforce same entity types
    if isinstance(actual_type, MaltegoEntityMeta):
        if actual_type != defined_property_type:
            raise TypeError(
                f"Cannot set property with type '{actual_type}' to a '{defined_property_type}'-annotated property."
            )
    origin = typing.get_origin(defined_property_type)
    if origin is not None:
        assert origin == list, "The only allowed generic property type is 'List[..]'"
        inner_type = typing.get_args(defined_property_type)[0]
        if isinstance(value, str):
            # Check if inner_type is a primitive type that supports comma-splitting
            is_primitive = False
            try:
                is_primitive = issubclass(inner_type, EntityPropertyTypePrimitive)  # type: ignore
            except TypeError:
                # inner_type is not a class (could be a generic type), not primitive
                pass

            if is_primitive or inner_type == str:
                # Maltego sends comma-separated strings for arrays of primitives
                # This means you can specify a single comma-separated string for array properties
                return enforce_annotated_type(value.split(","), defined_property_type, return_converted)
            else:
                # For non-primitive list types (like List[Entity]), wrap in a list
                # to maintain type consistency with the List[T] annotation
                log.warning(
                    f"Cannot split string to {defined_property_type} by commas. "
                    f"Expected a list but got a string. Wrapping in a single-item list."
                )
                if return_converted:
                    return [value]
                return None
        if not issubclass(actual_type, typing.Iterable):
            raise TypeError(
                f"Cannot set non-iterable value '{value}' to a '{defined_property_type}'-annotated property."
            )

        if return_converted:
            return [enforce_annotated_type(val, inner_type, return_converted) for val in value]
        #  this consumes generators
        #  (but honestly we should probably just disallow setting generators as properties anyway)
        vals = list(value)
        first_elem = None if not vals else value[0]
        # just check first element
        enforce_annotated_type(first_elem, inner_type, return_converted)
    elif value is None or issubclass(actual_type, defined_property_type):
        if return_converted:
            return value
    else:
        try:
            result_val = coerce_property_type_from_value(
                value,
                defined_property_type
            )
            if return_converted:
                return result_val
        except Exception as exception:
            raise TypeError(
                f"Cannot convert value '{str(value)}' to type '{defined_property_type}': {exception}"
            )
    return None



class MaltegoEntityMeta(type):
    # Not the best place but needed for entity type string to class registry.
    # This allows us to access MaltegoEntity['maltego.Xyz'] to get a MaltegoEntity() instance
    _registry: Dict[Optional[str], Type[MaltegoEntity]] = {}
    value_property_attribute_name: Optional[str] = None
    TYPE_NAME: Optional[str] = None
    entity_properties: Dict[str, _MaltegoEntityProperty[Any]]

    @staticmethod
    def get_entity_from_registry(entity_id: str) -> Optional[Type[MaltegoEntity]]:
        return MaltegoEntityMeta._registry.get(entity_id)

    @staticmethod
    def __merge_config__(
            name: str,
            bases: Tuple[type, ...],
            child_config: Optional[MaltegoEntityConfig]
    ) -> "MaltegoEntityConfig":
        merged_config = None

        compatible_bases = [base for base in bases if issubclass(base, MaltegoEntity)]

        for base in compatible_bases:
            merged_config = merge_maltego_entity_config(merged_config, base.Config)

        final_config = merge_maltego_entity_config(child_config, merged_config)
        if final_config is None:
            final_config = MaltegoEntityConfig(
                display_name=name
            )

        additional_bases = []
        for base in compatible_bases:
            if base is not MaltegoEntity and hasattr(base, "TYPE_NAME") and isinstance(base.TYPE_NAME, str):
                additional_bases.append(base.TYPE_NAME)

        final_config.set_base_entities(additional_bases)

        if final_config is None:
            raise TypeError(f"Could not infer entity config for {name}")
        return final_config

    @staticmethod
    def __finalize_config__(name: str, bases: Tuple[type, ...], dct: Dict[str, Any]) -> MaltegoEntityConfig:
        entity_config = dct.get("Config", None)
        if isinstance(entity_config, MaltegoEntityConfig):
            display_name = entity_config.display_name
        else:
            log.warning(
                f"Entity {name} does not define a Config. "
                f"Overwrite inherited display_name with {name}"
            )
            display_name = name

        final_config = MaltegoEntityMeta.__merge_config__(name, bases, entity_config)
        final_config.display_name = display_name
        return final_config

    @staticmethod
    def __get_properties_from_annotations__(
        dct: Dict[str, Any],
        entity_properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        for property_name, annotation in _namespace_annotations(dct).items():
            if property_name in RESERVED_ENTITY_ATTRIBUTES:
                continue
            if property_name.startswith("_"):
                continue
            if _contains_union(annotation):
                raise TypeError(
                    f"Property '{property_name}' on entity '{dct.get('TYPE_NAME')}' "
                    f"uses a Union[...] annotation which is not supported. "
                    f"Use a single type (e.g. List[Person], List[str], str, ...) for a property."
                )

            if property_name in entity_properties:
                entity_properties[property_name].annotated_type = annotation
            else:
                entity_properties[property_name] = mef_from_simple_annotation(
                    property_name,
                    annotation
                )
        return entity_properties

    @staticmethod
    def __is_valid_property(property_name: str, entity_property: Any) -> bool:
        if property_name in RESERVED_ENTITY_ATTRIBUTES:
            return False
        if callable(entity_property):
            return False
        if isinstance(entity_property, classmethod):
            return False
        if isinstance(entity_property, staticmethod):
            return False
        if property_name.startswith("_"):
            return False
        return True

    @staticmethod
    def __get_entity_properties__(dct: Dict[str, Any]) -> Dict[str, Any]:
        entity_properties: Dict[str, Any] = {}
        for property_name, entity_property in dct.items():
            if not MaltegoEntityMeta.__is_valid_property(property_name, entity_property):
                continue

            if isinstance(entity_property, _MaltegoEntityProperty):
                if entity_property.name is None:
                    entity_property.name = property_name
                if entity_property.display_name is None:
                    entity_property.display_name = generate_default_property_name(property_name)
                entity_properties[property_name] = entity_property
            else:
                entity_properties[property_name] = mef_from_value(
                    property_name,
                    entity_property
                )
        return MaltegoEntityMeta.__get_properties_from_annotations__(dct, entity_properties)

    @staticmethod
    def __compile_entity_properties__(name: str, bases: Tuple[type, ...], dct: Dict[str, Any]) -> Dict[str, Any]:
        entity_properties: Dict[str, Any] = {}
        if name == "MaltegoEntity":
            return entity_properties
        for base in bases:
            if not issubclass(base, MaltegoEntity):
                continue
            for property_name, property_definition in base.entity_properties.items():
                entity_properties[property_name] = property_definition.copy()
                entity_properties[property_name].inherited = True

        for property_name, entity_prop in MaltegoEntityMeta.__get_entity_properties__(dct).items():
            entity_properties[property_name] = entity_prop
        return entity_properties

    def __new__(
        cls,
        name: str,
        bases: Tuple[type, ...],
        dct: Dict[str, Any]
    ) -> "MaltegoEntityMeta":
        dct["entity_properties"] = MaltegoEntityMeta.__compile_entity_properties__(
            name,
            bases,
            dct
        )
        dct["_attr_name_to_property_id"] = {}
        for attribute_id, property_ in dct["entity_properties"].items():
            dct["_attr_name_to_property_id"][attribute_id] = property_.name

        dct["_ROOT_ENTITY"] = False
        if name == "MaltegoEntity":
            dct[COMPOSITE_ATTR] = False
            dct["is_composite"] = classmethod(lambda cls_: False)
            dct["_ROOT_ENTITY"] = True
            return super().__new__(cls, name, bases, dct)
        dct["Config"] = MaltegoEntityMeta.__finalize_config__(name, bases, dct)

        # Set value_property_attribute_name class attribute to save lookups later
        value_property = dct["Config"].value_property
        for attribute_name, entity_prop in dct["entity_properties"].items():
            if entity_prop.name == value_property:
                dct["value_property_attribute_name"] = attribute_name
                break

        inherited_composite = any(
            issubclass(base, MaltegoEntity) and getattr(base, COMPOSITE_ATTR, False)
            for base in bases
        )
        has_entity_typed_field = any(p.is_entity_type() for p in dct["entity_properties"].values())
        dct[COMPOSITE_ATTR] = bool(inherited_composite or has_entity_typed_field)

        def _is_composite(cls_) -> bool:
            return bool(getattr(cls_, COMPOSITE_ATTR, False))

        dct["is_composite"] = classmethod(_is_composite)

        maltego_entity_class = super().__new__(cls, name, bases, dct)
        assert issubclass(maltego_entity_class, MaltegoEntity)

        if name == "MaltegoEntity":
            MaltegoEntityMeta.try_add_registry(ALL_ENTITY_TYPES, maltego_entity_class)

        _entity_config = maltego_entity_class.Config
        if not _entity_config:
            raise ValueError(f"Can not create class {name} missing MaltegoEntityConfig")
        if _entity_config.value_property is not None and maltego_entity_class.value_property_attribute_name is None:
            raise ValueError(
                f"Specified value property '{value_property}' does not exist on Entity type {name}. "
                f"Make sure to specify the Maltego-level property ID (rather than the python attribute name)."
                f"These are often the same, but the Maltego property ID can override the attribute name if the "
                f"'name' parameter in the 'MaltegoEntityField' definition is specified."
            )

        type_name = dct.get("TYPE_NAME")
        if type_name and type_name in MaltegoEntityMeta._registry:
            raise TypeError(
                f"Entity {name} with type id {type_name} already exists in registry: "
                f"{MaltegoEntityMeta._registry[type_name]}"
            )
        if type_name and type_name != ALL_ENTITY_TYPES:
            MaltegoEntityMeta.try_add_registry(type_name, maltego_entity_class)
        return maltego_entity_class

    @classmethod
    def try_add_registry(cls, type_name: Optional[str], entity: Type[MaltegoEntity]) -> bool:
        if type_name is None or type_name in cls._registry:
            return False
        MaltegoEntityMeta._registry[type_name] = entity
        return True

    @classmethod
    def try_get_registry(cls, type_name: str) -> Optional[MaltegoEntityMeta]:
        if type_name is None or type_name not in cls._registry:
            return None
        return MaltegoEntityMeta._registry[type_name]

    # This allows us to create type signatures for entities we don't know about
    def __getitem__(cls, item: str) -> "MaltegoEntityMeta":
        return MaltegoEntityMeta.from_string(item)

    # This allows us to create type signatures for entities we don't know about
    @classmethod
    def from_string(cls, item: str, value_attr: str = "text") -> "MaltegoEntityMeta":
        if not isinstance(item, str):
            raise TypeError(
                f"Can only create {cls.__class__.__name__} metaclass instances using str parametrization")
        if item in MaltegoEntityMeta._registry:
            res = MaltegoEntityMeta._registry[item]
            return res

        cls_ = MaltegoEntityMeta.__new__(
            MaltegoEntityMeta,
            "AnonymousMaltegoEntity",
            (MaltegoEntity,),
            {
                '__module__': 'maltego.model.entity',
                '__qualname__': 'MaltegoEntityMeta.from_string.<locals>.AnonymousMaltegoEntity',
                '__annotations__': {value_attr: 'str'},
                'TYPE_NAME': item,
                'Config': MaltegoEntityConfig(
                    value_property=value_attr,
                    display_property=value_attr
                )
            })

        # The synthetic dct above injects the annotation as the string literal 'str'
        # (not an evaluated type), so on every Python version AnonymousMaltegoEntity's
        # collected annotation starts life as a string rather than the str type. We
        # therefore force the resolved type explicitly so the annotation is represented
        # as the actual type elsewhere in the code (specifically where types are
        # enforced). This override is independent of Python version and of the
        # module-level "from __future__ import annotations".
        cls_.entity_properties[value_attr].annotated_type = str

        return cls_

    def __iter__(cls) -> None:
        raise TypeError(f'{cls.__class__.__name__} object is not iterable')


def _is_uniform_list(name: str, value: EntityPropertyType) -> bool:
    if isinstance(value, list) and len(value) > 0:
        first = type(value[0])
        for elem in value:
            if not isinstance(elem, first):
                log.warning(
                    f"Non-uniform elements in list of property {name}: First Element is {first}, current {type(elem)}"
                )
                return False
    return True


def _is_supported_type_hint(t: Type[Any]) -> bool:
    """Check if a type hint is supported by the Maltego desktop client."""
    if t is None:
        return True
    origin = typing.get_origin(t)
    if origin is list:
        inner = typing.get_args(t)[0] if typing.get_args(t) else None
        if inner:
            if isinstance(inner, MaltegoEntityMeta):
                return True
            try:
                return issubclass(inner, EntityPropertyTypePrimitive)  # type: ignore
            except TypeError:
                return False
        return False
    if isinstance(t, MaltegoEntityMeta):
        return True
    try:
        return issubclass(t, EntityPropertyTypePrimitive)  # type: ignore
    except TypeError:
        return False


def _is_valid_property_type(name: str, value: EntityPropertyType) -> bool:
    """Check if a property value is valid (runtime type check on values)."""
    if isinstance(value, list):
        for elem in value:
            if isinstance(elem, MaltegoEntity):
                return True
            if not isinstance(elem, EntityPropertyTypePrimitive):  # type: ignore
                log.warning(f"Unknown list property type {type(elem)} for property {name}")
                return False
    else:
        if isinstance(value, MaltegoEntity):
            return True
        if not isinstance(value, EntityPropertyTypePrimitive):  # type: ignore
            log.warning(f"Unknown property type {type(value)} for property {name}")
            return False
    return True


class MaltegoEntity(Observable, metaclass=MaltegoEntityMeta):
    """This is a conceptual class representation of a generic Maltego Entity

    :param value: The "value" of the entity. This value gets assigned to the value
                  property of the entity. This is used to be able to instantiate
                  entities like this: Phrase("Hello World")
    :type value: Any
    """
    Config: MaltegoEntityConfig = MaltegoEntityConfig()
    TYPE_NAME: str = ALL_ENTITY_TYPES
    enum_keys: List[str] = [
        "bookmark",
        "link_style",
        "link_color",
        "link_thickness"
    ]

    ICON_URL_PROPERTY_ID: str = "reserved-entity-icon-overlay-url"

    def __init__(
            self,
            value: Any,
            weight: int = 100,
            maltego_entity_id: Optional[str] = None,
            icon_url: Optional[str] = None,
            properties: Optional[Dict[str, _MaltegoEntityProperty[Any]]] = None,
            note: Optional[str] = None,
            display_information: Optional[List[_DisplayInformationItem]] = None,
            bookmark: Optional[Bookmark] = None,
            link_label: Optional[str] = None,
            reverse_link: bool = False,
            link_style: LinkStyle = LinkStyle.NORMAL,
            link_color: LinkColor = LinkColor.NONE,
            link_thickness: LinkThickness = LinkThickness.THICKNESS_DEFAULT,
            overlays: Optional[List[Overlay]] = None,
    ):
        super().__init__()
        self.maltego_entity_id = maltego_entity_id or create_maltego_id()
        if hasattr(self, "_ROOT_ENTITY") and getattr(self, "_ROOT_ENTITY", False):
            raise TypeError(
                "Can't directly instantiate MaltegoEntity object, use MaltegoEntity['some.type.name'] "
                "(or a built-in subclass like maltego.entities.Domain)"
            )

        self._properties = {
            # The current _MaltegoEntityProperty implementation poorly
            # separates the abstraction of a property definition
            # and a property value. Because of this, we have to
            # deepcopy props here in order to make sure we do not
            # change any default values etc. across the whole class,
            # but only within one instance.
            prop_def.name: prop_def.copy()
            for name, prop_def in
            self.__class__.entity_properties.items() if prop_def.name is not None
        }

        self.value = value

        # Initialize attributes that might be accessed during set_property() calls
        # These must be set before the properties loop to avoid AttributeError
        self.display_information = display_information or []
        self.overlays = overlays or []
        self._bookmark = bookmark
        self._weight = weight
        self._note = note
        self.reverse_link = reverse_link
        self.link_style = link_style
        self.link_color = link_color
        self.link_thickness = link_thickness
        self.link_label = link_label

        properties = properties or {}
        for key, mef_object in properties.items():
            assert isinstance(mef_object, _MaltegoEntityProperty)
            self.set_property(
                key,
                mef_object.value,
                display_name=mef_object.display_name,
                matching_rule=mef_object.matching_rule
            )

        if icon_url is not None:
            self.icon_url = icon_url
            
        # list of all inherited types (most specific first, most abstract last)
        self.genealogy: Optional[List[str]] = None
        self._emit_metadata = None

    def __repr__(self) -> str:
        try:
            if isinstance(self.value, MaltegoEntity):
                value_repr = f"<{self.value.TYPE_NAME}>"
            else:
                value_str = str(self.value)
                value_repr = value_str if len(value_str) <= 100 else value_str[:100] + "..."
        except RecursionError:
            value_repr = "<recursion detected>"
        except Exception:
            value_repr = "<error>"
        return f"MaltegoEntity['{self.TYPE_NAME}'](value={value_repr})"

    def __contains__(self, item: str) -> bool:
        return item in self._properties

    def __getattribute__(self, item: str) -> Any:
        self_dict = object.__getattribute__(self, "__dict__")
        if "_properties" in self_dict:
            properties = object.__getattribute__(self, "_properties")
            map_dict = object.__getattribute__(self, "_attr_name_to_property_id")
            item = map_dict.get(item, item)
            if item in properties:
                return properties[item].value
        return object.__getattribute__(self, item)

    def __set_enum__(self, key: str, value: Optional[int]) -> None:
        if key == "bookmark":
            return super().__setattr__(key, ensure_enum_val(value, Bookmark))
        if key == "link_style":
            return super().__setattr__(key, ensure_enum_val(value, LinkStyle))
        if key == "link_color":
            return super().__setattr__(key, ensure_enum_val(value, LinkColor))
        if key == "link_thickness":
            return super().__setattr__(key, ensure_enum_val(value, LinkThickness))
        raise ValueError(f"Could not parse enum {key}: {value}")

    def __setattr__(self, key: str, value: Any) -> None:
        # Maltego-internal property names like "properties.url" are not settable this way, use set_property instead
        if key in self.enum_keys:
            return self.__set_enum__(key, value)

        if key == "value":
            if self.Config.value_property is None:
                return super().__setattr__("value", value)
            value_property = self._properties[self.Config.value_property]
            try:
                value_property.value = self.parse_property_type(
                    self.Config.value_property, value, value_property.annotated_type
                )
            except TypeError:
                value_property.value = value
            self.notify_update(self, self.Config.value_property, value_property)
            return super().__setattr__("value", value)
        if key in self.entity_properties:
            if isinstance(value, _MaltegoEntityProperty):
                raise ValueError(
                    "Use set_property if you want to update property behavior")
            key = self._attr_name_to_property_id.get(key, key)
            self.set_property(key, value)
        else:
            if key in [entity_prop.name for entity_prop in self.entity_properties.values()]:
                raise ValueError(
                    "Use MaltegoEntity.set_property(...) to set Maltego-internal property names directly!"
                )
        return super().__setattr__(key, value)

    def _add_display_label_or_field(self, name: str, value: str, content_type: str, type_: str) -> None:
        if content_type == 'text/markdown':
            content_type = 'text/html'
            try:
                value = markdown.markdown(
                    value,
                    extensions=['tables', 'fenced_code',
                                'nl2br', 'sane_lists']
                )
            except UnicodeDecodeError as exception:
                log.error(
                    f"Error in decoding unicode markdown text {value}: {exception}")
            except ValueError as exception:
                log.error(
                    f"Error in decoding unicode markdown text {value}: {exception}")
            # Sanitize the generated HTML to strip <script>, inline event
            # handlers (on*), and javascript:/data: URLs before storing.
            # Markdown formatting (headings, links, lists, tables, code) is preserved.
            value = nh3.clean(
                value,
                tags=_DISPLAY_HTML_ALLOWED_TAGS,
                attributes=_DISPLAY_HTML_ALLOWED_ATTRS,
                link_rel=None,          # don't force-add rel="noopener" (keep author's rel)
                strip_comments=True,
            )
        elif content_type == 'text/html':
            # Sanitize caller-supplied raw HTML so that add_display_field_html() /
            # add_display_label() with content_type="text/html" cannot smuggle
            # <script> or event handlers into the display panel.
            value = nh3.clean(
                value,
                tags=_DISPLAY_HTML_ALLOWED_TAGS,
                attributes=_DISPLAY_HTML_ALLOWED_ATTRS,
                link_rel=None,
                strip_comments=True,
            )
        if type_ == 'label':
            display_label = DisplayLabel(name, value, content_type=content_type)
            self.notify_update(self, 'display_information', display_label)
            return self.display_information.append(display_label)
        if type_ == 'field':
            display_field = DisplayField(name, value, content_type=content_type)
            self.notify_update(self, 'display_information', display_field)
            return self.display_information.append(display_field)
        raise ValueError(
            "_add_display_label_or_field: type_ needs to be in ['label', 'field']")

    @classmethod
    def base_entity_types(cls) -> Set[str]:
        entity_bases = set()
        for base in inspect.getmro(cls):
            if issubclass(base, MaltegoEntity) and base is not MaltegoEntity and isinstance(base.TYPE_NAME, str):
                entity_bases.add(base.TYPE_NAME)
        return entity_bases

    def add_display_label(self, name: str, value: str, content_type: str = "text/html") -> None:
        """Adds a display label to an entity

        :param name: The name of the display label
        :type: name: str
        :param value: The value of the display label
        :type: value: str
        :param content_type: The content_type of the display label. Either html or markdown.
                             If the values string contains correct html/markdown
                             it will be rendered in the maltego client
        :type: content_type: Literal["text/html", "text/markdown"]
        """
        return self._add_display_label_or_field(name, value, content_type, 'label')

    def add_display_field(
            self,
            name: str,
            value: str,
            content_type: str = "text/html"
    ) -> None:  # not sure if field vs label is any different
        """Adds a display field to an entity

        :param name: The name of the display label
        :type: name: str
        :param value: The value of the display label
        :type: value: str
        :param content_type: The content_type of the display label. Either html or markdown.
                             If the values string contains correct html/markdown
                             it will be rendered in the maltego client
        :type: content_type: Literal["text/html", "text/markdown"]
        """
        return self._add_display_label_or_field(name, value, content_type, 'field')

    def add_display_field_markdown(
            self,
            name: str,
            value: str,
    ) -> None:
        """Helper function to add markdown as a display field.

        :param name: _description_
        :type name: str
        :param value: _description_
        :type value: str
        :return: _description_
        :rtype: _type_
        """
        return self._add_display_label_or_field(name, value, 'text/markdown', 'field')

    def add_display_field_html(
            self,
            name: str,
            value: str,
    ) -> None:
        """per function to add html text as a display field.

        :param name: _description_
        :type name: str
        :param value: _description_
        :type value: str
        :return: _description_
        :rtype: _type_
        """
        return self._add_display_label_or_field(name, value, 'text/html', 'field')

    def add_overlay(
            self,
            overlay_type: OverlayTypes,
            position: OverlayPositions,
            property_name: str
    ) -> None:
        if not isinstance(overlay_type, OverlayTypes):
            raise ValueError("add_overlay: Overlay type must be of type OverlayTypes")

        if not isinstance(position, OverlayPositions):
            raise ValueError("add_overlay: Overlay position must be of type OverlayPositions")

        overlay = Overlay(
            overlay_type=overlay_type.value,
            position=position.value,
            property_name=property_name
        )
        self.overlays.append(overlay)

        self.notify_update(self, 'overlays', overlay)

    def get_properties(self) -> Dict[str, PossiblePropertyTypes]:
        return self._properties

    def has_property(self, property_name: str) -> bool:
        return property_name in self._properties

    def get_property(
            self,
            name: str,
            default_value: Optional[
                Union[str, float, int, bool, datetime.date, datetime.datetime, daterange]
            ] = None
    ) -> Optional[Union[str, float, int, bool, datetime.date, datetime.datetime, daterange]]:
        """Returns a property, identified by its property_id

        :param name: The property id to return
        :type name: str
        :param default_value: Default value. Returned in case the entity property does not exist or None,
                              defaults to None
        :type default_value: Optional[Union[str, float, int, bool, datetime.date, datetime.datetime, daterange]],
                             optional
        :return: Returns the property value or the default value as fallback
        :rtype: Optional[Union[str, float, int, bool, datetime.date, datetime.datetime, daterange]]
        """
        entity_property = self._properties.get(name)
        if default_value and entity_property is None:
            return default_value
        return entity_property.value if entity_property is not None else None

    def __set_property(
        self,
        name: str,
        value: Optional[EntityPropertyType],
        matching_rule: Optional[MatchingRule] = None,
        try_parsing: bool = True
    ) -> None:
        property_obj: _MaltegoEntityProperty[Any] = self._properties[name]
        ann_type = property_obj.annotated_type
        if try_parsing:  # this is mostly just used by server-side parsing of incoming client requests
            value = self.parse_property_type(name, value, ann_type)
        old_value = property_obj.value
        property_obj.set_value(value)
        property_obj.matching_rule = (
            matching_rule or property_obj.matching_rule
        )  # allow overriding
        if self.Config is not None and self.Config.value_property == name:
            # In this case we force-set the value since any needed validation would already have been done above.
            super().__setattr__("value", value)
        # Notify all observers of the update
        if old_value != value:
            self.notify_update(self, '_properties', [property_obj])

    def __set_dynamic_property(
        self,
        name_simple: str,
        value: Optional[EntityPropertyType],
        display_name: Optional[str] = None,
        matching_rule: Optional[MatchingRule] = None,
        property_type: Optional[Type[Any]] = None,
    ) -> None:
        """
        Set a dynamic property on the entity.

        :param name_simple: Property name
        :param value: Property value
        :param display_name: Display name for the property
        :param matching_rule: Matching rule for the property
        :param property_type: Optional type hint for explicit type coercion
                              If not provided, type is inferred from value
        """
        # TODO: This function has grown too large and should be refactored into smaller,
        # focused functions for type inference, validation, and coercion.
        if not display_name:
            log.debug(
                f"You're setting a dynamic property ('{name_simple}') "
                f"with no display name, this is usually a mistake."
            )

        # if no type hint provided - infer from value
        if property_type is None:
            if value is not None and not _is_valid_property_type(name_simple, value):
                # Unsupported type - _is_valid_property_type already logs warning
                # Try to cast to string, but skip property if that fails too
                try:
                    value = str(value)
                    property_type = str
                except Exception as e:
                    log.error(
                        f"Cannot convert unsupported value for dynamic property '{name_simple}' to string. "
                        f"Skipping this property. Error: {e}"
                    )
                    return  # Skip setting this property, but don't fail the transform
            else:
                # Supported type - infer from value
                if isinstance(value, list) and value:
                    # Infer List[inner_type] from first element
                    inner_type = type(value[0])
                    property_type = List[inner_type]  # type: ignore
                else:
                    property_type = type(value) if value is not None else str

        # if type hint provided - validate and coerce
        else:
            # Check if type hint is supported
            if not _is_supported_type_hint(property_type):
                log.warning(
                    f"Dynamic property '{name_simple}' has unsupported type hint {property_type}. "
                    f"The Maltego desktop client only supports primitive types (str, int, float, bool, date, datetime) "
                    f"and MaltegoEntity, or lists thereof. Converting value to string."
                )
                try:
                    value = str(value)
                    property_type = str
                except Exception as e:
                    log.error(
                        f"Cannot convert value for dynamic property '{name_simple}' to string. "
                        f"Skipping this property. Error: {e}"
                    )
                    return  # Skip setting this property, but don't fail the transform
            else:
                # Try to coerce value to the specified type
                if value is not None and not isinstance(value, property_type):
                    try:
                        # Attempt coercion using the existing coercion logic
                        value = coerce_property_type_from_value(value, property_type)
                    except (TypeError, ValueError) as e:
                        log.warning(
                            f"Cannot coerce value for dynamic property '{name_simple}' "
                            f"from {type(value).__name__} to {property_type}. "
                            f"Converting to string. Error: {e}"
                        )
                        try:
                            value = str(value)
                            property_type = str
                        except Exception as str_err:
                            log.error(
                                f"Cannot convert value for dynamic property '{name_simple}' to string. "
                                f"Skipping this property. Error: {str_err}"
                            )
                            return  # Skip setting this property, but don't fail the transform

        new_property = _MaltegoEntityProperty(
            name=name_simple,
            display_name=display_name,
            matching_rule=matching_rule if matching_rule else MATCHING_RULE_LOOSE,
            value=value,
            annotated_type=property_type
        )
        old_value = None
        if name_simple in self._properties:
            old_value = self._properties[name_simple].value

        self._properties[name_simple] = new_property
        # flag composition on the instance if we add an entity-typed property dynamically
        if isinstance(property_type, MaltegoEntityMeta):
            if not getattr(self, COMPOSITE_ATTR, False):
                setattr(self, COMPOSITE_ATTR, True)
        elif typing.get_origin(property_type) is list:
            args = typing.get_args(property_type)
            if args and isinstance(args[0], MaltegoEntityMeta):
                if not getattr(self, COMPOSITE_ATTR, False):
                    setattr(self, COMPOSITE_ATTR, True)

        if value != old_value:
            self.notify_update(self, '_properties', [new_property])

    def parse_property_type(
        self,
        name: str,
        value: Optional[Any],
        annotated_type: Optional[EntityPropertyTypeMeta]
    ) -> Any:
        if annotated_type is None:
            return None
        try:
            return enforce_annotated_type(
                value,
                annotated_type,
                return_converted=True
            )
        except TypeError as ex:
            log.exception(
                f"Unable to correctly parse value '{value}' of property '{name}'"
                f" to type {annotated_type}."
            )
            raise ex
        return None

    def set_property(
            self,
            name: str,
            value: Optional[EntityPropertyType],
            display_name: Optional[str] = None,
            matching_rule: Optional[MatchingRule] = None,
            try_parsing: bool = True,
            property_type: Optional[Type[Any]] = None,
    ) -> None:
        """Sets a property to a given value and translate internal property names like
        "properties.name" to class attribute namespace

        :param name: The property id to set
        :type name: str
        :param value: The value of the property
        :type value: Any
        :param display_name: The display name of the property as shown by the maltego client, defaults to name
        :type display_name: Optional[str], optional
        :param matching_rule: The matching rule decides if the property should be used for merging, defaults to None
        :type matching_rule: Optional[MatchingRule], optional
        :param try_parsing: Try to parse the value to the correct property type, defaults to False
        :type try_parsing: bool, optional
        :param property_type: Optional type hint for dynamic properties to control type coercion.
                              If not provided, type is inferred from value. Only used for dynamic properties.
        :type property_type: Optional[Type[Any]], optional
        """

        def _ensure_no_entities_for_coercion(v):
            if isinstance(v, MaltegoEntity):
                raise TypeError(f"Cannot coerce MaltegoEntity to string for property '{name}'")
            if isinstance(v, list) and any(isinstance(x, MaltegoEntity) for x in v):
                raise TypeError(f"Cannot coerce list containing MaltegoEntity to string for property '{name}'")

        def _coerce_primitives(v):
            _ensure_no_entities_for_coercion(v)
            return [str(x) for x in v] if isinstance(v, list) else str(v)

        # short-circuit for dynamic properties
        if name not in self._properties:
            if isinstance(value, list) and value:
                all_ent = all(isinstance(v, MaltegoEntity) for v in value)
                none_ent = all(not isinstance(v, MaltegoEntity) for v in value)
                if not (all_ent or none_ent):
                    msg = f"Dynamic list property '{name}' must be all entities or all primitives"
                    log.error(msg)
                    raise TypeError(msg)
            return self.__set_dynamic_property(name, value, display_name, matching_rule, property_type)

        ann_type = self._properties[name].annotated_type if name in self._properties else None

        if value is not None:
            expected_is_entity, allow_list = _schema_expectations(ann_type)

            if not _is_valid_property_type_schema_aware(name, value, expected_is_entity, allow_list):
                if expected_is_entity:
                    msg = f"Invalid value for ENTITY-typed property '{name}': {type(value).__name__}"
                    log.error(msg)
                    raise MaltegoHTTPInputEntityMalformed(msg)

                # if a list is not expected it, coerce to a comma-separated string
                coerced = _coerce_primitives(value)
                if isinstance(coerced, list) and not allow_list:
                    coerced = ", ".join(coerced)

                return self.__set_property(name, coerced, matching_rule, try_parsing)

            if isinstance(value, list) and not expected_is_entity and not _is_uniform_list(name, value):
                # if a list is not expected it, coerce to a comma-separated string
                coerced = _coerce_primitives(value)
                if isinstance(coerced, list) and not allow_list:
                    log.warning(f"Property {name} is not a list but got list")
                    coerced = ", ".join(coerced)
                return self.__set_property(name, coerced, matching_rule, try_parsing)

        return self.__set_property(name, value, matching_rule, try_parsing)


    @classmethod
    def get_property_defs(cls) -> Dict[str, _MaltegoEntityProperty[EntityPropertyType]]:
        return cls.entity_properties or {}

    @builtins.property
    def icon_url(self) -> Optional[str]:
        """Returns the icon-url"""
        icon_url = self.get_property(self.ICON_URL_PROPERTY_ID, None)
        if isinstance(icon_url, str):
            return icon_url
        return None

    @icon_url.setter
    def icon_url(self, icon_url: str) -> None:
        self.__set_dynamic_property(
            self.ICON_URL_PROPERTY_ID,
            icon_url,
            "Image"
        )

    @builtins.property
    def weight(self) -> int:
        return self._weight

    @weight.setter
    def weight(self, weight: int) -> None:
        if self._weight != weight:
            self.notify_update(self, "weight", weight)
            self._weight = weight

    @builtins.property
    def note(self) -> Optional[str]:
        return self._note

    @note.setter
    def note(self, note: Optional[str]) -> None:
        if self._note != note:
            self.notify_update(self, "note", note)
        self._note = note

    @builtins.property
    def bookmark(self) -> Bookmark:
        return self._bookmark

    @bookmark.setter
    def bookmark(self, bookmark: Bookmark) -> None:
        log.warning(
            "Setting 'bookmark' is deprecated and ignored. This property is read-only "
            "and the setter will be removed in a future version."
        )

    @classmethod
    def field_is_entity_typed(cls, entity: Type["MaltegoEntity"], field_name: str) -> bool:
        """
        Checks the field in defined properties of the entity for ENTITY type
        :param entity:
        :param field_name:
        :return:
        """
        field = entity.get_property_defs().get(field_name)
        return field is not None and field.is_entity_type()

    @classmethod
    def has_entity_typed_field(cls, entity: Type[Union["MaltegoEntity", "MaltegoEntityMeta"]]) -> bool:
        """
        Check all defined properties of the entity for ENTITY type (including inherited)
        :param entity:
        :return:
        """
        return any(
            field.is_entity_type()
            for field in entity.get_property_defs().values()
        )

    @classmethod
    def is_composite(cls) -> bool:
        """
        Checks if the entity definition is composite
        (i.e. has at least one ENTITY-typed property)
        :return:
        """
        # Always present because the metaclass sets it during class creation
        return bool(getattr(cls, COMPOSITE_ATTR, False))

    @builtins.property
    def is_composite_instance(self) -> bool:
        """
        Checks if the entity instance is composite, including dynamic properties
        :return:
        """
        return bool(
            getattr(type(self), COMPOSITE_ATTR, False)
            or getattr(self, COMPOSITE_ATTR, False)
        )

    @classmethod
    def to_v3_entity_property_fields(cls, entity: Type["MaltegoEntity"], composed_graph: Optional[bool] = False) -> List[V3EntityField]:
        """
        Serializes JSON protocol property fields for entity definition
        :param entity:
        :param composed_graph: Whether to serialize with composition support
        :return:
        """
        fields: List[V3EntityField] = []
        for entity_field in entity.get_property_defs().values():
            if entity_field.inherited:
                continue

            if not composed_graph and entity_field.is_entity_type():
                # Downgrade ENTITY field to STRING if composition is not supported
                field_model = entity_field.to_field_model()
                field_model.type = "STRING"
                field_model.hidden = True
                field_model.readonly = True
                field_model.entity_type = None
                field_model.link_properties = None
                fields.append(field_model)
            else:
                fields.append(entity_field.to_field_model())
        return fields

    @classmethod
    def to_v3_entity_property_definitions(cls, entity: Type["MaltegoEntity"],
                                          composed_graph: Optional[bool] = False) -> V3EntityProperties:
        """
        Serializes JSON protocol entity property definitions
        :param entity:
        :param composed_graph: Whether to serialize with composition support
        :return:
        """
        if entity.Config is None:
            raise MaltegoHTTPServerError()

        config: MaltegoEntityConfig = entity.Config

        value_prop = config.value_property or ''
        display_prop = config.display_property
        value_key = config.value_key
        display_key = config._display_key

        if not composed_graph:
            # if composition is not supported, ensure value and display do not have ENTITY typed references
            if cls.field_is_entity_typed(entity, value_prop):
                value_prop = "legacy_wrapper_value"
                value_key = None

            if display_prop is not None and cls.field_is_entity_typed(entity, display_prop):
                display_prop = "legacy_wrapper_value"
                display_key = None

        fields = MaltegoEntity.to_v3_entity_property_fields(entity, composed_graph)

        # Inject fallback wrapper field if used
        if not composed_graph and ("legacy_wrapper_value" in {value_prop, display_prop}):
            fields.insert(
                0,
                V3EntityField(
                    name="legacy_wrapper_value",
                    type="STRING",
                    default_value="Wrapper entity (legacy)",
                    hidden=False,
                    readonly=True,
                    display_name="Legacy Label",
                    description="Fallback label for legacy clients.",
                    matching_rule="strict",
                    nullable=False,
                    is_array=False,
                )
            )

        return V3EntityProperties(
            value=value_prop,
            value_key=value_key,
            display_value=display_prop,
            display_key=display_key,
            image_overlay=config.overlay_image_property,
            fields=fields
        )

    @classmethod
    def to_v3_entity_definition(cls, entity: Type["MaltegoEntity"], composed_graph: Optional[bool] = False) -> V3EntityDefinition:
        """
        Serializes JSON protocol entity definition
        :param entity:
        :param composed_graph: Whether to serialize with composition support
        :return:
        """
        if entity.Config is None:
            raise MaltegoHTTPServerError(f"Invalid: Entity {type(entity)} has no Config")
        if entity.TYPE_NAME is None:
            raise MaltegoHTTPServerError(f"Invalid: Entity {type(entity)} TYPE_NAME is None")
        config: MaltegoEntityConfig = entity.Config
        overlays = config.overlays if config.overlays else []

        # if composition is not supported but entity has ENTITY-typed properties, downgrade them to STRING
        requires_downgrade = cls.has_entity_typed_field(entity) and not composed_graph

        # If downgrade required, force allowed_root = False
        # This means an entity with entity-typed properties needs to be downgraded,
        # and having it in the palette would be confusing without support for its real properties
        allowed_root = False if requires_downgrade else config.allowed_root
        return V3EntityDefinition(
            id=entity.TYPE_NAME,
            display_name=config.display_name,
            display_name_plural=config.display_name_plural,
            description=config.description,
            category=config.category,
            icon_resource=config.large_icon_resource,
            visible=config.visible,
            allowed_root=allowed_root,
            conversion_order=config.conversion_order,
            base_entities=config.get_base_entities(),
            properties=MaltegoEntity.to_v3_entity_property_definitions(entity, composed_graph),
            overlays=[
                V3EntityOverlay(
                    property_name=overlay.property_name,
                    position=overlay.position,
                    type=overlay.overlay_type
                ) for overlay in overlays
            ],
            regex_converter=V3EntityRegexConverter(
                regex=config.converter.regex,
                groups=config.converter.groups
            ) if config.converter else None,
            actions=[
                V3EntityAction(
                    name=action.name,
                    display_name=action.display_name,
                    config=action.config,
                    type=action.action_type.value
                )
                for action in config.actions
            ]

        )

    @classmethod
    def from_v3_run_entity(
            cls,
            run_model: TransformRunEntity,
            entity_typed_properties: Optional[Dict[str, MaltegoEntity]] = None,
    ) -> MaltegoEntity:
        """

        :param run_model: entity model from transform request
        :param entity_typed_properties: dictionary of entities for entity-typed properties.
                                        the request sends them as flat list of entities,
                                        we add them to the property values instead of reference strings
        :return: MaltegoEntity created from run_model
        """
        if not entity_typed_properties:
            entity_typed_properties = {}
        properties = {}

        for entity_property in run_model.properties or []:
            name = entity_property.name
            value = entity_property.value

            resolved_value = None

            if entity_property.type == "ENTITY":
                # resolve single id
                if isinstance(value, str):
                    if value not in entity_typed_properties:
                        msg = f"ENTITY property '{name}' references unknown id '{value}'"
                        log.error(msg)
                        raise MaltegoHTTPInputEntityMalformed(msg)
                    resolved_value = entity_typed_properties[value]

                # resolve list of ids
                elif isinstance(value, list):
                    if not all(isinstance(item, str) for item in value):
                        msg = f"ENTITY property '{name}' must be a list of string IDs; got: {value!r}"
                        log.error(msg)
                        raise MaltegoHTTPInputEntityMalformed(msg)
                    missing = [item for item in value if item not in entity_typed_properties]
                    if missing:
                        msg = f"ENTITY property '{name}' references unknown ids: {missing!r}"
                        log.error(msg)
                        raise MaltegoHTTPInputEntityMalformed(msg)
                    resolved_value = [entity_typed_properties[item] for item in value]
                else:
                    # anything else is invalid
                    msg = f"ENTITY property '{name}' must be a string ID or list of string IDs; got: {type(value).__name__}"
                    log.error(msg)
                    raise MaltegoHTTPInputEntityMalformed(msg)

            else:
                try:
                    resolved_value = parse_str_type_to_value(value, entity_property.type)
                except Exception:
                    log.exception(f"Could not handle property {name} with value {value!r}")
                    resolved_value = value

            properties[name] = _MaltegoEntityProperty(
                name=name,
                display_name=entity_property.display_name,
                value=resolved_value,
            )

        if run_model.id is None:
            if run_model.type is None:
                msg = "Transform run request entity has no id"
                log.error(msg)
                raise ValueError(msg)
            msg = f"Transform run request entity with type {run_model.type} has no id"
            log.error(msg)
            raise ValueError(msg)

        entity_type = str(run_model.type)
        entity_class: Optional[Type[MaltegoEntity]] = MaltegoEntityMeta.get_entity_from_registry(entity_type)

        if entity_class is None:
            bases = []
            for base_entity in run_model.base_entities or []:
                if base_entity_class := MaltegoEntityMeta.get_entity_from_registry(base_entity):
                    bases.append(base_entity_class)
            entity_class = type(
                "AnonymousMaltegoEntity",
                tuple(bases + [MaltegoEntity]),
                {"TYPE_NAME": entity_type}
            )

        assert issubclass(entity_class, MaltegoEntity)

        # Derive the ctor value as an entity if valueRef is ENTITY
        ctor_value = ""
        if run_model.value_ref and (prop_def := properties.get(run_model.value_ref)):
            v = prop_def.value
            # if the valueRef property is an entity, keep it as entity
            if isinstance(v, MaltegoEntity):
                ctor_value = v
            elif v is not None:
                ctor_value = str(v)

        model = entity_class(
            value=ctor_value,
            maltego_entity_id=run_model.id,
            properties=properties,
            bookmark=run_model.bookmark or Bookmark.NONE,
            weight=run_model.weight if run_model.weight is not None else 100,
            note=run_model.note,
        )
        assert isinstance(model, MaltegoEntity)

        model.genealogy = run_model.base_entities or []

        return model

    def to_v3_run_entity_from_id(self) -> TransformRunEntity:
        return TransformRunEntity(
            id=self.maltego_entity_id
        )

    def to_v3_run_entity(self, composed_graph: Optional[bool] = False) -> TransformRunEntity:
        if self.TYPE_NAME is None:
            raise MaltegoHTTPServerError(f"Invalid: Entity {type(self)} TYPE_NAME is None")
        return TransformRunEntity(
            id=self.maltego_entity_id,
            type=self.TYPE_NAME,
            value_ref=self.Config.value_property,
            weight=self.weight,
            properties=[
                property.to_v3_property(composed_graph) for property in self.get_properties().values() if property.value is not None
            ],
            display_information=[
                display_information.to_v3_display_information(
                ) for display_information in self.display_information if self.display_information
            ],
            bookmark=self.bookmark,
            overlays=[overlay.to_v3_overlay()
                      for overlay in self.overlays if self.overlays],
            note=self.note
        )

    def to_v3_run_entity_update(
            self,
            updates: dict[str, Any],
            composed_graph: Optional[bool] = False
    ) -> TransformRunEntity:

        updated_entity = TransformRunEntity(
            id=self.maltego_entity_id
        )

        for updated_property_name, updated_property_value in updates.items():
            if updated_property_name == '_properties':
                assert isinstance(updated_property_value, list) and (is_entity_property_list(updated_property_value))
                updated_property_value = [prop.to_v3_property(composed_graph) for prop in updated_property_value]
                if updated_entity.properties is None:
                    updated_entity.properties = []
                updated_entity.properties.extend(updated_property_value)
            elif isinstance(updated_property_value, _MaltegoEntityProperty):
                updated_property_value = [updated_property_value.to_v3_property(composed_graph)]
                if updated_entity.properties is None:
                    updated_entity.properties = []
                updated_entity.properties.extend(updated_property_value)
            elif isinstance(updated_property_value, Overlay):
                updated_property_value = [updated_property_value.to_v3_overlay()]
                setattr(updated_entity, updated_property_name, updated_property_value)
            elif isinstance(updated_property_value, (DisplayField, DisplayLabel)):
                updated_property_value = [updated_property_value.to_v3_display_information()]
                setattr(updated_entity, updated_property_name, updated_property_value)
            elif isinstance(updated_property_value, Bookmark):
                updated_property_value = updated_property_value.value
                setattr(updated_entity, updated_property_name, updated_property_value)
            else:
                setattr(updated_entity, updated_property_name, updated_property_value)

        return updated_entity

    def _set_composite_child(self):
        """
        Mark this entity as a composite child.
        """
        from maltego.model.types import AttributeNames, ENTITY_ATTRIBUTE_NAMESPACE
        attr_name = f"{ENTITY_ATTRIBUTE_NAMESPACE}.{AttributeNames.composite_child}"
        self.set_property(attr_name, True, attr_name)

    def _is_composite_child(self) -> bool:
        """
        Check if this entity is marked as a composite child.
        """
        from maltego.model.types import AttributeNames, ENTITY_ATTRIBUTE_NAMESPACE
        attr_name = f"{ENTITY_ATTRIBUTE_NAMESPACE}.{AttributeNames.composite_child}"
        return self.get_property(attr_name) is True

    def _get_internal_attributes(self) -> Dict[str, Any]:
        """
        Get all internal attribute properties under ENTITY_ATTRIBUTE_NAMESPACE.
        :return: Dict of attribute name (without namespace) to property value.
        """
        from maltego.model.types import ENTITY_ATTRIBUTE_NAMESPACE
        result = {}
        for prop in self._properties:
            if prop.startswith(f"{ENTITY_ATTRIBUTE_NAMESPACE}."):
                attr_name = prop[len(f"{ENTITY_ATTRIBUTE_NAMESPACE}."):]
                result[attr_name] = self.get_property(prop)
        return result

    def has_entity_typed_property(self) -> bool:
        return any(property.is_entity_type() for property in self._properties.values())


def coerce_property_type_from_value(value: Any, type_: Type[Any]) -> Any:
    if isinstance(value, type_):
        return value

    if issubclass(type_, bool):  # bool for some reason subclasses int, so we need to check it first
        return value in ("true", "True")

    if issubclass(type_, datetime.datetime):
        if not isinstance(value, str):
            raise TypeError(f"Cannot parse {type(value)} with dateutil")
        _assert_date_str_len(value, "DATE_TIME")
        return dateutil.parser.parse(value)

    if issubclass(type_, datetime.date):
        if not isinstance(value, str):
            raise TypeError(f"Cannot parse {type(value)} with dateutil")
        _assert_date_str_len(value, "DATE")
        return dateutil.parser.parse(value).date()

    if issubclass(type_, daterange):
        if isinstance(value, str):
            _assert_date_str_len(value, "DATE_RANGE")
        return daterange.fromstring_v3(value)

    if issubclass(type_, (Url, Color)):
        return str(value)

    if issubclass(type_, (str, int, float)):
        if isinstance(value, datetime.date):
            raise TypeError(f"Cannot parse {type(value)} to {type_}")
        if isinstance(value, daterange):
            raise TypeError(f"Cannot parse {type(value)} to {type_}")
        return type_(value)

    if issubclass(type_, MaltegoEntity):
        return type_(value)

    raise TypeError(f"Unable to coerce type '{type(value)}' to {type_}.")
