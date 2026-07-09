# Copyright (c) Maltego Technologies GmbH.
import io
from typing import Dict, Set, Type, TypedDict
import logging
from PIL import Image
from maltego.model.machine import MaltegoMachine

from maltego.model.oauth import OAuthAuthenticator
from maltego.model.entity import MaltegoEntity
from maltego.model.transform_set import TransformSet

log = logging.getLogger(__name__)
ENTITY_ICON_SIZE_MIN = 96
ENTITY_ICON_SIZES = (16, 24, 32, 48, 96)


def open_icon(path: str) -> Image.Image:
    image = Image.open(path)
    x = image.size[0]
    y = image.size[1]
    if x != y:
        log.warning(
            f"Entity Icon '{path=}' is not quadratic ({x=}, {y=})"
        )
    if (x % 2) != 0:
        log.warning(
            f"Entity Icon '{path=}' x-axis is not a divisible by two ({x=}, {y=})"
        )
    if x < ENTITY_ICON_SIZE_MIN:
        log.warning(
            f"Entity Icon {path=} x-axis is smaller then {ENTITY_ICON_SIZE_MIN=} ({x=}, {y=})"
        )
    return image


class IconDef(TypedDict):
    data: Dict[int, bytes]
    category: str


class MaltegoPairedConfiguration:
    def __init__(self) -> None:
        self.entities: Dict[str, Type["MaltegoEntity"]] = {}
        self.entity_categories: Set[str] = set()
        self.transform_sets: Dict[str, Type[TransformSet]] = {}
        self.machines: Dict[str, Type[MaltegoMachine]] = {}
        self.authenticators: Dict[str, OAuthAuthenticator] = {}
        self.icons: Dict[str, IconDef] = {}

    def add_entity(self, entity: Type[MaltegoEntity]) -> None:
        if entity.TYPE_NAME is None:
            raise RuntimeError(
                f"Entity {entity.__name__} has no TYPE_NAME parameter. Cannot add to discovery"
            )
        if entity.TYPE_NAME in self.entities:
            raise RuntimeError(
                f"Entity {entity.__name__} with TYPE_NAME {entity.TYPE_NAME} "
                "already exists in paired configuration for entity class"
            )
        self.entities[entity.TYPE_NAME] = entity
        self.add_entity_icons(entity)

    def add_transform_to_set(
            self,
            transform_set: str,
            transform_id: str,
    ) -> None:
        if transform_set not in self.transform_sets:
            self.transform_sets[transform_set] = type(transform_set, (TransformSet,), {
                "name": transform_set,
                "transforms": [],
                "description": None
            })
        self.transform_sets[transform_set].transforms.append(transform_id)

    def add_icon_from_file(self, icon_name: str, icon_filename: str, category: str) -> None:
        sizes = ENTITY_ICON_SIZES
        log.info(f"Creating icon '{icon_name}' from {icon_filename}")
        image = open_icon(icon_filename)
        self.icons[icon_name] = {
            "data": {},
            "category": category
        }
        for size in sizes:
            _image = image.resize((size, size), Image.Resampling.BICUBIC)
            if _image.size[0] != size or _image.size[1] != size:
                log.error(
                    f"Error when generating thumbnail for '{icon_filename}'. "
                    f"Request size is '{size}' generated size is '{image.size}'"
                )
                raise RuntimeError(
                    f"Error when generating thumbnail for '{icon_filename}'. "
                    f"Request size is '{size}' generated size is '{image.size}'"
                )
            file_object = io.BytesIO()
            _image.save(file_object, "PNG")
            self.icons[icon_name]["data"][size] = file_object.getvalue()
        image.close()

    def add_entity_icons(self, entity_type: Type[MaltegoEntity]) -> None:
        if entity_type.Config is None:
            log.error(f"Entity {entity_type} is missing Config")
            return
        icon_filename = entity_type.Config.gen_icon_path
        icon_name = entity_type.Config.icon_name

        if icon_filename is None:
            return

        assert icon_name is not None
        icon_filename = entity_type.Config.gen_icon_path
        if icon_name is not None and icon_filename is not None:
            self.add_icon_from_file(icon_name, icon_filename, entity_type.Config.category)
