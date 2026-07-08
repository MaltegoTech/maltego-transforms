# Copyright (c) Maltego Technologies GmbH.
import datetime
import logging
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from maltego._helper import create_maltego_id
from maltego.model.entity.type_handling import infer_v3_type_from_property_value
from maltego.model.observer import Observable
from maltego.model.types import (LinkColor, LinkPropertyType, LinkStyle, LinkThickness, MatchingRule,
                                 daterange,
                                 to_str_format,
                                 AttributeNames,
                                 LINK_ATTRIBUTE_NAMESPACE)
from maltego.protocol.v3.discovery.transform import serialize_daterange
from maltego.protocol.v3.execution.link import TransformRunLink
from maltego.protocol.v3.execution.property import Property

MaltegoLinkEnum = TypeVar('MaltegoLinkEnum', LinkColor, LinkStyle, LinkThickness)

log = logging.getLogger(__name__)


class MaltegoLinkProperty(Generic[LinkPropertyType]):

    def __init__(
            self,
            name: str,
            value: LinkPropertyType,
            display_name: Optional[str] = None,
            matching_rule: Optional[MatchingRule] = None
    ) -> None:
        self.name = name
        self.value: LinkPropertyType = value
        self.display_name = display_name
        self.matching_rule = matching_rule

    @classmethod
    def from_v3_run_link_property(cls, run_property: Property) -> "MaltegoLinkProperty[Any]":
        assert run_property.value is not None
        return cls(
            name=run_property.name,
            value=run_property.value,
            display_name=run_property.display_name
        )

    def to_v3_link_property(self) -> Property:
        assert self.name
        property_type = infer_v3_type_from_property_value(self.value)
        value: Optional[Any] = None
        if isinstance(self.value, daterange):
            value = serialize_daterange(self.value)
        elif isinstance(self.value, datetime.datetime):
            value = to_str_format(self.value)
        elif isinstance(self.value, datetime.date):
            value = to_str_format(self.value)
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


