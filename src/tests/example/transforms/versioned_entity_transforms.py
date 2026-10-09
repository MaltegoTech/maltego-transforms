# Copyright (c) Maltego Technologies GmbH.
from maltego.model.entity import MaltegoEntityConfig, MaltegoEntityProperty, MaltegoEntity
from maltego.server import register_transform


class VersionedEntity(MaltegoEntity):
    TYPE_NAME = "maltego.VersionedEntity"
    TYPE_VERSION = "1.2.3"

    Config = MaltegoEntityConfig(
        value_property="value"
    )

    value: str = MaltegoEntityProperty(
        display_name="Value",
        name="value",
        description="Value Test Property",
        sample_value="test"
    )


@register_transform(
    display_name="Test Versioned", name="TestVersioned", description="test versioned", transform_set="Versioned Entity Transforms"
)
async def mock_transform_versioned(input_entity: VersionedEntity, settings) -> VersionedEntity:
    return VersionedEntity("Test")
