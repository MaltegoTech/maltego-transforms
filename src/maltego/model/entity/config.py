# Copyright (c) Maltego Technologies GmbH.
import logging
from typing import Optional, List, Union, Tuple
from enum import Enum
from dataclasses import dataclass, field

from maltego.model.entity.constants import Overlay

log = logging.getLogger(__name__)


class MaltegoActionType(str, Enum):
    BROWSER = "maltego.spec.action.type.browser"


@dataclass
class MaltegoEntityAction:
    name: str
    display_name: str
    config: str
    action_type: MaltegoActionType


@dataclass
class MaltegoEntityRegexConverter:
    regex: str
    groups: List[str] = field(default_factory=list)


class MaltegoEntityConfig:

    def __init__(
            self,
            value_property: Optional[str] = None,
            value_key: Optional[str] = None,
            display_name: Optional[str] = None,
            description: Optional[str] = None,
            category: Optional[str] = None,
            allowed_root: bool = True,
            overlays: Optional[List[Overlay]] = None,
            overlay_image_property: Optional[str] = None,
            conversion_order: Optional[int] = None,
            icon_resource: Optional[Union[str, Tuple[str, str]]] = None,
            display_name_plural: Optional[str] = None,
            display_property: Optional[str] = None,
            display_key: Optional[str] = None,
            _visible: bool = True,
            converter: Optional[MaltegoEntityRegexConverter] = None,
            actions: Optional[List[MaltegoEntityAction]] = None
    ):
        self.value_property = str(value_property) if value_property is not None else None
        self.value_key = str(value_key) if value_key is not None else None
        self.display_name = str(display_name)
        self._description = str(description) if description is not None else None
        self._category = str(category) if category is not None else None
        self.allowed_root = bool(allowed_root)
        for overlay in overlays if overlays is not None else []:
            if not isinstance(overlay, Overlay):
                raise TypeError("Entity Config overlays need to be of type Overlay")

        self.overlays = overlays
        self.overlay_image_property = str(
            overlay_image_property
        ) if overlay_image_property is not None else None
        self._conversion_order = int(conversion_order) if conversion_order is not None else 2147483647
        if icon_resource:
            if isinstance(icon_resource, tuple):
                if len(icon_resource) != 2 or not (
                    isinstance(icon_resource[0], str) and isinstance(icon_resource[1], str)
                ):
                    raise TypeError("Icon tuple needs to be tuple[str, str]")
            elif not isinstance(icon_resource, str):
                raise TypeError("Icon needs to be string or tuple of strings")
        self.icon_resource = icon_resource
        self._display_property = str(
            display_property
        ) if display_property is not None else None
        self._display_key = str(display_key) if display_key is not None else None
        self._display_name_plural = str(
            display_name_plural
        ) if display_name_plural is not None else None
        self._visible = bool(_visible)
        self._base_entities: List[str] = []
        if converter and not isinstance(converter, MaltegoEntityRegexConverter):
            raise TypeError(
                f"Converter for entity {display_name} must be an object of type MaltegoEntityRegexConverter"
            )
        self.converter = converter
        self.actions = actions if actions is not None else []
        for action in self.actions:
            if not isinstance(action, MaltegoEntityAction):
                raise TypeError(f"EntityAction has invalid type {type(action)}. Need to be a MaltegoEntityAction")

    def copy(self) -> "MaltegoEntityConfig":
        config = MaltegoEntityConfig(
            value_property=self.value_property,
            display_name=self.display_name,
            description=self._description,
            category=self._category,
            allowed_root=self.allowed_root,
            overlays=self.overlays,
            overlay_image_property=self.overlay_image_property,
            conversion_order=self._conversion_order,
            icon_resource=self.icon_resource,
            display_name_plural=self._display_name_plural,
            display_property=self.display_property,
            _visible=self._visible,
            converter=self.converter,
            actions=self.actions
        )
        config.set_base_entities(self.get_base_entities().copy())
        return config

    def merge_with(self, other: "MaltegoEntityConfig") -> "MaltegoEntityConfig":
        merged = MaltegoEntityConfig(
            value_property=self.value_property or other.value_property,
            value_key=self.value_key or other.value_key,
            display_name=self.display_name or other.display_name,
            display_name_plural=self._display_name_plural or other._display_name_plural,  # pylint: disable=protected-access
            icon_resource=self.icon_resource or other.icon_resource,
            display_property=self._display_property or other._display_property,  # pylint: disable=protected-access
            display_key=self._display_key or other._display_key,
            description=self._description or other._description,  # pylint: disable=protected-access
            category=self._category or other._category,  # pylint: disable=protected-access
            allowed_root=self.allowed_root,
            overlays=self.overlays,
            overlay_image_property=self.overlay_image_property or other.overlay_image_property,
            converter=self.converter,
            actions=self.actions,
            conversion_order=self._conversion_order or other._conversion_order,  # pylint: disable=protected-access
            _visible=self._visible or other._visible  # pylint: disable=protected-access
        )
        return merged

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"{self.value_property=} "
            f"{self.display_property=} "
            f"{self.display_name=} "
            f"{self.display_name_plural=} "
            f"{self.category=} "
            f"{self.allowed_root=} "
            f"{self.icon_name=} "
            f")"
        )

    @property
    def category(self) -> str:
        return self._category or "Custom"

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def conversion_order(self) -> int:
        return self._conversion_order or 2147483647

    @property
    def description(self) -> str:
        return self._description or ""

    @property
    def display_name_plural(self) -> str:
        return self._display_name_plural or f"{self.display_name}s"

    @property
    def display_property(self) -> Optional[str]:
        return self._display_property or self.value_property

    @property
    def display_key(self) -> Optional[str]:
        return self._display_key or self.value_key

    @property
    def icon_name(self) -> str:
        if isinstance(self.icon_resource, tuple):
            return self.icon_resource[0]
        if isinstance(self.icon_resource, str):
            return self.icon_resource
        return "Unknown"

    @property
    def gen_icon_path(self) -> Optional[str]:
        if isinstance(self.icon_resource, tuple):
            return self.icon_resource[1]
        return None

    @property
    def large_icon_resource(self) -> str:
        return self.icon_name

    @property
    def small_icon_resource(self) -> str:
        return self.icon_name

    def set_base_entities(self, base_entities: List[str]) -> None:
        self._base_entities = base_entities

    def get_base_entities(self) -> List[str]:
        if self._base_entities is None:
            return []
        return self._base_entities


def merge_maltego_entity_config(
        child_config: Optional[MaltegoEntityConfig] = None,
        parent_config: Optional[MaltegoEntityConfig] = None
) -> Optional[MaltegoEntityConfig]:
    if parent_config is None and child_config is None:
        return None
    if child_config is None and parent_config is not None:
        return parent_config.copy()
    if parent_config is None and child_config is not None:
        return child_config

    assert child_config is not None
    assert parent_config is not None
    final_config = child_config.merge_with(parent_config)
    return final_config


RESERVED_ENTITY_ATTRIBUTES = [
    "Config",
    "TYPE_NAME",
    "entity_properties",
    "__module__",
    "__qualname__",
    "__annotations__"
]
