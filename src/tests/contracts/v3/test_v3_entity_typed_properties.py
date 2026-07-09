# Copyright (c) Maltego Technologies GmbH.
import httpx
import pytest

from tests.conftest import AffiliationComposite, UniqueIdentifier
from maltego.model.entity.property import _MaltegoEntityProperty as MaltegoEntityProperty
from maltego.model.input_constraints.property.equals import PropertyValueEquals
from maltego.model.input_constraints.property.match import PropertyValueStringMatch, ConstraintStringMatchType
from maltego.model.input_constraints.property.regex import PropertyValueMatchesRegex
from tests.conftest import MOCK_TRANSFORM_RUN_REQUEST_V3_ENTITY_TYPED_PROPERTY, MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN, \
    NAMESPACE, PREFIX, Phrase, Person, Alias
from tests.contracts.v3.test_v3_transform_execution import run_v3_transform

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_get_assets_entities_example(async_client_example_server: httpx.AsyncClient) -> None:
    response = await async_client_example_server.get("/api/v3/assets/entities",
                                                     headers={"maltego-client-capabilities": "compositeEntities"})
    assert response.status_code == 200
    ent = [ent for ent in response.json() if ent.get("id") == "maltego.AffiliationComposite"][0]
    assert ent == {
        "id": "maltego.AffiliationComposite",
        "displayName": "Affiliation",
        "displayNamePlural": "Affiliations",
        "iconResource": "Affiliation",
        "description": "A composite entity containing information about an affiliation",
        "category": "Social Network",
        "visible": True,
        "allowedRoot": True,
        "conversionOrder": 2147483647,
        "baseEntities": [],
        "overlays": [],
        "properties": {
            "value": "uid",
            "valueKey": "properties.uniqueidentifier",
            "displayValue": "person",
            "displayKey": "person.fullname",
            "fields": [
                {
                    "name": "person",
                    "matchingRule": "loose",
                    "type": "ENTITY",
                    "displayName": "Account Owner",
                    "nullable": True,
                    "hidden": False,
                    "readonly": False,
                    "description": "The owner of this account.",
                    "isArray": False,
                    "sampleValue": "Jane Doe",
                    "linkProperties": [
                        {
                            "name": "maltego.link.label",
                            "value": "To Owner",
                            "type": "STRING"
                        }
                    ],
                    "entityType": "maltego.Person"
                },
                {
                    "name": "alias",
                    "matchingRule": "loose",
                    "type": "ENTITY",
                    "displayName": "Aliases",
                    "nullable": True,
                    "hidden": False,
                    "readonly": False,
                    "description": "A list of aliases.",
                    "isArray": True,
                    "entityType": "maltego.Alias"
                },
                {
                    "name": "uid",
                    "matchingRule": "strict",
                    "type": "ENTITY",
                    "displayName": "UID",
                    "nullable": True,
                    "hidden": False,
                    "readonly": False,
                    "description": "A unique identifier for the account.",
                    "isArray": False,
                    "entityType": "maltego.UniqueIdentifier"
                },
                {
                    "name": "profile_image",
                    "matchingRule": "loose",
                    "type": "ENTITY",
                    "displayName": "Profile Image",
                    "nullable": True,
                    "hidden": False,
                    "readonly": False,
                    "description": "The profile image of the account.",
                    "isArray": False,
                    "entityType": "maltego.Image"
                }
            ]
        },
        "actions": []
    }


