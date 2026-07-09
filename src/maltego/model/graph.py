# Copyright (c) Maltego Technologies GmbH.
from collections import defaultdict
from typing import List, Optional, Dict, Any, Set, Tuple, TypeVar, Generic

from maltego.model.entity import MaltegoEntity, _MaltegoEntityProperty
from maltego.model.link import MaltegoLink
from maltego.model.observer import Observable
from maltego.model.types import LinkStyle, LinkColor, LinkThickness


T = TypeVar('T')


def check_entity_type(entity: MaltegoEntity) -> bool:
    if not isinstance(entity, MaltegoEntity):
        raise TypeError("The entity has to be of type MaltegoEntity")
    return True


class MaltegoGraph(Generic[T], Observable):
    """This class represents a Maltego Graph as provided to the transform function"""

    def __init__(
            self,
            entities: Optional[List[MaltegoEntity]] = None,
            links: Optional[List[MaltegoLink]] = None
    ):
        super().__init__()
        self.__entities: dict[str, MaltegoEntity] = {}
        for entity in entities or []:
            self.__entities[entity.maltego_entity_id] = entity

        self.__composite_entity_ids: set[str] = set()
        self.__comp_parent_to_children: dict[str, set[str]] = defaultdict(set)
        self.__comp_child_to_parents: dict[str, set[str]] = defaultdict(set)

        self.__links: dict[str, MaltegoLink] = {}
        for link in links or []:
            if link.source_id not in self.__entities:
                raise ValueError(
                    f'The source entity for link {link.maltego_link_id} is not present on the Graph'
                )
            if link.target_id not in self.__entities:
                raise ValueError(
                    f'The target entity for link {link.maltego_link_id} is not present on the Graph'
                )
            self.__links[link.maltego_link_id] = link


    def __add_entity_property_links(self, entity: MaltegoEntity, ent_ids: List[Tuple[str, str]]):
        """
        Add links between entity and list of ids,
        these ids represent the already added entity-typed properties
        :param entity:
        :param ent_ids: list of tuple: property name, entity id
        :return:
        """
        existing_composite_targets = {l.target_id for l in self.get_links_from(entity) if l._is_composite()}

        for prop_name, ent_id in ent_ids:
            # skip if already a composite link between entities
            if ent_id in existing_composite_targets:
                continue

            if prop_name in entity.get_property_defs():
                entity_prop: _MaltegoEntityProperty = entity.get_property_defs()[prop_name]
            else:
                entity_prop = entity.get_properties()[prop_name]

            if not entity_prop.link_properties:
                from maltego.model.entity.property import LinkProperties
                entity_prop.link_properties = LinkProperties()

            target_entity = self.get_entity_by_id(ent_id)
            if not target_entity:
                raise ValueError(f"Entity with ID {ent_id} not found when creating link.")

            link = self.add_link(
                source=entity,
                target=target_entity,
                is_reversed=entity_prop.link_properties.is_reversed,
                style=entity_prop.link_properties.style,
                color=entity_prop.link_properties.color,
                thickness=entity_prop.link_properties.thickness,
                properties=entity_prop.link_properties.properties,
                label=entity_prop.link_properties.label,
            )
            # events created from this link should be tagged as composite,
            # since not explicit link event but represent reference for entity-typed property
            link._set_composite()
            existing_composite_targets.add(ent_id)

    def __add_entity_from_properties(self, entity: MaltegoEntity, visited: set[str]) -> List[Tuple[str, str]]:
        """
        Check properties of an entity,
        if entity-typed property, add to the graph and collect property name and entity for links
        :param entity: MaltegoEntity
        :param visited: whether this entity was already added
        :return:
        """
        if entity.maltego_entity_id in visited:
            return []
        visited.add(entity.maltego_entity_id)

        ent_ids: List[Tuple[str, str]] = []
        parent_id = entity.maltego_entity_id

        for prop_name, prop in entity.get_properties().items():
            val = prop.value
            if isinstance(val, MaltegoEntity):
                child_id = val.maltego_entity_id
                ent_ids.append((prop_name, child_id))
                self.__composite_entity_ids.add(child_id)
                self.__comp_parent_to_children[parent_id].add(child_id)
                self.__comp_child_to_parents[child_id].add(parent_id)
                if child_id not in self.__entities:
                    val._set_composite_child()
                    self.__add_entity(val, visited)

            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, MaltegoEntity):
                        child_id = item.maltego_entity_id
                        ent_ids.append((prop_name, child_id))
                        self.__composite_entity_ids.add(child_id)
                        self.__comp_parent_to_children[parent_id].add(child_id)
                        self.__comp_child_to_parents[child_id].add(parent_id)
                        if child_id not in self.__entities:
                            item._set_composite_child()
                            self.__add_entity(item, visited)

        return ent_ids

    def __add_entity(self, entity: MaltegoEntity, visited: Optional[Set] = None) -> MaltegoEntity:
        """
        Add entity to the graph
        :param entity: MaltegoEntity
        :param visited: a list of visited entities
        :return:
        """
        _visited: Set[str] = visited or set()

        # Register and add parent entity first
        for observer in self.get_observers():
            entity.register(observer)
        self.notify_add(entity)
        if entity.maltego_entity_id not in self.__entities:
            self.__entities[entity.maltego_entity_id] = entity

        # process properties for child entities (recurse, will early-return if already visited)
        ent_ids = self.__add_entity_from_properties(entity, _visited)

        # add property links
        if ent_ids:
            self.__add_entity_property_links(entity, ent_ids)
        return self.__entities[entity.maltego_entity_id]

    def __delete_entity(self, entity: MaltegoEntity) -> Optional[MaltegoEntity]:
        ent_id = entity.maltego_entity_id

        # If this entity was a composite parent, detach its children
        for child_id in self.__comp_parent_to_children.pop(ent_id, set()):
            parents = self.__comp_child_to_parents.get(child_id)
            if parents:
                parents.discard(ent_id)
                if not parents:
                    # child no longer referenced by any parent
                    self.__comp_child_to_parents.pop(child_id, None)
                    self.__composite_entity_ids.discard(child_id)

        # If this entity was a composite child, detach it from its parents
        for parent_id in self.__comp_child_to_parents.pop(ent_id, set()):
            kids = self.__comp_parent_to_children.get(parent_id)
            if kids:
                kids.discard(ent_id)
                if not kids:
                    self.__comp_parent_to_children.pop(parent_id, None)

        # Remove this entity from composite set if present
        self.__composite_entity_ids.discard(ent_id)

        self.notify_delete(entity)
        for observer in self.get_observers():
            entity.unregister(observer)
        return self.__entities.pop(ent_id, None)

    def __add_link(self, link: MaltegoLink) -> MaltegoLink:
        for observer in self.get_observers():
            link.register(observer)
        self.notify_add(link)
        self.__links[link.maltego_link_id] = link
        return self.__links[link.maltego_link_id]

    def __delete_link(self, link: MaltegoLink) -> Optional[MaltegoLink]:
        self.notify_delete(link)
        for observer in self.get_observers():
            link.unregister(observer)
        return self.__links.pop(link.maltego_link_id, None)

    @property
    def entities(self) -> List[MaltegoEntity]:
        """Returns all entities in the graph as a List"""
        return list(self.__entities.values())

    @property
    def links(self) -> List[MaltegoLink]:
        """Returns all links in the graph as a List"""
        return list(self.__links.values())

    def add_entities(
            self,
            entities: List[MaltegoEntity]
    ) -> List[MaltegoEntity]:
        """Adds one or more entities to the Graph

        :param entities: Entities to add
        :type entities: List[MaltegoEntity]
        :raises ValueError: Thrown if input is not a List
        :return: Returns the added entities
        :rtype: List[MaltegoEntity]
        """
        if not isinstance(entities, list):
            raise ValueError('Entities should be an instance of a list')
        return [self.__add_entity(entity) for entity in entities]

    def add_entity(
            self,
            entity: MaltegoEntity
    ) -> MaltegoEntity:
        """Adds a single entity to the graph

        :param entity: Entity to add
        :type entity: MaltegoEntity
        :raises TypeError: Raised if input is not a subclass of MaltegoEntity
        :return: Returns the added entity
        :rtype: MaltegoEntity
        """
        if not isinstance(entity, MaltegoEntity):
            raise TypeError("You can only add a MaltegoEntity to the graph")
        self.__add_entity(entity)
        return entity

    def delete_entity(self, entity: MaltegoEntity) -> Optional[MaltegoEntity]:
        """Delete a single entity from the graph

        :param entity: Entity to delete
        :type entity: Optional[MaltegoEntity]
        :raises TypeError: Raised if input is not a subclass of MaltegoEntity
        :return: Returns the deleted entity if present
        :rtype: Optional[MaltegoEntity]
        """
        if not isinstance(entity, MaltegoEntity):
            raise TypeError(
                "The input parameter of the delete_entity method should be a MaltegoEntity")
        return self.__delete_entity(entity)

    def delete_entity_by_id(self, entity_id: str) -> Optional[MaltegoEntity]:
        """Delete a single entity from the graph using the entity id

        :param entity_id: Entity ID to delete
        :type entity_id: Optional[MaltegoEntity]
        :return: Returns the deleted entity if present
        :rtype: Optional[MaltegoEntity]
        """
        if entity_id not in self.__entities:
            return None
        return self.__delete_entity(self.__entities[entity_id])

    def add_child(
        self,
        entity: MaltegoEntity,
        child: MaltegoEntity,
        link_properties: Optional[Dict[str, Any]] = None
    ) -> MaltegoEntity:
        """Adds an entity to the graph as a child of another entity.

        When using this function a link between entity and child is added automatically

        :param entity: Parent Entity
        :type entity: MaltegoEntity
        :param child: Child Entity
        :type child: MaltegoEntity
        :param link_properties: Optional link properties for the created link, defaults to None
        :type link_properties: Optional[Dict[str, Any]], optional
        :raises TypeError: Raises a TypeError if either of the input entities in not a child of MaltegoEntity
        :return: Returns the added Entity
        :rtype: MaltegoEntity
        """
        if not isinstance(entity, MaltegoEntity):
            raise TypeError("The parent entity is not of type MaltegoEntity")
        if not isinstance(child, MaltegoEntity):
            raise TypeError("The child entity is not of type MaltegoEntity")

        self.add_link(
            source=entity,
            target=child,
            properties=link_properties,
            is_reversed=child.reverse_link,
            style=child.link_style,
            label=child.link_label,
            thickness=child.link_thickness,
            color=child.link_color
        )
        return child

    def add_link(
            self,
            source: MaltegoEntity,
            target: MaltegoEntity,
            is_reversed: bool = False,
            style: LinkStyle = LinkStyle.NORMAL,
            color: LinkColor = LinkColor.NONE,
            thickness: LinkThickness = LinkThickness.THICKNESS_DEFAULT,
            properties: Optional[Dict[str, Any]] = None,
            label: Optional[str] = None
    ) -> MaltegoLink:
        """Adds a link between two entities

        :param source: Source Entity
        :type source: MaltegoEntity
        :param target: Target Entity
        :type target: MaltegoEntity
        :param is_reversed: Link direction. Link is reversed if set to True, defaults to False
        :type is_reversed: bool, optional
        :param style: Optional Link Style, defaults to LinkStyle.NORMAL
        :type style: LinkStyle, optional
        :param color: Optional Link Color, defaults to LinkColor.NONE
        :type color: LinkColor, optional
        :param thickness: Optional Link Thickness, defaults to LinkThickness.THICKNESS_2
        :type thickness: LinkThickness, optional
        :param properties: Optional properties added to the link, defaults to None
        :type properties: Optional[Dict[str, Any]], optional
        :param label: Optional Link Label, defaults to None
        :type label: Optional[str], optional
        :raises TypeError: Raises a Type Error if any of the inputs is not a MaltegoEntity
        :return: Returns the added link
        :rtype: MaltegoLink
        """
        if not isinstance(source, MaltegoEntity):
            raise TypeError("The source entity is not of type MaltegoEntity")
        if not isinstance(target, MaltegoEntity):
            raise TypeError("The target entity is not of type MaltegoEntity")

        if source.maltego_entity_id not in self.__entities:
            source = self.add_entity(source)

        if target.maltego_entity_id not in self.__entities:
            target = self.add_entity(target)

        link = MaltegoLink(
            source_id=source.maltego_entity_id,
            target_id=target.maltego_entity_id,
            is_reversed=is_reversed,
            style=style,
            color=color,
            thickness=thickness,
            properties=properties,
            label=label
        )
        self.__add_link(link)

        return link


    def delete_link(self, link: MaltegoLink) -> Optional[MaltegoLink]:
        if not isinstance(link, MaltegoLink):
            raise TypeError("The input parameter of the delete_link method should be a MaltegoLink")
        return self.__delete_link(link)

    def get_entities_by_property(
        self,
        property_name: str,
    ) -> List[MaltegoEntity]:
        """Returns all entities in the graph with a given property

        :param property_name: The name of the property.
                              All entities having a property matching this name will be returned
        :type property_name: str
        :return: List of entities that matches the filter
        :rtype: List[MaltegoEntity]
        """
        entities = []
        for entity in self.__entities.values():
            if entity.has_property(property_name):
                entities.append(entity)
        return entities

    def get_entities_of_type(self, entity_type_id: str) -> List[MaltegoEntity]:
        """Returns all entities in the graph with a given type name

        :param entity_type_id: Type ID. e. g. "maltego.Phrase"
        :type entity_type_id: str
        :return: List of entities that matches the given type
        :rtype: List[MaltegoEntity]
        """
        return [entity for _, entity in self.__entities.items() if entity.TYPE_NAME == entity_type_id]

    def get_entity_by_id(self, entity_id: str) -> Optional[MaltegoEntity]:
        """Return the entity with the given id if present.

        The ID is a unique identification for each entity generated by the maltego client and it not to be confused with
        the entities type id (i. e. maltego.Phrase)

        :param entity_id: ID of the entity to retrieve
        :type entity_id: str
        :rtype: Optional[MaltegoEntity]
        """
        return self.__entities.get(entity_id, None)

    def get_link_from(self, entity: MaltegoEntity) -> Optional[MaltegoLink]:
        """Returns first links from the given entity to any other entity

        :param entity: Source Entity
        :type entity: MaltegoEntity
        :raises TypeError: Raises a TypeError if input is not a MaltegoEntity
        :return: Link from the given source entity
        :rtype: Optional[MaltegoLink]
        """
        assert check_entity_type(entity)

        if entity.maltego_entity_id not in self.__entities:
            raise ValueError(
                "The entity that you are trying to get the links from is not present on in the Graph"
            )

        for link in self.__links.values():
            if link.source_id == entity.maltego_entity_id:
                return link

        return None

    def get_links_from(self, entity: MaltegoEntity) -> List[MaltegoLink]:
        """Returns all links from the given entity to any other entity

        :param entity: Source Entity
        :type entity: MaltegoEntity
        :raises TypeError: Raises a TypeError if input is not a MaltegoEntity
        :return: Links from the given source entity
        :rtype: Optional[MaltegoLink]
        """
        assert check_entity_type(entity)

        if entity.maltego_entity_id not in self.__entities:
            raise ValueError(
                "The entity that you are trying to get the links from is not present on in the Graph"
            )

        links_from = []
        for link in self.__links.values():
            if link.source_id == entity.maltego_entity_id:
                links_from.append(link)

        return links_from

    def get_link_to(self, entity: MaltegoEntity) -> Optional[MaltegoLink]:
        """Returns first links to the given entity from any other entity

        :param entity: Target Entity
        :type entity: MaltegoEntity
        :raises TypeError: Raises a TypeError if input is not a MaltegoEntity
        :return: Link to the given target entity
        :rtype: Optional[MaltegoLink]
        """
        assert check_entity_type(entity)

        if entity.maltego_entity_id not in self.__entities:
            raise ValueError(
                "The entity that you are trying to get the links to is not present on in the Graph"
            )

        for link in self.__links.values():
            if link.target_id == entity.maltego_entity_id:
                return link

        return None


    def get_links_to(self, entity: MaltegoEntity) -> List[MaltegoLink]:
        """Returns all links to the given entity from any other entity

        :param entity: Target Entity
        :type entity: MaltegoEntity
        :raises TypeError: Raises a TypeError if input is not a MaltegoEntity
        :return: Links to the given target entity
        :rtype: Optional[MaltegoLink]
        """
        assert check_entity_type(entity)

        if entity.maltego_entity_id not in self.__entities:
            raise ValueError(
                "The entity that you are trying to get the links to is not present on in the Graph"
            )

        links_to = []
        for link in self.__links.values():
            if link.target_id == entity.maltego_entity_id:
                links_to.append(link)

        return links_to

    def get_link_between(
            self,
            source_entity: MaltegoEntity,
            target_entity: MaltegoEntity
    ) -> Optional[MaltegoLink]:
        """Get link between two given entities

        :param source_entity: Source Entity
        :type source_entity: MaltegoEntity
        :param target_entity: TargetEntity
        :type target_entity: MaltegoEntity
        :raises TypeError: Raised if either of the inputs is not a MaltegoEntity
        :raises ValueError: Raised if either of the inputs is not part of the Graph
        :return: Link if exists
        :rtype: Optional[MaltegoLink]
        """
        if not isinstance(source_entity, MaltegoEntity) or not isinstance(target_entity, MaltegoEntity):
            raise TypeError("The source_entity and the target_entity must be of type Entity")

        if source_entity.maltego_entity_id not in self.__entities:
            raise ValueError("The source entity is not present on the Graph")

        if target_entity.maltego_entity_id not in self.__entities:
            raise ValueError("The target entity is not present on the Graph")

        for link in self.__links.values():
            if link.source_id == source_entity.maltego_entity_id and link.target_id == target_entity.maltego_entity_id:
                return link
        return None

    def get_source(self, link: MaltegoLink) -> MaltegoEntity:
        """Returns the entity that is the source of a given link

        :param link: Link to resolve
        :type link: MaltegoLink
        :raises TypeError: Raised if the input is not a Link
        :raises ValueError: Raised if the link is not part of the graph
        :return: Source Entity of the link
        :rtype: MaltegoEntity
        """
        if not isinstance(link, MaltegoLink):
            raise TypeError("The link must be of type MaltegoLink")

        if link.maltego_link_id not in self.__links:
            raise ValueError("The link is not present on the Graph")

        source_entity = self.__entities.get(link.source_id)

        if source_entity is None:
            raise ValueError(
                f"The source entity with id {link.source_id} can not be found on the Graph"
            )

        return source_entity

    def get_target(self, link: MaltegoLink) -> MaltegoEntity:
        """Returns the entity that is the target of a given link

        :param link: Link to resolve
        :type link: MaltegoLink
        :raises TypeError: Raised if the input is not a Link
        :raises ValueError: Raised if the link is not part of the graph
        :return: Target Entity of the link
        :rtype: MaltegoEntity
        """
        if not isinstance(link, MaltegoLink):
            raise TypeError("The link must be of type MaltegoLink")

        if link.maltego_link_id not in self.__links:
            raise ValueError("The link is not present on the Graph")

        target_entity = self.__entities.get(link.target_id)

        if target_entity is None:
            raise ValueError(
                f"The target entity with id {link.target_id} is not present on the Graph"
            )

        return target_entity

    def get_child_entities(
            self,
            entity: MaltegoEntity
    ) -> List[MaltegoEntity]:
        """Get all child entities of a given entity. Child entities are all entities with a link from the source entity

        :param entity: Parent Entity
        :type entity: MaltegoEntity
        :raises TypeError: Raised if input is not a MaltegoEntity
        :raises ValueError: Raised if parent entity is not part of the graph
        :return: Returns all child entities found on the Graph
        :rtype: List[MaltegoEntity]
        """
        if not isinstance(entity, MaltegoEntity):
            raise TypeError("The parent entity must be of type MaltegoEntity")

        if entity.maltego_entity_id not in self.__entities:
            raise ValueError("The parent entity is not present on the Graph")

        child_entities = []
        for link in self.__links.values():
            if link.source_id == entity.maltego_entity_id:
                child_entity = self.__entities.get(link.target_id)
                if child_entity is None:
                    raise ValueError(f"The child entity with id {link.target_id} "
                                     f"for parent entity with id {entity.maltego_entity_id} "
                                     f"could not be found on the Graph")
                child_entities.append(child_entity)

        return child_entities

    @property
    def primary_entities(self) -> List[MaltegoEntity]:
        """
        Parent/top-level entities: everything not marked as a composite child.
        This is the “only parent level” view.
        """
        if not self.__composite_entity_ids:
            return list(self.__entities.values())
        comp = self.__composite_entity_ids
        return [e for e in self.__entities.values() if e.maltego_entity_id not in comp]

    def get_links_from_and_to(self, source_entity: MaltegoEntity, target_entity: MaltegoEntity) -> List[MaltegoLink]:
        """Get all links between two entities

        :param source_entity: Source Entity from which the links originate
        :type source_entity: MaltegoEntity
        :param target_entity: Target Entity of the links
        :type target_entity: MaltegoEntity
        :raises TypeError: Raised if inputs are not subclass of MaltegoEntity
        :return: Links between source and target entity
        :rtype: List[MaltegoLink]
        """
        if not isinstance(source_entity, MaltegoEntity):
            raise TypeError("The source entity must be of type MaltegoEntity")

        if not isinstance(target_entity, MaltegoEntity):
            raise TypeError("The target entity must be of type MaltegoEntity")

        from_and_to_links = []
        for link in self.__links.values():
            if link.source_id == source_entity.maltego_entity_id and link.target_id == target_entity.maltego_entity_id:
                from_and_to_links.append(link)

        return from_and_to_links

    def process_entity_typed_properties(self, entity: MaltegoEntity) -> List[Tuple[str, str]]:
        """
        Scan an entity for any nested MaltegoEntity props,
        add them to the graph (if not already), and return the list
        of (property_name, child_entity_id)
        """
        ent_ids = self.__add_entity_from_properties(entity, set())
        if ent_ids:
            self.__add_entity_property_links(entity, ent_ids)
        return ent_ids
