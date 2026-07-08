# Copyright (c) Maltego Technologies GmbH.
from typing import Any
import pytest
from tests.conftest import Phrase
from maltego.server import MaltegoGraph, MaltegoLink
from tests.conftest import Phrase

pytestmark = pytest.mark.unit


def test_value_graph_create():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    link = MaltegoLink(
        source_id=entity1.maltego_entity_id,
        target_id=entity2.maltego_entity_id
    )
    graph = MaltegoGraph([entity1, entity2], [link])
    assert len(graph.entities) == 2
    assert len(graph.links) == 1


def test_invalid_graph_create():
    orphaned_link = MaltegoLink("1", "2")
    with pytest.raises(ValueError):
        MaltegoGraph([], [orphaned_link])


def test_add_entity():
    entity1 = Phrase("Phrase one")
    graph = MaltegoGraph()
    graph.add_entity(entity1)
    assert len(graph.entities) == 1
    assert graph.entities[0] == entity1


def test_add_child_and_add_link():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase three")
    graph = MaltegoGraph([entity1], [])
    graph.add_child(entity1, entity2)
    assert len(graph.entities) == 2
    assert graph.entities[0] == entity1
    assert graph.entities[1] == entity2
    assert len(graph.links) == 1
    link = graph.links[0]
    assert link.source_id == entity1.maltego_entity_id
    assert link.target_id == entity2.maltego_entity_id


def test_get_entities_of_type():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    entity3 = Phrase("Phrase three")
    graph = MaltegoGraph([entity1, entity2, entity3], [])
    entities_of_type = graph.get_entities_of_type("maltego.Phrase")
    assert len(entities_of_type) == 3
    assert entities_of_type[0] == entity1


def test_get_links_from():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    entity3 = Phrase("Phrase three")
    graph = MaltegoGraph()
    graph.add_link(entity1, entity2)
    graph.add_link(entity1, entity3)
    links_from = graph.get_links_from(entity1)
    assert len(links_from) == 2


def test_get_link_from_and_get_links_to():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    graph = MaltegoGraph()
    graph.add_link(entity1, entity2)
    link_from = graph.get_link_from(entity1)
    links_from = graph.get_links_from(entity1)
    link_to = graph.get_link_to(entity2)
    links_to = graph.get_links_to(entity2)
    assert link_from == links_from[0]
    assert link_to == links_to[0]


def test_get_link_between():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    graph = MaltegoGraph()
    graph.add_link(entity1, entity2)
    link_between = graph.get_link_between(entity1, entity2)
    assert link_between is not None
    assert link_between.source_id == entity1.maltego_entity_id
    assert link_between.target_id == entity2.maltego_entity_id


def test_get_source_and_get_target():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    graph = MaltegoGraph()
    link = graph.add_link(entity1, entity2)
    source = graph.get_source(link)
    target = graph.get_target(link)
    assert source == entity1
    assert target == entity2


def test_get_child_entities():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    graph = MaltegoGraph()
    graph.add_entity(entity1)
    graph.add_child(entity1, entity2)
    child_entities = graph.get_child_entities(entity1)
    assert len(child_entities) == 1
    assert child_entities[0] == entity2


def test_get_links_from_and_to():
    entity1 = Phrase("Phrase one")
    entity2 = Phrase("Phrase two")
    graph = MaltegoGraph()
    graph.add_link(entity1, entity2)
    graph.add_link(entity1, entity2)
    links_from_and_to = graph.get_links_from_and_to(entity1, entity2)
    assert len(links_from_and_to) == 2


def test_graph_interface(example_graph: MaltegoGraph[Any]):
    assert len(example_graph.entities) == 22
    assert len(example_graph.links) == 92
    assert len(example_graph.get_entities_of_type("maltego.Phrase")) == 14
    first_entity = example_graph.entities[0]
    last_entity = example_graph.entities[-1]
    new_entity = Phrase("foo")
    new_entity_ = Phrase("foo")
    child1 = example_graph.add_child(first_entity, new_entity)
    grandchild = example_graph.add_child(new_entity, new_entity_)
    assert child1 is new_entity
    assert grandchild is new_entity_
    assert example_graph.get_child_entities(child1)[0] is grandchild

    link1 = example_graph.add_link(grandchild, last_entity)
    assert len(example_graph.entities) == 24
    assert len(example_graph.links) == 95
    assert link1 is example_graph.get_links_from(grandchild)[0]
    assert link1 is example_graph.get_link_between(grandchild, last_entity)

    assert example_graph.get_child_entities(child1)[0] == grandchild

    example_graph.add_entities([Phrase(i) for i in range(0, 10)])
    assert len(example_graph.entities) == 34

    example_graph.delete_entity(first_entity)
    assert len(example_graph.entities) == 33
    assert len(example_graph.links) == 95

    example_graph.add_entity(first_entity)
    assert len(example_graph.entities) == 34
    assert len(example_graph.links) == 95

    example_graph.delete_link(link1)
    assert len(example_graph.entities) == 34
    assert len(example_graph.links) == 94

    example_graph.delete_entity(new_entity)
    assert len(example_graph.entities) == 33
    assert len(example_graph.links) == 94
    child1 = example_graph.add_child(first_entity, new_entity)

    example_graph.delete_entity(child1)
    assert len(example_graph.entities) == 33
    assert len(example_graph.links) == 95

    example_graph.delete_entity(child1)
    assert len(example_graph.entities) == 33
    assert len(example_graph.links) == 95


def test_get_entity_by_id(example_graph: MaltegoGraph[Any]):
    optional_entity = example_graph.get_entity_by_id("not-present")
    assert optional_entity is None

    present_entity = example_graph.add_entity(Phrase("present"))
    assert example_graph.get_entity_by_id(present_entity.maltego_entity_id) is not None


def test_delete_entity_by_id(example_graph: MaltegoGraph[Any]):
    optional_entity = example_graph.delete_entity_by_id("not-present")
    assert optional_entity is None

    present_entity = example_graph.add_entity(Phrase("present"))
    assert example_graph.delete_entity_by_id(present_entity.maltego_entity_id) is not None
