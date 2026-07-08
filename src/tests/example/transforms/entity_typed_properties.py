# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=unused-argument
from typing import List

from tests.example.transforms.entities.composite_entities import (
    AliasOnlyComposite,
    CompositeInheritingAtomic,
    ExtendedAffiliationComposite,
    HasAffiliationComposite,
    MultiInheritComposite,
)
from tests.conftest import UniqueIdentifier, AffiliationComposite
from maltego.model.context import MaltegoContext
from maltego.model.entity import MaltegoEntity
from maltego.model.graph import MaltegoGraph
from maltego.server import register_transform
from tests.conftest import Alias, Image, Person, Phrase

__all__ = [
    "composed_affiliation_transform",
    "composed_affiliation_enrich_transform",
    "oversize_composed_affiliation_transform",
    "list_composed_affiliation_transform",
    "delete_composed_affiliation_transform",
    "add_and_replace_prop_composed_affiliation_transform",
    "duplicate_child_composed_affiliation_transform",
    "duplicate_child_delete_composed_affiliation_transform",
    "shared_children_composed_affiliation_transform",
    "composed_affiliation_dynamic_prop_transform",
    "wrong_entity_type_for_composite_prop_transform",
    "test_composite_inheriting_atomic_transform",
    "test_extended_affiliation_composite_transform",
    "test_has_affiliation_composite_transform",
    "test_multi_inherit_composite_transform",
    "test_combinations_transform",
    "replace_alias_list_transform",
    "person_with_dynamic_alias_transform"
]