@pytest.mark.asyncio
async def test_composed_affiliation_transform(async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 10

    # AffiliationComposite (parent) should be first
    assert result_events[0]["data"]["inputType"] == "ENTITY"
    assert result_events[0]["data"]["entity"]["type"] == "maltego.AffiliationComposite"

    # Children follow
    assert result_events[1]["data"]["inputType"] == "ENTITY"
    assert result_events[1]["data"]["entity"]["type"] == "maltego.Person"

    assert result_events[2]["data"]["inputType"] == "ENTITY"
    assert result_events[2]["data"]["entity"]["type"] == "maltego.Alias"

    assert result_events[3]["data"]["inputType"] == "ENTITY"
    assert result_events[3]["data"]["entity"]["type"] == "maltego.Alias"

    assert result_events[4]["data"]["inputType"] == "ENTITY"
    assert result_events[4]["data"]["entity"]["type"] == "maltego.UniqueIdentifier"

    def is_composite_link(event):
        link_props = event["data"]["link"].get("properties", {})
        return any(
            [True for link in link_props if link.get("name") == "maltego.link.composite" and link.get("value") == True])

    for i, target_idx in zip(range(5, 9), [1, 2, 3, 4]):
        assert result_events[i]["data"]["inputType"] == "LINK"
        assert is_composite_link(result_events[i])
        assert result_events[i]["data"]["link"]["sourceId"] == result_events[0]["data"]["entity"]["id"]
        assert result_events[i]["data"]["link"]["targetId"] == result_events[target_idx]["data"]["entity"]["id"]

    # Last link: not composite
    assert result_events[9]["data"]["inputType"] == "LINK"
    link_props_9 = result_events[9]["data"]["link"].get("properties", {})
    assert "#maltego.composite.link" not in link_props_9
    assert result_events[9]["data"]["link"]["sourceId"] == "0"
    assert result_events[9]["data"]["link"]["targetId"] == result_events[0]["data"]["entity"]["id"]


@pytest.mark.asyncio
async def test_composed_affiliation_enrich_transform(async_client_example_server: httpx.AsyncClient) -> None:
    # TODO: when update events are fixed for transforms with Entity In -> Graph Out, this response will change
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_enrich_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_ENTITY_TYPED_PROPERTY,
        composed=True,
    )

    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 12

    assert result_events[0]["data"]["inputType"] == "ENTITY"
    assert result_events[0]["data"]["entity"]["type"] == "maltego.AffiliationComposite"

    assert result_events[1]["data"]["inputType"] == "ENTITY"
    assert result_events[1]["data"]["entity"]["type"] == "maltego.Person"

    assert result_events[2]["data"]["inputType"] == "ENTITY"
    assert result_events[2]["data"]["entity"]["type"] == "maltego.Alias"

    assert result_events[3]["data"]["inputType"] == "ENTITY"
    assert result_events[3]["data"]["entity"]["type"] == "maltego.Alias"

    assert result_events[5]["data"]["inputType"] == "ENTITY"
    assert result_events[5]["data"]["entity"]["type"] == "maltego.Image"

    uid_ent = next(
        e["data"]["entity"]
        for e in result_events
        if e["data"]["inputType"] == "ENTITY"
        and e["data"]["entity"]["type"] == "maltego.UniqueIdentifier"
    )
    assert uid_ent["id"] == "1"

    def is_composite_link(event):
        link_props = event["data"]["link"].get("properties", {})
        return any(
            prop.get("name") == "maltego.link.composite" and prop.get("value") is True
            for prop in link_props
        )

    for i, target_idx in zip(range(6, 11), [1, 2, 3, 4, 5]):
        assert result_events[i]["data"]["inputType"] == "LINK"
        assert is_composite_link(result_events[i])
        assert result_events[i]["data"]["link"]["sourceId"] == result_events[0]["data"]["entity"]["id"]
        assert result_events[i]["data"]["link"]["targetId"] == result_events[target_idx]["data"]["entity"]["id"]

    # Last link: not composite
    assert result_events[11]["data"]["inputType"] == "LINK"
    link_props_11 = result_events[11]["data"]["link"].get("properties", {})
    assert not any(
        prop.get("name") == "maltego.link.composite" and prop.get("value") is True
        for prop in link_props_11
    )
    assert result_events[11]["data"]["link"]["sourceId"] == result_events[0]["data"]["entity"]["id"]
    assert result_events[11]["data"]["link"]["targetId"] == result_events[0]["data"]["entity"]["id"]

    assert all(event["data"].get("eventType") == "ADD" for event in result_events)


@pytest.mark.asyncio
async def test_delete_composed_affiliation_transform(async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.delete_composed_affiliation_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_ENTITY_TYPED_PROPERTY,
        composed=True,
    )

    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 1

    delete_event = result_events[0]
    assert delete_event["data"]["inputType"] == "ENTITY"
    assert delete_event["data"]["eventType"] == "DELETE"
    assert delete_event["data"]["entity"].get("id") == "4"


