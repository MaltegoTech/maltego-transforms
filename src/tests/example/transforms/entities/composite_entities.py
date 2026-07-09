# Copyright (c) Maltego Technologies GmbH.

from maltego.model.entity import MaltegoEntity, MaltegoEntityConfig, MEF
from maltego.server import register_entity
from tests.conftest import Person, Alias, AffiliationComposite, UniqueIdentifier
from maltego.model.entity import MaltegoEntityProperty

__all__ = [
    "AliasOnlyComposite",
    "CompositeCoalesceTestEntity",
]

# Register the entities from conftest with the example server
register_entity(UniqueIdentifier)
register_entity(AffiliationComposite)


@register_entity
class AliasOnlyComposite(MaltegoEntity):
    Config = MaltegoEntityConfig(
        value_property="alias",
        display_name="AliasOnlyComposite",
        icon_resource="Alias"
    )
    alias: Alias = MEF(
        name="alias",
        display_name="Alias",
        description="Alias entity only",
        matching_rule="loose"
    )


@register_entity
class AtomicEntity(MaltegoEntity):
    TYPE_NAME = "maltego.AtomicEntity"
    Config = MaltegoEntityConfig(
        value_property="atomic_value",
        display_name="AtomicEntity",
        icon_resource="Phrase"
    )
    atomic_value: str = MaltegoEntityProperty(
        sample_value="atomic"
    )
    atomic_number: int = MaltegoEntityProperty(
        sample_value=42
    )


@register_entity
class CompositeInheritingAtomic(AtomicEntity):
    TYPE_NAME = "maltego.CompositeInheritingAtomic"
    Config = MaltegoEntityConfig(
        display_name="CompositeInheritingAtomic"
    )
    related_person: Person = MEF(
        name="related_person",
        display_name="Related Person",
        description="A related person entity",
        matching_rule="loose",
    )


@register_entity
class ExtendedAffiliationComposite(AffiliationComposite):
    TYPE_NAME = "maltego.ExtendedAffiliationComposite"
    Config = MaltegoEntityConfig(
        value_property="uid",
        display_name="ExtendedAffiliationComposite",
        icon_resource="Affiliation"
    )
    extra_field: str = MaltegoEntityProperty(
        sample_value="extra"
    )
    extra_person: Person = MEF(
        name="extra_person",
        display_name="Extra Person",
        description="An additional person entity",
        matching_rule="loose",
    )


@register_entity
class HasAffiliationComposite(MaltegoEntity):
    TYPE_NAME = "maltego.HasAffiliationComposite"
    Config = MaltegoEntityConfig(
        value_property="affiliation",
        display_name="HasAffiliationComposite",
        icon_resource="Affiliation"
    )
    affiliation: AffiliationComposite = MEF(
        name="affiliation",
        display_name="Affiliation",
        description="An AffiliationComposite entity as a property",
        matching_rule="loose",
    )


@register_entity
class MultiInheritComposite(HasAffiliationComposite, AtomicEntity):
    TYPE_NAME = "maltego.MultiInheritComposite"
    Config = MaltegoEntityConfig(
        value_property="multi_value",
        display_name="MultiInheritComposite",
        icon_resource="Phrase"
    )
    multi_value: str = MaltegoEntityProperty(
        sample_value="multi"
    )
    extra_number: int = MaltegoEntityProperty(
        sample_value=99
    )


@register_entity
class CompositeCoalesceTestEntity(MaltegoEntity):
    """
    Composite test entity with $coalesce() in MEF value + evaluator.

    Used to test desktop filtering for coalesce expressions on composite entities.
    Composite means it has entity-typed properties (Person, Alias, UniqueIdentifier).
    """
    TYPE_NAME = "maltego.CompositeCoalesceTestEntity"
    Config = MaltegoEntityConfig(
        value_property="display_property",
        display_name="Composite Coalesce Test",
        description="Composite entity with coalesce in MEF value (not supported by desktop)",
        icon_resource="Affiliation",
        allowed_root=True,
    )
    display_property: str = MEF(
        name="display_property",
        display_name="Display Property",
        sample_value="Coalesced Value",
        value='$coalesce($property(person), $property(alias), $property(identifier), "Unknown Profile")',
        evaluator="maltego.replace",
    )
    person: Person = MEF(
        name="person",
        display_name="Person",
        description="The person associated with this profile",
        matching_rule="loose",
    )
    alias: Alias = MEF(
        name="alias",
        display_name="Alias",
        description="An alias for this profile",
        matching_rule="loose",
    )
    identifier: UniqueIdentifier = MEF(
        name="identifier",
        display_name="Identifier",
        description="A unique identifier for this profile",
        matching_rule="loose",
    )
