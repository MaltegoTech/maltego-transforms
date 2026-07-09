# Copyright (c) Maltego Technologies GmbH.
import datetime
from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Optional, Type, get_args, get_origin

from maltego.model.entity.type_handling import contains_entity, \
    infer_v3_type_from_property_value, \
    to_v3_entity_property_type, \
    to_v3_property_type
from maltego.model.link import MaltegoLink
from maltego.model.types import EntityPropertyType, EntityPropertyTypeMeta, LinkColor, LinkStyle, LinkThickness, \
    MATCHING_RULE_STRICT, \
    MatchingRule, \
    daterange, normalize_date, to_str_format, v3_property_types
from maltego.protocol.v3.discovery.entity import V3EntityField
from maltego.protocol.v3.discovery.transform import serialize_daterange
from maltego.protocol.v3.execution.property import Property

@dataclass
class LinkProperties:
    """
    This class is used to pre-define link properties of an entity-typed property
    """
    is_reversed: bool = False
    style: 'LinkStyle' = LinkStyle.NORMAL
    color: 'LinkColor' = LinkColor.NONE
    thickness: 'LinkThickness' = LinkThickness.THICKNESS_DEFAULT
    properties: Optional[Dict[str, Any]] = None
    label: Optional[str] = None


def generate_default_property_name(internal_property_name: str) -> str:
    cand = internal_property_name.capitalize()
    words = cand.split("_")
    upper = {"url", "ip", "ssl", "http", "https", "vin",
             "id", "dns", "zip", "sha1", "md5", "uid", "uuid"}
    replace = {"ipv4": "IPv4", "ipv6": "IPv6"}
    for i, word in enumerate(words):
        if word.lower() in upper:
            words[i] = word.upper()
        words[i] = replace.get(word, word)
    return " ".join(words).strip()


# MEL (Maltego Expression Language) functions that require an evaluator
MEL_EXPRESSION_FUNCTIONS = (
    "$coalesce(",
    "$trim(",
    "$property(",
)


def _validate_mel_expression(
    value: Optional[Any],
    evaluator: Optional[str],
    name: Optional[str] = None
) -> None:
    """
    Validate that MEL expressions in value have a required evaluator.

    MEL functions like $coalesce(), $trim(), $property() etc. require
    evaluator='maltego.replace' to be processed by the client.
    """
    if not isinstance(value, str) or evaluator is not None:
        return

    for mel_func in MEL_EXPRESSION_FUNCTIONS:
        if mel_func in value:
            field_info = f" for field '{name}'" if name else ""
            raise ValueError(
                f"MEF{field_info} with value containing '{mel_func[:-1]}()' requires "
                f"evaluator='maltego.replace'. Got value={value!r} without evaluator."
            )