@pytest.mark.asyncio
async def test_duplicate_child_composed_affiliation_transform(async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.duplicate_child_composed_affiliation_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )

    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 11

    # Last event should be a link (explicit add_child link)
    last_event = result_events[10]
    assert last_event["data"]["inputType"] == "LINK"

    # There should NOT be a composite link property
    link_props = last_event["data"]["link"].get("properties", [])
    assert not any(
        prop.get("name") == "maltego.link.composite" and prop.get("value") is True
        for prop in link_props
    ), "Explicitly added child link should not have composite property."

    affiliation_composite = next(
        e["data"]["entity"]
        for e in result_events
        if e["data"]["inputType"] == "ENTITY"
        and e["data"]["entity"]["type"] == "maltego.AffiliationComposite"
    )
    person_entity = next(
        e["data"]["entity"]
        for e in result_events
        if e["data"]["inputType"] == "ENTITY"
        and e["data"]["entity"]["type"] == "maltego.Person"
    )

    assert last_event["data"]["link"]["sourceId"] == affiliation_composite["id"]
    assert last_event["data"]["link"]["targetId"] == person_entity["id"]


@pytest.mark.asyncio
async def test_duplicate_child_delete_composed_affiliation_transform(
        async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.duplicate_child_delete_composed_affiliation_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )

    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 12

    # Last link event should not have the composite property
    last_link_event = result_events[10]
    assert last_link_event["data"]["inputType"] == "LINK"

    link_props = last_link_event["data"]["link"].get("properties", [])
    assert not any(
        prop.get("name") == "maltego.link.composite" and prop.get("value") is True
        for prop in link_props
    ), "Explicit link after deletion should not have the composite property."

    # Find AffiliationComposite and Person entities
    affiliation_composite = next(
        e["data"]["entity"]
        for e in result_events
        if e["data"]["inputType"] == "ENTITY"
        and e["data"]["entity"]["type"] == "maltego.AffiliationComposite"
    )
    person_entity = next(
        e["data"]["entity"]
        for e in result_events
        if e["data"]["inputType"] == "ENTITY"
        and e["data"]["entity"]["type"] == "maltego.Person"
    )

    assert last_link_event["data"]["link"]["sourceId"] == affiliation_composite["id"]
    assert last_link_event["data"]["link"]["targetId"] == person_entity["id"]


@pytest.mark.asyncio
async def test_shared_children_composed_affiliation_transform(async_client_example_server: httpx.AsyncClient) -> None:
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.shared_children_composed_affiliation_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 16

    def is_composite_link(event):
        link_props = event["data"]["link"].get("properties", [])
        return any(
            prop.get("name") == "maltego.link.composite" and prop.get("value") is True
            for prop in link_props
        )

    child_types = {"maltego.Person", "maltego.Alias", "maltego.UniqueIdentifier"}
    child_entities = [
        event["data"]["entity"]
        for event in result_events
        if event["data"]["inputType"] == "ENTITY"
           and event["data"]["entity"]["type"] in child_types
    ]
    child_entity_ids = set(ent["id"] for ent in child_entities)

    composite_entities = [
        event["data"]["entity"]
        for event in result_events
        if event["data"]["inputType"] == "ENTITY"
           and event["data"]["entity"]["type"] == "maltego.AffiliationComposite"
    ]
    assert len(composite_entities) == 2
    affiliation_composite_2 = composite_entities[1]

    link_events = [event for event in result_events if event["data"]["inputType"] == "LINK"]
    composite_links = [event for event in link_events if
                       is_composite_link(event) and event["data"]["link"]["sourceId"] == affiliation_composite_2["id"]]

    assert len(composite_links) == 4
    for link_event in composite_links:
        assert link_event["data"]["link"]["targetId"] in child_entity_ids

    last_link_event = link_events[-1]
    link_props = last_link_event["data"]["link"].get("properties", [])
    assert not any(
        prop.get("name") == "maltego.link.composite" and prop.get("value") is True
        for prop in link_props
    )
    assert last_link_event["data"]["link"]["sourceId"] == "0"
    assert last_link_event["data"]["link"]["targetId"] == affiliation_composite_2["id"]