class MaltegoLink(Observable):
    """A Link as represented in a Maltego Graph
    """
    LABEL_PROPERTY_ID = 'maltego.link.label'
    COLOR_PROPERTY_ID = 'maltego.link.color'
    STYLE_PROPERTY_ID = 'maltego.link.style'
    THICKNESS_PROPERTY_ID = 'maltego.link.thickness'
    REVERSED_PROPERTY_ID = 'maltego.link.is_reversed'

    _enum_keys: List[str] = [STYLE_PROPERTY_ID, COLOR_PROPERTY_ID, THICKNESS_PROPERTY_ID]
    _default_properties: List[str] = [
        'source_id',
        'target_id',
        'maltego_link_id',
        '_properties',
        '_observers'
    ]
    _property_id_lookup = {
        'color': COLOR_PROPERTY_ID,
        'label': LABEL_PROPERTY_ID,
        'style': STYLE_PROPERTY_ID,
        'thickness': THICKNESS_PROPERTY_ID,
        'is_reversed': REVERSED_PROPERTY_ID
    }

    def __init__(
            self,
            source_id: str,
            target_id: str,
            is_reversed: bool = False,
            style: LinkStyle = LinkStyle.NORMAL,
            color: LinkColor = LinkColor.NONE,
            thickness: LinkThickness = LinkThickness.THICKNESS_DEFAULT,
            label: Optional[str] = None,
            maltego_link_id: Optional[str] = None,
            properties: Optional[Dict[str, MaltegoLinkProperty[Any]]] = None,
    ) -> None:
        super().__init__()
        self._properties: Dict[str, MaltegoLinkProperty[Any]] = properties or {}
        self.source_id = source_id
        self.target_id = target_id
        self.maltego_link_id = maltego_link_id or create_maltego_id()
        if is_reversed:
            self.set_property(self.REVERSED_PROPERTY_ID, is_reversed)
        if color is not LinkColor.NONE:
            self.set_property(self.COLOR_PROPERTY_ID, color)
        if style is not LinkStyle.NORMAL:
            self.set_property(self.STYLE_PROPERTY_ID, style)
        if thickness is not LinkThickness.THICKNESS_DEFAULT:
            self.set_property(self.THICKNESS_PROPERTY_ID, thickness)
        if label:
            self.set_property(self.LABEL_PROPERTY_ID, label)

    def __setattr__(self, key: str, value: Any) -> None:
        # Allow setting internal composite attributes directly
        if (
            key.startswith(LINK_ATTRIBUTE_NAMESPACE) and
            any(key == f"{LINK_ATTRIBUTE_NAMESPACE}.{attr}" for attr in vars(AttributeNames).values() if isinstance(attr, str))
        ):
            object.__setattr__(self, key, value)
            return

        if key in self._property_id_lookup:
            key = self._property_id_lookup[key]
        if key in self._enum_keys:
            self.__set_enum__(key, value)
        elif key in self._default_properties:
            super().__setattr__(key, value)
        else:
            self.set_property(key, value)

    def __getattr__(self, key: str) -> Optional[Any]:
        if key in self._property_id_lookup:
            key = self._property_id_lookup[key]
        if key in self._default_properties:
            return super().__getattribute__(key)
        return self._properties.get(key)

    def __set_enum_link_style(self, key: str, value: LinkStyle) -> None:
        if not isinstance(value, LinkStyle):
            raise ValueError(
                f"Link Thickness must be an object of type LinkStyle got {type(value)}"
            )
        self._properties[key] = MaltegoLinkProperty(
            name=key,
            value=value.value,
            display_name="Link Style"
        )

    def __set_enum_link_color(self, key: str, value: Union[str, LinkColor]) -> None:
        if isinstance(value, LinkColor):
            value_ = value.hex_color()
        elif value is None or (isinstance(value, str) and value.startswith("#") and len(value) == 7):
            value_ = value or "#FFFFFF"
        else:
            raise ValueError(
                "Color property needs to be either an hex string or a LinkColor object"
            )
        self._properties[key] = MaltegoLinkProperty(
            name=key,
            value=value_,
            display_name="Link Color"
        )

    def __set_enum_link_thickness(self, key: str, value: LinkThickness) -> None:
        if not isinstance(value, LinkThickness):
            raise ValueError("Link Thickness must be an object of type LinkThickness")
        self._properties[key] = MaltegoLinkProperty(
            name=key,
            value=value.value,
            display_name="Link Thickness"
        )

    def __set_enum__(self, key: str, value: Union[str, LinkStyle, LinkColor, LinkThickness]) -> None:
        if key == self.STYLE_PROPERTY_ID and isinstance(value, LinkStyle):
            self.__set_enum_link_style(key, value)
        elif key == self.COLOR_PROPERTY_ID and isinstance(value, (LinkColor, str)):
            self.__set_enum_link_color(key, value)
        elif key == self.THICKNESS_PROPERTY_ID and isinstance(value, LinkThickness):
            self.__set_enum_link_thickness(key, value)
        else:
            raise ValueError(f"Could not parse enum {key}: {value}")

    def get_properties(self) -> Dict[str, MaltegoLinkProperty[Any]]:
        """Returns all properties of the link

        :return: Dictionary of property names=>values
        :rtype: Dict[str, Any]
        """
        return self._properties

    def get_property(
            self,
            name: str,
            default_value: Optional[LinkPropertyType] = None
    ) -> Optional[LinkPropertyType]:
        """Returns a property of the link

        :param name: Name of the property to return
        :type name: str
        :param default_value: Default value. Returned in case the link property does not exist or None, defaults to None
        :type default_value: Optional[LinkPropertyType], optional
        :return: Returns the property value or the default value as fallback
        :rtype: Optional[LinkPropertyType]
        """
        link_property = self._properties.get(name)
        if default_value and link_property is None:
            return default_value
        return link_property.value if link_property is not None else None

    def set_property(
            self,
            name: str,
            value: Optional[Union[LinkPropertyType, LinkColor, LinkStyle, LinkThickness]],
            display_name: Optional[str] = None,
    ) -> None:
        """Set a property to a given value

        :param name: Name of the property
        :type name: str
        :param value: Value that the property should hold
        :type value: Optional[Union[LinkPropertyType, LinkColor, LinkStyle, LinkThickness]]
        :param display_name: Name used for display in the maltego client, defaults to name
        :type display_name: Optional[str], optional
        """
        if name in self._enum_keys:
            if isinstance(value, (LinkColor, LinkStyle, LinkThickness)):
                self.__set_enum__(name, value)
        elif name in self._properties:
            self._properties[name].value = value
        else:
            self._properties[name] = MaltegoLinkProperty(
                name=name,
                display_name=display_name,
                value=value
            )

    @property
    def is_reversed(self) -> bool:
        """Returns whether the link is reversed"""
        is_reversed = self.get_property(self.REVERSED_PROPERTY_ID)
        return bool(is_reversed)

    @is_reversed.setter
    def is_reversed(self, value: bool) -> None:
        self.is_reversed = value

    @property
    def style(self) -> int:
        """Returns the link style"""
        return self.get_property(self.STYLE_PROPERTY_ID) or LinkStyle.NORMAL.value

    @style.setter
    def style(self, value: LinkStyle) -> None:
        self.style = value.value

    @property
    def color(self) -> Optional[str]:
        """Returns the link color"""
        return self.get_property(self.COLOR_PROPERTY_ID)

    @color.setter
    def color(self, value: Union[str, LinkColor]) -> None:
        if isinstance(value, str):
            self.color = value
        else:
            self.color = value.value

    @property
    def thickness(self) -> Optional[int]:
        """Returns the link thickness"""
        thickness = self.get_property(self.THICKNESS_PROPERTY_ID)
        if isinstance(thickness, int):
            return thickness
        return None

    @thickness.setter
    def thickness(self, thickness: LinkThickness) -> None:
        self.thickness = thickness.value

    @property
    def label(self) -> Optional[str]:
        """Returns the link label"""
        return self.get_property(self.LABEL_PROPERTY_ID, None) or ""

    @label.setter
    def label(self, value: str) -> None:
        self.label = value

    @classmethod
    def from_v3_run_link(cls, link: TransformRunLink) -> "MaltegoLink":
        if link.source_id is None:
            raise ValueError(f"Got empty source for Link {link.id} in TransformRunRequest")
        if link.target_id is None:
            raise ValueError(f"Got empty target for Link {link.id} in TransformRunRequest")
        return cls(
            source_id=link.source_id,
            target_id=link.target_id,
            maltego_link_id=link.id,
            properties={
                link_property.name: MaltegoLinkProperty.from_v3_run_link_property(
                    link_property
                ) for link_property in link.properties or []
            }
        )

    def to_v3_link_properties(self) -> List[Property]:
        return [
            link_property.to_v3_link_property() for link_property in self.get_properties().values()
            if link_property.value is not None
        ]

    def to_v3_run_link(self) -> TransformRunLink:
        return TransformRunLink(
            id=self.maltego_link_id,
            source_id=self.source_id,
            target_id=self.target_id,
            properties=self.to_v3_link_properties()
        )

    def to_v3_run_link_from_id(self) -> TransformRunLink:
        return TransformRunLink(
            id=self.maltego_link_id
        )

    def to_v3_run_link_update(self, updated_property: Any) -> TransformRunLink:
        return TransformRunLink(
            id=self.maltego_link_id,
            properties=[
                updated_property.to_v3_link_property()
            ]
        )

    def _set_composite(self):
        """
        Mark this link as a composite by setting the appropriate hidden property.
        """
        from maltego.model.types import AttributeNames, LINK_ATTRIBUTE_NAMESPACE
        hidden_prop_name = f"{LINK_ATTRIBUTE_NAMESPACE}.{AttributeNames.composite_link}"
        # Note: links do not have a 'hidden' property, so we do not set it here
        self.set_property(hidden_prop_name, True)

    def _is_composite(self) -> bool:
        """
        Check if this link is marked as a composite.
        """
        from maltego.model.types import AttributeNames, LINK_ATTRIBUTE_NAMESPACE
        hidden_prop_name = f"{LINK_ATTRIBUTE_NAMESPACE}.{AttributeNames.composite_link}"
        return self.get_property(hidden_prop_name) is True

    def _get_internal_attributes(self) -> Dict[str, Any]:
        """
        Get all internal attribute properties under LINK_ATTRIBUTE_NAMESPACE.
        :return: Dict of attribute name (without namespace) to property value.
        """
        from maltego.model.types import LINK_ATTRIBUTE_NAMESPACE
        result = {}
        for prop in self._properties:
            if prop.startswith(f"{LINK_ATTRIBUTE_NAMESPACE}."):
                attr_name = prop[len(f"{LINK_ATTRIBUTE_NAMESPACE}."):]
                result[attr_name] = self.get_property(prop)
        return result