ENTITY_TYPED_PROPERTIES = "Entity-typed Properties Transforms [Maltego]"


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def composed_affiliation_enrich_transform(
        input_entity: AffiliationComposite,
        context: MaltegoContext,
) -> MaltegoEntity:
    """
    This transform enriches a composed entity with a profile image
    :return enriched composed entity
    """
    # Add a maltego.Image property to the input entity
    graph_ents = context.graph.entities
    img_ent = Image("Profile Picture")
    img_ent.url = "https://media.istockphoto.com/id/896916940/photo/cat-cowboy-on-a-horse.jpg?s=612x612&w=0&k=20&c=vWP2EmHTDwgLnTXYyoBEmr3AD9R3dQcmiUbK-HNIbak="
    input_entity.profile_image = img_ent
    # Yield the updated entity
    yield input_entity


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def oversize_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: a composite graph that has more than 50 events, so parent would be in the second page
    for i in range(0, 40):
        # Create nested entities
        person_entity = Person(f"John Doe [{i}]")
        uid_entity = UniqueIdentifier(f"1477245957 [{i}]")
        # Create composed entity
        affiliation_composite = AffiliationComposite(uid_entity)

        # use attribute assignment or setter function, similar to existing property, to set nested entities
        affiliation_composite.person = person_entity

        # Add the composed entity to the graph
        context.graph.add_child(input_entity, affiliation_composite)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def list_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> List[AffiliationComposite]:
    # test idea: return a list of entities instead of using graph observation
    results = []
    for i in range(0, 3):
        # Create nested entities
        person_entity = Person(f"John Doe [{i}]")
        alias_entities: List[Alias] = [Alias(f"johndoe42 [{i}]"), Alias(f"john.d [{i}]")]
        uid_entity = UniqueIdentifier(f"1477245957 [{i}]")
        # Create composed entity
        affiliation_composite = AffiliationComposite(uid_entity)

        # use attribute assignment or setter function, similar to existing property, to set nested entities
        affiliation_composite.person = person_entity
        affiliation_composite.set_property("alias", alias_entities)

        results.append(affiliation_composite)
    return results


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def delete_composed_affiliation_transform(
        graph: MaltegoGraph,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: delete input and return
    assert isinstance(context.graph.entities[0], AffiliationComposite)
    context.graph.delete_entity(context.graph.entities[0])
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def add_and_replace_prop_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)

    # Updated entity should be in the result graph
    # TODO: this is not curently supported, will add and update event for .person with reference to
    # TODO: Jane Doe but wont add the entity.
    affiliation_composite.person = Person("Jane Doe")

    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def duplicate_child_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: add entity to graph and also add child in graph with add_child: should both be in there?
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)
    context.graph.add_child(affiliation_composite, person_entity)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def duplicate_child_delete_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: add entity to graph and also add child but then delete child
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)
    context.graph.add_child(affiliation_composite, person_entity)
    context.graph.delete_entity(person_entity)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def shared_children_composed_affiliation_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: add same children entities to multiple composite parents. child events should not be duplicated but links should be added
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    for i in range(0, 2):
        # Create composed entity
        affiliation_composite = AffiliationComposite(uid_entity)

        # use attribute assignment or setter function, similar to existing property, to set nested entities
        affiliation_composite.person = person_entity
        affiliation_composite.set_property("alias", alias_entities)

        # Add the composed entity to the graph
        context.graph.add_child(input_entity, affiliation_composite)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def composed_affiliation_dynamic_prop_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # test idea: set dynamic properties (both primitive and entity-typed)
    # Create nested entities
    person_entity = Person("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)
    affiliation_composite.set_property(name="dynamic_alias_str", value="StringAlias")
    affiliation_composite.set_property(name="dynamic_alias_ent", value=Alias("EntityAlias"))

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def composed_affiliation_dynamic_prop_transform_mixed_typing(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # Create nested entities
    person_entity = Alias("John Doe")
    alias_entities: List[Alias] = [Alias("johndoe42"), Alias("john.d")]
    uid_entity = UniqueIdentifier("1477245957")
    # Create composed entity
    affiliation_composite = AffiliationComposite(uid_entity)

    # use attribute assignment or setter function, similar to existing property, to set nested entities
    affiliation_composite.person = person_entity
    affiliation_composite.set_property("alias", alias_entities)

    # Add the composed entity to the graph
    context.graph.add_child(input_entity, affiliation_composite)
    # Return the graph
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def wrong_entity_type_for_composite_prop_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> AliasOnlyComposite:
    """
    Test: Set a Person entity where an Alias is expected (composite property).
    Should raise an error or behave unexpectedly.
    """
    composite = AliasOnlyComposite(Alias("should be alias"))
    # Intentionally set wrong type: expects Alias, gets Person
    composite.set_property("alias", Person("Wrong Type"))
    return composite


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def test_composite_inheriting_atomic_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> CompositeInheritingAtomic:
    # Composite entity inheriting AtomicEntity, adds ENTITY-typed property
    ent = CompositeInheritingAtomic("composite atomic")
    ent.atomic_number = 8
    ent.related_person = Person("Related Person")
    return ent


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def test_extended_affiliation_composite_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> ExtendedAffiliationComposite:
    # Composite entity inheriting AffiliationComposite, adds its own fields
    uid = UniqueIdentifier("999999")
    ext = ExtendedAffiliationComposite(uid)
    ext.extra_field = "extra info"
    ext.extra_person = Person("Extra Person")
    ext.person = Person("Owner Person")
    ext.alias = [Alias("alias1"), Alias("alias2")]
    ext.display_information = []
    return ext


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def test_has_affiliation_composite_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> HasAffiliationComposite:
    # Entity with AffiliationComposite as a property
    uid = UniqueIdentifier("888888")
    aff = AffiliationComposite(uid)
    aff.person = Person("Aff Person")
    aff.alias = [Alias("affalias")]
    ent = HasAffiliationComposite(aff)
    return ent


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def test_multi_inherit_composite_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MultiInheritComposite:
    # Entity with multiple inheritance, has its own properties
    uid = UniqueIdentifier("777777")
    aff = AffiliationComposite(uid)
    aff.person = Person("Multi Person")
    aff.alias = [Alias("multialias")]
    ent = MultiInheritComposite("multi value")
    ent.extra_number = 111
    ent.affiliation = aff
    ent.multi_value = "multi test"
    ent.extra_number = 456
    ent.atomic_value = "atomic in multi"
    return ent


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def test_combinations_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> List[MaltegoEntity]:
    # Return a list of all the above for easy inspection
    results = []
    results.append(await test_composite_inheriting_atomic_transform(input_entity, context))
    results.append(await test_extended_affiliation_composite_transform(input_entity, context))
    results.append(await test_has_affiliation_composite_transform(input_entity, context))
    results.append(await test_multi_inherit_composite_transform(input_entity, context))
    return results


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    display_name="Replace Alias List",
    description="Adds a composite, then replaces its alias list and returns the graph",
    composite_entities=True,
)
async def replace_alias_list_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> MaltegoGraph:
    # create the composite and give it two initial aliases
    comp = AffiliationComposite(UniqueIdentifier("replace‑test‑uid"))
    comp.set_property("alias", [Alias("first1"), Alias("first2")])

    # add it to the graph (this will emit ADDs and links for the two first aliases)
    context.graph.add_child(input_entity, comp)

    # replace the alias list with two brand‑new ones
    comp.set_property("alias", [Alias("second1"), Alias("second2")])
    # This should *remove* the old composite‑links and emit new ADD+UPDATE+LINK events
    # TODO: how to remove the initial Alias entities?
    return context.graph


@register_transform(
    transform_set=ENTITY_TYPED_PROPERTIES,
    composite_entities=True,
)
async def person_with_dynamic_alias_transform(
        input_entity: Phrase,
        context: MaltegoContext,
) -> Person:
    # Create a Person entity and set a dynamic property 'alias'
    person_entity = Person("Dynamic Alias Person")
    person_entity.set_property("alias", Alias("dynamic_alias_123"))
    return person_entity