@pytest.mark.asyncio
async def test_composed_affiliation_dynamic_prop_transform(async_client_example_server: httpx.AsyncClient) -> None:
    def find_alias_entity_by_value(events, alias_value):
        return next(
            event["data"]["entity"]
            for event in events
            if event["data"]["inputType"] == "ENTITY"
            and event["data"]["entity"]["type"] == "maltego.Alias"
            and any(
                prop.get("name") == "alias" and prop.get("value") == alias_value
                for prop in event["data"]["entity"].get("properties", [])
            )
        )

    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_dynamic_prop_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )
    assert len(status_response) == 1
    result_events = status_response[0].json()["result"]['events']
    assert len(result_events) == 12

    affiliation_composite = next(
        event["data"]["entity"]
        for event in result_events
        if event["data"]["inputType"] == "ENTITY" and event["data"]["entity"]["type"] == "maltego.AffiliationComposite"
    )
    dynamic_alias_ent = find_alias_entity_by_value(result_events, "EntityAlias")

    prop = next(
        (p for p in affiliation_composite.get("properties", [])
         if p.get("name") == "dynamic_alias_ent" and p.get("type") == "ENTITY"),
        None
    )
    assert prop is not None, "AffiliationComposite should have dynamic_alias_ent property of type ENTITY"

    assert prop.get("value") == dynamic_alias_ent["id"]

    link_found = any(
        event["data"]["inputType"] == "LINK"
        and event["data"]["link"]["sourceId"] == affiliation_composite["id"]
        and event["data"]["link"]["targetId"] == dynamic_alias_ent["id"]
        for event in result_events
    )
    assert link_found, "There should be a link from AffiliationComposite to the dynamic alias entity."


@pytest.mark.asyncio
async def test_wrong_entity_type_for_composite_prop_transform(async_client_example_server: httpx.AsyncClient):
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.wrong_entity_type_for_composite_prop_transform",
        MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN,
        composed=True,
    )
    result_json = status_response[0].json()
    assert result_json["result"]["events"][0]["data"]["statusMessage"]["text"].startswith("Unexpected exception")


@pytest.mark.asyncio
async def test_list_transform_returns_list_of_three(mock_context):
    from tests.example.transforms.entity_typed_properties import list_composed_affiliation_transform
    root = Phrase("foo")
    results = await list_composed_affiliation_transform(root, mock_context)
    assert isinstance(results, list) and len(results) == 3
    for ent in results:
        assert isinstance(ent, AffiliationComposite)
        assert ent.person is not None
        assert isinstance(ent.alias, list)


@pytest.mark.asyncio
async def test_mixed_typing_rejects_wrong_type(mock_context):
    from tests.example.transforms.entity_typed_properties import composed_affiliation_dynamic_prop_transform_mixed_typing
    root = Phrase("foo")
    with pytest.raises(TypeError):
        await composed_affiliation_dynamic_prop_transform_mixed_typing(root, mock_context)