class _MaltegoEntityProperty(Generic[EntityPropertyType]):

    def __init__(
            self,
            display_name: Optional[str] = None,
            name: Optional[str] = None,
            matching_rule: MatchingRule = MATCHING_RULE_STRICT,
            # this doubles as the default value when we're defining a full entity
            value: Optional[EntityPropertyType] = None,
            description: str = "",
            hidden: bool = False,
            readonly: bool = False,
            nullable: bool = True,
            sample_value: Optional[EntityPropertyType] = None,
            evaluator: Optional[str] = None,
            annotated_type: Optional[EntityPropertyTypeMeta] = str,
            link_properties: Optional[LinkProperties] = None,
    ) -> None:
        self.name = name  # might be changed/inferred in MaltegoEntityMeta class
        self.display_name = display_name  # might be inferred in MaltegoEntityMeta class
        self.description = description
        self.value: Optional[EntityPropertyType] = self.normalize_property_values(value)
        if contains_entity(sample_value):
            raise TypeError(
                "MEF(..., sample_value=…) only accepts primitive types (str/int/bool) "
                "or lists thereof."
            )
        self.sample_value: Optional[EntityPropertyType] = self.normalize_property_values(
            sample_value
        )

        self.default_value: Optional[EntityPropertyType] = self.normalize_property_values(value)
        self.annotated_type = annotated_type
        self.matching_rule: MatchingRule = matching_rule
        self.evaluator = evaluator
        _validate_mel_expression(value, evaluator, name)
        self.hidden = hidden
        self.readonly = readonly
        self.nullable = nullable
        self.inherited = False
        self.link_properties = link_properties

    @property
    def is_array(self) -> bool:
        if get_origin(self.annotated_type) == list:
            return True
        return False

    @property
    def primitive_type(self) -> Any:
        if get_origin(self.annotated_type) is None:
            return self.annotated_type
        if get_origin(self.annotated_type) == list:
            return get_args(self.annotated_type)[0]
        raise ValueError(f"{type(self.annotated_type)} has unparsable origin {get_origin(self.annotated_type)}")

    def is_entity_type(self) -> bool:
        return to_v3_property_type(self.primitive_type) == "ENTITY"

    def set_value(self, value: Optional[EntityPropertyType]) -> Optional[EntityPropertyType]:
        self.value = self.normalize_property_values(value)
        return self.value

    def normalize_property_values(self, value: Optional[EntityPropertyType]) -> Optional[EntityPropertyType]:
        if isinstance(value, datetime.datetime):
            normalized = normalize_date(value)
            assert isinstance(normalized, datetime.datetime)
            return normalized
        if isinstance(value, datetime.date):
            return normalize_date(value)
        return value

    def copy(self) -> "_MaltegoEntityProperty[EntityPropertyType]":
        res = _MaltegoEntityProperty(
            display_name=self.display_name, name=self.name, matching_rule=self.matching_rule, value=self.value,
            description=self.description, hidden=self.hidden, readonly=self.readonly, nullable=self.nullable,
            sample_value=self.sample_value, evaluator=self.evaluator, annotated_type=self.annotated_type
        )
        return res

    def __repr__(self) -> str:
        return (
            f"MaltegoEntityField(name={repr(self.name)}, "
            f"value={repr(self.value)}, "
            f"display_name={repr(self.display_name)}, "
            f"matching_rule={repr(self.matching_rule)},"
            f"annotated_type={repr(self.annotated_type)}, ...)"
        )

    @classmethod
    def from_simple_annotation(cls, property_name: str, annotation: Any) -> "_MaltegoEntityProperty[Any]":
        return cls(
            name=property_name,
            display_name=property_name,
            annotated_type=annotation
        )

    @classmethod
    def from_value(cls, property_name: str, value: Any) -> "_MaltegoEntityProperty[Any]":
        return cls(
            name=property_name,
            display_name=property_name,
            sample_value=value,
            value=value,
            annotated_type=type(value)
        )

    def to_field_model(self) -> V3EntityField:
        assert self.name is not None
        sample_value: Optional[Any] = None
        if isinstance(self.sample_value, daterange):
            sample_value = serialize_daterange(self.sample_value)
        elif isinstance(self.sample_value, datetime.datetime):
            sample_value = to_str_format(self.sample_value)
        elif isinstance(self.sample_value, datetime.date):
            sample_value = to_str_format(self.sample_value)
        else:
            sample_value = self.sample_value

        default_value: Optional[Any] = None
        if isinstance(self.default_value, daterange):
            default_value = serialize_daterange(self.default_value)
        elif isinstance(self.default_value, datetime.datetime):
            default_value = to_str_format(self.default_value)
        elif isinstance(self.default_value, datetime.date):
            default_value = to_str_format(self.default_value)
        else:
            default_value = self.default_value

        return V3EntityField(
            name=self.name,
            display_name=self.display_name,
            matching_rule=self.matching_rule,
            nullable=self.nullable,
            hidden=self.hidden,
            readonly=self.readonly,
            description=self.description,
            sample_value=sample_value,
            default_value=default_value,
            type=to_v3_property_type(self.primitive_type),
            is_array=self.is_array,
            evaluator=self.evaluator,
            link_properties=self.to_v3_link_properties(),
            entity_type=to_v3_entity_property_type(self.primitive_type)
        )

    def to_v3_link_properties(self) -> Optional[List[Property]]:
        # this function is used in entity discovery to show pre-defined link properties for entity-typed properties
        if self.link_properties is None:
            return None
        return MaltegoLink(source_id=None,
                           target_id=None,
                           is_reversed=self.link_properties.is_reversed,
                           style=self.link_properties.style,
                           color=self.link_properties.color,
                           thickness=self.link_properties.thickness,
                           label=self.link_properties.label,
                           properties=self.link_properties.properties,
                           ).to_v3_link_properties()

    def to_v3_property(self, composed_graph: Optional[bool] = False) -> Property:
        # TODO: consider adding support for when a property is to be deleted / set to None after initial ADD event
        from maltego.model import MaltegoEntity
        assert self.name
        property_type = infer_v3_type_from_property_value(self.value)
        if property_type == "ENTITY" and not composed_graph:
            property_type = "STRING"
        value: Optional[Any] = None

        if isinstance(self.value, daterange):
            value = serialize_daterange(self.value)
        elif isinstance(self.value, datetime.datetime):
            value = to_str_format(self.value)
        elif isinstance(self.value, datetime.date):
            value = to_str_format(self.value)
        elif isinstance(self.value, MaltegoEntity):
            value = self.value.maltego_entity_id
        elif (
                self.value
                and isinstance(self.value, list)
        ):
            value = [v.maltego_entity_id if isinstance(v, MaltegoEntity) else v for v in self.value]
        else:
            value = self.value
        assert value is not None
        return Property(
            name=self.name,
            value=value,
            type=property_type,
            display_name=self.display_name,
            matching_rule=self.matching_rule
        )


