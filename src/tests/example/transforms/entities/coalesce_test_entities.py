# Copyright (c) Maltego Technologies GmbH.
"""
Test entities for EntityConfigOverrides and coalesce capability negotiation.

These are ATOMIC entities (no entity-typed properties) with $coalesce() expressions.
For composite coalesce entities, see composite_entities.py.
"""
from maltego.model.entity import MaltegoEntity, MaltegoEntityConfig, MEF
from maltego.server import register_entity

__all__ = [
    "AtomicCoalesceTestEntity",
    "CoalescingDisplayPropertyEntity",
]


@register_entity
class AtomicCoalesceTestEntity(MaltegoEntity):
    """
    Atomic (non-composite) test entity with $coalesce() in MEF value + evaluator.

    Used to test desktop filtering for coalesce expressions.
    Atomic means all properties are primitive types (str, int, etc.), not entity types.
    """
    TYPE_NAME = "maltego.AtomicCoalesceTestEntity"
    Config = MaltegoEntityConfig(
        value_property="display_property",
        display_name="Atomic Coalesce Test",
        description="Atomic entity with coalesce in MEF value (not supported by desktop)",
        icon_resource="Phrase",
        allowed_root=True,
    )
    display_property: str = MEF(
        name="display_property",
        display_name="Display Property",
        sample_value="Coalesced Value",
        value='$coalesce($property(name), $property(alias), "Unknown")',
        evaluator="maltego.replace",
    )
    name: str = MEF(
        name="name",
        display_name="Name",
        sample_value="Test Name"
    )
    alias: str = MEF(
        name="alias",
        display_name="Alias",
        sample_value="Test Alias"
    )


@register_entity
class CoalescingDisplayPropertyEntity(MaltegoEntity):
    """
    Coalesce entity with override configured - tests that entity config overrides
    can remove $coalesce() from field default_value, allowing it to pass capability filtering.
    """
    TYPE_NAME = "maltego.CoalescingDisplayPropertyEntity"

    Config = MaltegoEntityConfig(
        value_property="display_property",
        display_name="Coalescing Display Property Entity",
        description="Coalesce entity with override - tests override removes coalesce for desktop",
        icon_resource="Phrase",
        allowed_root=True,
    )

    display_property: str = MEF(
        name="display_property",
        display_name="Display Property",
        sample_value="Coalesced Value",
        value='$coalesce($property(name), $property(alias), $property(identifier), "Default Value")',
        evaluator="maltego.replace",
    )

    name: str = MEF(
        name="name",
        display_name="Name",
        sample_value="Test Name"
    )

    alias: str = MEF(
        name="alias",
        display_name="Alias",
        sample_value="Test Alias"
    )

    identifier: str = MEF(
        name="identifier",
        display_name="Identifier",
        sample_value="Test Identifier"
    )