@pytest.mark.asyncio
async def test_composed_bad_input(async_client_example_server: httpx.AsyncClient) -> None:
    duplicate_id_in_request = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.AffiliationComposite": 1,
                    "maltego.Person": 1,
                    "maltego.UniqueIdentifier": 1,
                    "maltego.Alias": 2,
                },
                "entitiesTotalCount": 5,
                "linksTotalCount": 0,
                "rootEntitiesCount": 5
            },
            "graph": {
                "entities": [
                    {
                        "id": "2pq5od4f2sm3l",
                        "valueRef": "uid",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "alias",
                                "value": ["2rgjai77r4fv7", "2q0a1pfwkhl79"],
                                "type": "ENTITY",
                                "displayName": "Aliases",
                                "matchingRule": "loose"
                            },
                            {
                                "name": "uid",
                                "value": "2uk2ryumtxufk",
                                "type": "ENTITY",
                                "displayName": "UID",
                                "matchingRule": "strict"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.AffiliationComposite",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2uk2ryumtxufk",
                        "valueRef": "properties.uniqueidentifier",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "properties.uniqueidentifier",
                                "value": "1477245957",
                                "type": "STRING",
                                "displayName": "UniqueIdentifier",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.UniqueIdentifier",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2rgjai77r4fv7",
                        "valueRef": "alias",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "alias",
                                "value": "johndoe42",
                                "type": "STRING",
                                "displayName": "Alias",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.Alias",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2rgjai77r4fv7",
                        "valueRef": "alias",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "alias",
                                "value": "john.d",
                                "type": "STRING",
                                "displayName": "Alias",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.Alias",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                ],
                "links": []
            }
        },
        "limit": 12,
        "transformSettings": [],
        "transformRunExecutionContext": {
            "graphId": "2mwypxcnpgoiw",
            "runSource": "DIRECT",
            "sourceName": None
        }
    }
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_enrich_transform",
        duplicate_id_in_request,
        composed=True,
        expected_run_response=400,
    )

    assert run_response.json()["detail"] == "Invalid request: malformed input entities"  # R2-6: generic detail

    missing_id_in_request = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.AffiliationComposite": 1,
                    "maltego.Person": 1,
                    "maltego.UniqueIdentifier": 1,
                    "maltego.Alias": 2,
                },
                "entitiesTotalCount": 5,
                "linksTotalCount": 0,
                "rootEntitiesCount": 5
            },
            "graph": {
                "entities": [
                    {
                        "id": "2pq5od4f2sm3l",
                        "valueRef": "uid",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "person",
                                "value": ["2fse051hmsm01"],
                                "type": "ENTITY",
                                "displayName": "Account Owner",
                                "matchingRule": "loose"
                            },
                            {
                                "name": "uid",
                                "value": "2uk2ryumtxufk",
                                "type": "ENTITY",
                                "displayName": "UID",
                                "matchingRule": "strict"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.AffiliationComposite",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2fse051hmsm01",
                        "valueRef": "person.fullname",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "person.fullname",
                                "value": "John Doe",
                                "type": "STRING",
                                "displayName": "Full Name",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.Person",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2uk2ryumtxufk",
                        "valueRef": "properties.uniqueidentifier",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "properties.uniqueidentifier",
                                "value": "1477245957",
                                "type": "STRING",
                                "displayName": "UniqueIdentifier",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.UniqueIdentifier",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                ],
                "links": []
            }
        },
        "limit": 12,
        "transformSettings": [],
        "transformRunExecutionContext": {
            "graphId": "2mwypxcnpgoiw",
            "runSource": "DIRECT",
            "sourceName": None
        }
    }

    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_enrich_transform",
        missing_id_in_request,
        composed=True,
        expected_run_response=400,
    )

    assert run_response.json()["detail"] == "Invalid value for ENTITY-typed property 'person': list"

    wrong_entity_reference_id = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.AffiliationComposite": 1,
                    "maltego.Person": 1,
                    "maltego.UniqueIdentifier": 1,
                    "maltego.Alias": 2,
                },
                "entitiesTotalCount": 5,
                "linksTotalCount": 0,
                "rootEntitiesCount": 5
            },
            "graph": {
                "entities": [
                    {
                        "id": "2pq5od4f2sm3l",
                        "valueRef": "uid",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "person",
                                "value": 11111,
                                "type": "ENTITY",
                                "displayName": "Account Owner",
                                "matchingRule": "loose"
                            },
                            {
                                "name": "uid",
                                "value": "2uk2ryumtxufk",
                                "type": "ENTITY",
                                "displayName": "UID",
                                "matchingRule": "strict"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.AffiliationComposite",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2fse051hmsm01",
                        "valueRef": "person.fullname",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "person.fullname",
                                "value": "John Doe",
                                "type": "STRING",
                                "displayName": "Full Name",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.Person",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    },
                    {
                        "id": "2uk2ryumtxufk",
                        "valueRef": "properties.uniqueidentifier",
                        "weight": 100,
                        "properties": [
                            {
                                "name": "properties.uniqueidentifier",
                                "value": "1477245957",
                                "type": "STRING",
                                "displayName": "UniqueIdentifier",
                                "matchingRule": "loose"
                            }
                        ],
                        "displayInformation": [],
                        "type": "maltego.UniqueIdentifier",
                        "overlays": [],
                        "bookmark": -1,
                        "baseEntities": [],
                        "note": ""
                    }
                ],
                "links": []
            }
        },
        "limit": 12,
        "transformSettings": [],
        "transformRunExecutionContext": {
            "graphId": "2mwypxcnpgoiw",
            "runSource": "DIRECT",
            "sourceName": None
        }
    }
    run_response, status_response = await run_v3_transform(
        async_client_example_server,
        f"{PREFIX}.{NAMESPACE}.composed_affiliation_enrich_transform",
        wrong_entity_reference_id,
        composed=True,
        expected_run_response=400,
    )

    assert run_response.json()["detail"] == "ENTITY property 'person' must be a string ID or list of string IDs; got: int"


def test_property_value_equals_with_entity_typed_property():
    """Test PropertyValueEquals constraint with entity-typed property extracts the main value."""
    person = Person("John Doe")
    person.fullname = "John Doe"
    person.firstnames = "John"
    person.lastname = "Doe"

    person_property = MaltegoEntityProperty(
        name="person",
        display_name="Person",
        value=person,
        annotated_type=Person
    )

    # Test equals constraint - should extract person.fullname (the main value)
    constraint = PropertyValueEquals(value="John Doe")
    assert constraint.evaluate(person_property) is True

    # Test with non-matching value
    constraint_no_match = PropertyValueEquals(value="Jane Doe")
    assert constraint_no_match.evaluate(person_property) is False

    # Test case-insensitive matching
    constraint_case_insensitive = PropertyValueEquals(value="john doe", ignore_case=True)
    assert constraint_case_insensitive.evaluate(person_property) is True