def mef_from_simple_annotation(property_name: str, annotation: Any) -> _MaltegoEntityProperty[Any]:
    return _MaltegoEntityProperty.from_simple_annotation(
        property_name, annotation
    )


def mef_from_value(property_name: str, value: Any) -> _MaltegoEntityProperty[Any]:
    return _MaltegoEntityProperty.from_value(
        property_name, value
    )


# Stolen from dataclasses:
# This function is used instead of exposing Field creation directly,
# so that a type checker can be told (via overloads) that this is a
# function whose type depends on its parameters.
def MEF(  # pylint: disable=invalid-name
        *,
        display_name: Optional[str] = None,
        name: Optional[str] = None,
        matching_rule: MatchingRule = MATCHING_RULE_STRICT,
        # this doubles as the default value when we're defining a full entity
        value: Optional[EntityPropertyType] = None,
        description: str = "",
        hidden: bool = False,
        readonly: bool = False,
        nullable: bool = True,
        sample_value: Optional[EntityPropertyType] = None,
        evaluator: Optional[str] = None,
        link_properties: Optional[LinkProperties] = None,
) -> Any:
    if contains_entity(value):
        raise TypeError(
            "MEF(..., value=…) only accepts primitives (str/int/etc) or lists thereof; "
            "you cannot pass MaltegoEntity instances in an entity definition."
        )
    return _MaltegoEntityProperty(
        display_name=display_name,
        name=name,
        matching_rule=matching_rule,
        value=value,
        description=description,
        hidden=hidden,
        readonly=readonly,
        nullable=nullable,
        sample_value=sample_value,
        evaluator=evaluator,
        link_properties=link_properties,
    )


def MaltegoEntityProperty(  # pylint: disable=invalid-name
        *,
        display_name: Optional[str] = None,
        name: Optional[str] = None,
        matching_rule: MatchingRule = MATCHING_RULE_STRICT,
        # this doubles as the default value when we're defining a full entity
        value: Optional[EntityPropertyType] = None,
        description: str = "",
        hidden: bool = False,
        readonly: bool = False,
        nullable: bool = True,
        sample_value: Optional[EntityPropertyType] = None,
        evaluator: Optional[str] = None
) -> Any:
    """A Maltego Entity property definition

    :param display_name: Display name of this property, defaults to None
    :type display_name: Optional[str], optional
    :param name: Property Id used to reference property in the client, defaults to None
    :type name: Optional[str], optional
    :param matching_rule: The Matching Rule defines whether this property is used for the Maltego
                          clients merging algorithm, defaults to MATCHING_RULE_STRICT
    :type matching_rule: MatchingRule, optional
    :param description: Description of the property, defaults to ""
    :type description: str, optional
    :param hidden: If True the property is not shown in the Maltego client, defaults to False
    :type hidden: bool, optional
    :param readonly: Defines if property can be modified by the user, defaults to False
    :type readonly: bool, optional
    :param nullable: Defines if property can have no value, defaults to True
    :type nullable: bool, optional
    :param sample_value: Sample value used by the Maltego Client, defaults to None
    :type sample_value: Optional[EntityPropertyType], optional
    :return: A Maltego Property object
    :rtype: Any
    """
    return MEF(
        display_name=display_name,
        name=name,
        matching_rule=matching_rule,
        value=value,
        description=description,
        hidden=hidden,
        readonly=readonly,
        nullable=nullable,
        sample_value=sample_value,
        evaluator=evaluator
    )