def test_property_value_equals_with_nested_entity_typed_property():
    """Test PropertyValueEquals with double-nested entity (entity contains entity)."""
    uid = UniqueIdentifier("12345")
    uid.uniqueidentifier = "12345"

    affiliation = AffiliationComposite(uid)
    affiliation.uid = uid

    composite_property = MaltegoEntityProperty(
        name="affiliation",
        display_name="Affiliation Composite",
        value=affiliation,
        annotated_type=AffiliationComposite
    )

    # The main value of AffiliationComposite is uid (which is UniqueIdentifier)
    # The main value of UniqueIdentifier is uniqueidentifier = "12345"
    # So this should extract: affiliation.uid.uniqueidentifier -> "12345"
    constraint = PropertyValueEquals(value="12345")
    assert constraint.evaluate(composite_property) is True

    constraint_no_match = PropertyValueEquals(value="99999")
    assert constraint_no_match.evaluate(composite_property) is False


def test_property_value_string_match_with_entity_typed_property():
    """Test PropertyValueStringMatch constraint with entity-typed property."""
    person = Person("Alice Smith")
    person.fullname = "Alice Smith"
    person.firstnames = "Alice"
    person.lastname = "Smith"

    person_property = MaltegoEntityProperty(
        name="person",
        display_name="Person",
        value=person,
        annotated_type=Person
    )

    # Test CONTAINS match
    constraint_contains = PropertyValueStringMatch(
        value="Alice",
        match_type=ConstraintStringMatchType.CONTAINS
    )
    assert constraint_contains.evaluate(person_property) is True

    # Test STARTSWITH match
    constraint_startswith = PropertyValueStringMatch(
        value="Alice",
        match_type=ConstraintStringMatchType.STARTSWITH
    )
    assert constraint_startswith.evaluate(person_property) is True

    # Test ENDSWITH match
    constraint_endswith = PropertyValueStringMatch(
        value="Smith",
        match_type=ConstraintStringMatchType.ENDSWITH
    )
    assert constraint_endswith.evaluate(person_property) is True

    # Test no match
    constraint_no_match = PropertyValueStringMatch(
        value="Bob",
        match_type=ConstraintStringMatchType.CONTAINS
    )
    assert constraint_no_match.evaluate(person_property) is False

    # Test case-insensitive
    constraint_case_insensitive = PropertyValueStringMatch(
        value="alice",
        match_type=ConstraintStringMatchType.STARTSWITH,
        ignore_case=True
    )
    assert constraint_case_insensitive.evaluate(person_property) is True


def test_property_value_string_match_with_nested_entity():
    """Test PropertyValueStringMatch with double-nested entity."""
    uid = UniqueIdentifier("UA-1234567-89")
    uid.uniqueidentifier = "UA-1234567-89"

    affiliation = AffiliationComposite(uid)
    affiliation.uid = uid

    composite_property = MaltegoEntityProperty(
        name="affiliation",
        display_name="Affiliation Composite",
        value=affiliation,
        annotated_type=AffiliationComposite
    )

    # Test pattern matching on the nested value
    constraint_startswith = PropertyValueStringMatch(
        value="UA-",
        match_type=ConstraintStringMatchType.STARTSWITH
    )
    assert constraint_startswith.evaluate(composite_property) is True

    constraint_contains = PropertyValueStringMatch(
        value="1234567",
        match_type=ConstraintStringMatchType.CONTAINS
    )
    assert constraint_contains.evaluate(composite_property) is True


def test_property_value_matches_regex_with_entity_typed_property():
    """Test PropertyValueMatchesRegex constraint with entity-typed property."""
    person = Person("John.Doe@example.com")
    person.fullname = "John.Doe@example.com"
    person.firstnames = "John"
    person.lastname = "Doe"

    person_property = MaltegoEntityProperty(
        name="person",
        display_name="Person",
        value=person,
        annotated_type=Person
    )

    # Test email regex pattern
    constraint_email = PropertyValueMatchesRegex(
        regex=r"^[\w\.-]+@[\w\.-]+\.\w+$"
    )
    assert constraint_email.evaluate(person_property) is True

    # Test non-matching regex
    constraint_no_match = PropertyValueMatchesRegex(
        regex=r"^\d+$"  # Numbers only
    )
    assert constraint_no_match.evaluate(person_property) is False


def test_property_value_matches_regex_with_nested_entity():
    """Test PropertyValueMatchesRegex with double-nested entity."""
    uid = UniqueIdentifier("UA-1553321-5")
    uid.uniqueidentifier = "UA-1553321-5"

    affiliation = AffiliationComposite(uid)
    affiliation.uid = uid

    composite_property = MaltegoEntityProperty(
        name="affiliation",
        display_name="Affiliation Composite",
        value=affiliation,
        annotated_type=AffiliationComposite
    )

    # Test Google Analytics ID pattern
    constraint_ga_pattern = PropertyValueMatchesRegex(
        regex=r"^UA-\d{7}-\d{1,2}$"
    )
    assert constraint_ga_pattern.evaluate(composite_property) is True

    # Test non-matching pattern
    constraint_no_match = PropertyValueMatchesRegex(
        regex=r"^G-[A-Z0-9]+$"  # GA4 pattern
    )
    assert constraint_no_match.evaluate(composite_property) is False


def test_property_constraints_with_list_of_entities():
    """Test that constraints work with list properties containing entity-typed values."""
    alias1 = Alias("johndoe42")
    alias1.alias = "johndoe42"

    alias2 = Alias("john.d")
    alias2.alias = "john.d"

    aliases_property = MaltegoEntityProperty(
        name="aliases",
        display_name="Aliases",
        value=[alias1, alias2],
        annotated_type=list[Alias]
    )

    # Test equals - should match if ANY element matches
    constraint_equals = PropertyValueEquals(value="johndoe42")
    assert constraint_equals.evaluate(aliases_property) is True

    constraint_equals_second = PropertyValueEquals(value="john.d")
    assert constraint_equals_second.evaluate(aliases_property) is True

    constraint_no_match = PropertyValueEquals(value="notfound")
    assert constraint_no_match.evaluate(aliases_property) is False


def test_property_value_equals_hierarchical_with_entity():
    """Test evaluate_with_hierarchy returns proper results for entity-typed properties."""
    person = Person("Test User")
    person.fullname = "Test User"
    person.firstnames = "Test"
    person.lastname = "User"

    person_property = MaltegoEntityProperty(
        name="person",
        display_name="Person",
        value=person,
        annotated_type=Person
    )

    # Test successful match with hierarchy
    constraint = PropertyValueEquals(value="Test User")
    result = constraint.evaluate_with_hierarchy(person_property)

    assert result.success is True
    assert "Test User" in result.message
    assert "matches" in result.message

    # Test failed match with hierarchy
    constraint_no_match = PropertyValueEquals(value="Other User")
    result_no_match = constraint_no_match.evaluate_with_hierarchy(person_property)

    assert result_no_match.success is False
    assert "does not match" in result_no_match.message


def test_property_value_string_match_hierarchical_with_entity():
    """Test evaluate_with_hierarchy for PropertyValueStringMatch with entity-typed properties."""
    person = Person("Alice Bob Carol")
    person.fullname = "Alice Bob Carol"

    person_property = MaltegoEntityProperty(
        name="person",
        display_name="Person",
        value=person,
        annotated_type=Person
    )

    constraint = PropertyValueStringMatch(
        value="Bob",
        match_type=ConstraintStringMatchType.CONTAINS
    )
    result = constraint.evaluate_with_hierarchy(person_property)

    assert result.success is True
    assert "contains" in result.message
    assert "Bob" in result.message


def test_property_value_regex_hierarchical_with_entity():
    """Test evaluate_with_hierarchy for PropertyValueMatchesRegex with entity-typed properties."""
    uid = UniqueIdentifier("UA-9876543-21")
    uid.uniqueidentifier = "UA-9876543-21"

    uid_property = MaltegoEntityProperty(
        name="uid",
        display_name="Unique Identifier",
        value=uid,
        annotated_type=UniqueIdentifier
    )

    constraint = PropertyValueMatchesRegex(regex=r"^UA-\d{7}-\d{1,2}$")
    result = constraint.evaluate_with_hierarchy(uid_property)

    assert result.success is True
    assert "matches regex pattern" in result.message
    assert "UA-9876543-21" in result.message
