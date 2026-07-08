# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=redefined-outer-name,line-too-long,unused-argument,too-many-lines
from typing import List, Optional, Union, Dict, Any
from unittest.mock import MagicMock

import asyncio

import sys
import importlib
import datetime
import json
import base64
import httpx
from maltego.model.entity.config import MaltegoEntityRegexConverter
from maltego.model.entity.property import MEF, LinkProperties
import pytest
import os

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from starlette.requests import Request
from maltego.model.graph import MaltegoGraph
from maltego.model.link import MaltegoLink
from maltego.model.machine import MaltegoMachine
from maltego.model.input_constraints import (
    ConstraintStringMatchType,
    EntityHasPropertySatisfying,
    EntitySatisfiesAll,
    EntitySatisfiesNone,
    EntityTypeConstraint,
    PropertyNameEquals,
    PropertySatisfiesAll,
    PropertyValueMatchesRegex,
    PropertyValueStringMatch,
)

from maltego.model.types import Color, MATCHING_RULE_LOOSE, Url, daterange
from maltego.model.entity import (
    MaltegoEntity,
    MaltegoEntityConfig,
    MaltegoEntityProperty,
)
from maltego.model.transform import MaltegoTransform
from maltego.runner import ThreadedTransformRunner
from maltego.runner.transform_result_set import TransformResultSet
from maltego.model.server import EntityConfigOverride, EntityConfigOverrides
from maltego.server import (
    MaltegoTransformServer,
    MaltegoServerSettings,
    MaltegoContext,
    IntegrationClient,
    TransformSetting,
)
import maltego.server

from maltego.protocol.v3.execution.transform_run import TransformRunRequest
from tests.fixtures.files import config_file, example_config_file, zip_to_json
from tests.fixtures.clients import minimal_integration_client, mocked_integration_client
from tests.fixtures.pagination import (
    TEST_HEADERS,
    TEST_JSON,
    TEST_PARAMS,
    TEST_URL,
    offset_limit_paginator,
    page_based_paginator,
    pagination_state,
    pagination_state_with_offset_limit,
    pagination_state_with_page,
)

TEST_CONTENT = "I Am Some Body Content"

NAMESPACE = "maltoso.test"
PREFIX = "pytest"
SERVER = "https://"

MOCK_HEADER_V3 = {"Maltego-API-Key": "foobarbaz"}
UA_4_0_0 = {"user-agent": "Maltego Desktop/4.0.0 (Maltego One Eval; Mac OS X; 14.3; 0)"}
UA_4_7_0 = {"user-agent": "Maltego Desktop/4.7.0 (Maltego One Eval; Mac OS X; 14.3; 0)"}
UA_4_7_2 = {"user-agent": "Maltego Desktop/4.7.2 (Maltego One Eval; Mac OS X; 14.3; 0)"}
UA_4_8_0 = {
    "user-agent": "Maltego Desktop/4.8.0 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)"
}
UA_4_8_1 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)"
}

UA_4_8_2 = {
    "user-agent": "Maltego Desktop/4.8.2 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)"
}

UA_4_10_0 = {
    "user-agent": "Maltego Desktop/4.10.0 (Maltego One Eval; Mac OS X; 14.3; 0)"
}

UA_5_0_0 = {
    "user-agent": "Maltego Desktop/5.0.0 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)"
}

# Desktop version that supports coalesce (must match COALESCE_MIN_DESKTOP)
UA_9_9_9 = {
    "user-agent": "Maltego Desktop/9.9.9 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)"
}

UA_LATEST = UA_4_8_1

GRAPH_BROWSER_1_0_0 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)",
    "maltego-client-identifier": "Maltego Graph Browser",
    "maltego-client-version": "1.0.0",
}
GRAPH_BROWSER_2_0_0 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)",
    "maltego-client-identifier": "Maltego Graph Browser",
    "maltego-client-version": "2.0.0",
}

GRAPH_BROWSER_2_1_0 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)",
    "maltego-client-identifier": "Maltego Graph Browser",
    "maltego-client-version": "2.1.0",
}

GRAPH_BROWSER_3_0_0 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)",
    "maltego-client-identifier": "Maltego Graph Browser",
    "maltego-client-version": "3.0.0",
}

GRAPH_BROWSER_3_0_2 = {
    "user-agent": "Maltego Desktop/4.8.1 (Graph Desktop Organization Plan; Mac OS X; 15.0.1; 6668347)",
    "maltego-client-identifier": "Maltego Graph Browser",
    "maltego-client-version": "3.0.2",
}


class Alias(MaltegoEntity):
    TYPE_NAME = "maltego.Alias"
    Config = MaltegoEntityConfig(
        value_property="alias",
        display_name="Alias",
        description="An alias for a person",
        display_property="alias",
        category="Personal",
        display_name_plural="Aliases",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="Alias",
        _visible=True,
    )
    alias: str = MEF(
        name="alias",
        display_name="Alias",
        description="An Alias for a person",
        sample_value="Mr. T",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class Phrase(MaltegoEntity):
    TYPE_NAME = "maltego.Phrase"
    Config = MaltegoEntityConfig(
        value_property="text",
        display_name="Phrase",
        description="Any text or part thereof",
        display_property="text",
        category="Personal",
        display_name_plural="Phrases",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="Phrase",
        _visible=True,
    )
    text: str = MEF(
        name="text",
        display_name="Text",
        sample_value="Some phrase",
    )

class ExtendedPhraseListStr(MaltegoEntity):
    TYPE_NAME = "maltego.ExtendedPhraseListStr"
    Config = MaltegoEntityConfig(
        value_property="text",
        display_name="Phrase",
        description="Any text or part thereof",
        display_property="text",
        category="Personal",
        display_name_plural="Phrases",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="Phrase",
        _visible=True,
    )
    text: str = MEF(
        name="text",
        display_name="Text",
        sample_value="Some phrase",
    )
    list_str: List[str] = MEF(
        name="list_str",
        display_name="List of Strings",
    )


class Person(MaltegoEntity):
    TYPE_NAME = "maltego.Person"
    Config = MaltegoEntityConfig(
        value_property="person.fullname",
        display_name="Person",
        description="Entity representing a human",
        display_property="person.fullname",
        category="Personal",
        display_name_plural="People",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="Person",
        _visible=True,
    )
    fullname: str = MEF(
        name="person.fullname",
        display_name="Full Name",
        value="$trim($property(person.firstnames) $property(person.lastname))",
        matching_rule=MATCHING_RULE_LOOSE,
        evaluator="maltego.replace",
    )
    firstnames: str = MEF(
        name="person.firstnames",
        display_name="First Names",
        sample_value="John",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    lastname: str = MEF(
        name="person.lastname",
        display_name="Surname",
        sample_value="Doe",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class Document(MaltegoEntity):
    TYPE_NAME = "maltego.Document"
    Config = MaltegoEntityConfig(
        value_property="title",
        display_name="Document",
        description="A document on the Internet",
        display_property="title",
        category="Personal",
        display_name_plural="Documents",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="InternetDocument",
        _visible=True,
    )
    title: str = MEF(
        name="title",
        display_name="Title",
        sample_value="Some Document",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    meta_data: str = MEF(
        name="document.meta-data",
        display_name="Meta-Data",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    url: str = MEF(
        name="url",
        display_name="URL",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class Domain(MaltegoEntity):
    TYPE_NAME = "maltego.Domain"
    Config = MaltegoEntityConfig(
        value_property="fqdn",
        display_name="Domain",
        description="An internet domain",
        display_property="fqdn",
        category="Infrastructure",
        display_name_plural="Domains",
        # overlays= TODO
        # overlay_image_property TODO
        icon_resource="NetworkGlobal",
        _visible=True,
    )
    fqdn: str = MEF(
        name="fqdn",
        display_name="Domain Name",
        sample_value="maltego.com",
    )
    whois_info: str = MEF(
        name="whois-info",
        display_name="WHOIS Info",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class DNSName(MaltegoEntity):
    TYPE_NAME = "maltego.DNSName"
    Config = MaltegoEntityConfig(
        value_property="fqdn",
        display_name="DNS Name",
        description="Domain Name System server name",
        display_property="fqdn",
        category="Infrastructure",
        display_name_plural="DNS Names",
        icon_resource="ServerDNS",
        conversion_order=100,
        _visible=True,
        converter=MaltegoEntityRegexConverter(
            regex=r"[-\w]{1,120}\.[-\w]{1,120}\.[-\w]{0,120}\.*[-\w]{1,4}\.*[a-zA-Z]+[-\w]{1,3}"
        ),
    )
    fqdn: str = MEF(
        name="fqdn",
        display_name="DNS Name",
        sample_value="maltego.com",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class IPv4Address(MaltegoEntity):
    TYPE_NAME = "maltego.IPv4Address"
    Config = MaltegoEntityConfig(
        value_property="ipv4-address",
        display_name="IPv4 Address",
        description="An IP version 4 address",
        display_property="ipv4-address",
        category="Infrastructure",
        display_name_plural="IPv4 Addresses",
        icon_resource="NetworkCard",
        _visible=True,
        conversion_order=60,
        converter=MaltegoEntityRegexConverter(
            regex=r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
        ),
    )
    ipv4_address: str = MEF(
        name="ipv4-address",
        display_name="IP Address",
        sample_value="93.184.216.34",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    internal: bool = MEF(
        name="ipaddress.internal",
        display_name="Internal",
        sample_value=False,
        matching_rule=MATCHING_RULE_LOOSE,
    )


class Image(MaltegoEntity):
    TYPE_NAME = "maltego.Image"
    Config = MaltegoEntityConfig(
        value_property="description",
        display_name="Image",
        description="A visual representation of something",
        display_property="description",
        category="Personal",
        display_name_plural="Images",
        icon_resource="Image",
        conversion_order=85,
        overlay_image_property="url",
        _visible=True,
        converter=MaltegoEntityRegexConverter(
            regex=r"(http[s]*://[-\w\.\:]*[^\s]*/([^\s]+\.(bmp|jpg|jpeg|png|gif|svg|webp))(\?[^\s]*)?)",
            groups=[
                "url",
                "description",
            ],
        ),
    )
    description: str = MEF(
        name="description",
        display_name="Description",
        sample_value="Image",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    url: Url = MEF(
        name="url",
        display_name="URL",
    )


class UniqueIdentifier(MaltegoEntity):
    TYPE_NAME = "maltego.UniqueIdentifier"
    Config = MaltegoEntityConfig(
        value_property="properties.uniqueidentifier",
        display_name="Tracking Code",
        description="Represents a tracking code for a web service.",
        display_property="properties.uniqueidentifier",
        category="Infrastructure",
        display_name_plural="UniqueIdentifiers",
        icon_resource="Log",
        _visible=True,
    )
    uniqueidentifier: str = MEF(
        name="properties.uniqueidentifier",
        display_name="UniqueIdentifier",
        value=" ",
        sample_value="UA-1553321-*",
        matching_rule=MATCHING_RULE_LOOSE,
    )
    identifier_type: str = MEF(
        name="identifierType",
        display_name="Identifier Type",
        sample_value="Google Analytics ID",
        matching_rule=MATCHING_RULE_LOOSE,
    )


class AffiliationComposite(MaltegoEntity):
    TYPE_NAME = "maltego.AffiliationComposite"
    Config = MaltegoEntityConfig(
        value_property="uid",
        value_key="properties.uniqueidentifier",  # Optionally, extract a specific attribute from the uid entity for value
        display_name="Affiliation",
        description="A composite entity containing information about an affiliation",
        display_property="person",
        display_key="person.fullname",  # Optionally, extract a specific attribute from the person entity
        category="Social Network",
        display_name_plural="Affiliations",
        icon_resource="Affiliation",
        _visible=True,
    )

    person: Person = MEF(
        name="person",
        display_name="Account Owner",
        description="The owner of this account.",
        matching_rule=MATCHING_RULE_LOOSE,
        sample_value="Jane Doe",
        link_properties=LinkProperties(is_reversed=False, label="To Owner"),
    )

    alias: List[Alias] = MEF(
        name="alias",
        display_name="Aliases",
        description="A list of aliases.",
        matching_rule=MATCHING_RULE_LOOSE,
    )

    uid: UniqueIdentifier = MEF(
        name="uid",
        display_name="UID",
        description="A unique identifier for the account.",
    )

    profile_image: Image = MEF(
        name="profile_image",
        display_name="Profile Image",
        matching_rule="loose",
        description="The profile image of the account.",
    )


class ComplexEntity2(MaltegoEntity):
    TYPE_NAME = "maltego.complexEntity2"
    Config = MaltegoEntityConfig(
        value_property="str_property",
        display_name="complexEntity",
        icon_resource=("maltego_transforms_test_image_resampling", "resources/icons/maltego_logo.png"),
        description="A custom entity",
        display_property="str_property",
        category="Custom",
        allowed_root=True,
        display_name_plural="complexEntities",
    )

    str_property: str = MaltegoEntityProperty(
        readonly=True,
        nullable=False,
        display_name="String",
        description="String Test Property",
        sample_value="Foo"
    )
    float_property: float = MaltegoEntityProperty(
        display_name="Float",
        name="float",
        description="Float Test Property",
        sample_value=42.23
    )
    int_property: int = MaltegoEntityProperty(
        display_name="Integer",
        name="int",
        description="Integer Test Property",
        sample_value=42
    )
    bool_property: bool = MaltegoEntityProperty(
        display_name="Boolean",
        name="bool",
        description="Boolean Test Property",
        sample_value=True
    )
    date_property: datetime.date = MaltegoEntityProperty(
        display_name="Date",
        name="date",
        description="Date Test Property",
        sample_value=datetime.date.fromtimestamp(0)
    )
    datetime_property: datetime.datetime = MaltegoEntityProperty(
        display_name="Datetime",
        name="datetime",
        description="Datetime Test Property",
        sample_value=datetime.datetime.fromtimestamp(0)
    )
    daterange_property: daterange = MaltegoEntityProperty(
        display_name="Daterange",
        name="daterange",
        description="Daterange Test Property",
        sample_value=daterange(
            start=datetime.datetime.fromtimestamp(0),
            end=datetime.datetime.fromtimestamp(100000)
        )
    )
    daterange2_property: daterange = MaltegoEntityProperty(
        display_name="Daterange2",
        name="daterange2",
        description="Daterange2 Test Property",
        sample_value=daterange(date_range=daterange.Ranges.last_10_years)
    )
    str_list_property: List[str] = MaltegoEntityProperty(
        display_name="String List",
        name="string_list",
        description="String List Test Property",
        sample_value=["Foo", "Bar", "Baz"]
    )
    float_list_property: List[float] = MaltegoEntityProperty(
        display_name="Float List",
        name="float_list",
        description="Float List Test Property",
        sample_value=[42.23, 23.42]
    )
    int_list_property: List[int] = MaltegoEntityProperty(
        display_name="Integer List",
        name="int_list",
        description="Integer List Test Property",
        sample_value=[42, 23]
    )
    bool_list_property: List[bool] = MaltegoEntityProperty(
        display_name="Boolean List",
        name="bool_list",
        description="Boolean List Test Property",
        sample_value=[True, False]
    )
    url: Url = MaltegoEntityProperty(
        display_name="Url",
        name="url",
        description="URL Test Property",
        sample_value="https://www.exmaple.com"
    )
    color: Color = MaltegoEntityProperty(
        display_name="Color",
        name="color",
        description="Color Test Property",
        sample_value="#ffff00"
    )


TEST_INPUT_CONSTRAINT_ALIAS = EntitySatisfiesAll(
    constraints=[
        EntityTypeConstraint(entity_type="maltego.Alias"),
        EntityHasPropertySatisfying(
            constraint=PropertySatisfiesAll(
                constraints=[
                    PropertyValueStringMatch(
                        value="username11",
                        ignore_case=True,
                        match_type=ConstraintStringMatchType.STARTSWITH
                    ),
                    PropertyNameEquals(value="alias"),
                ]
            )
        )
    ]
)

TEST_INPUT_CONSTRAINT_ALIAS_NOT = EntitySatisfiesNone(
    constraints=[
        EntityHasPropertySatisfying(
            constraint=PropertySatisfiesAll(
                constraints=[
                    PropertyValueStringMatch(
                        value="username11",
                        ignore_case=True,
                        match_type=ConstraintStringMatchType.STARTSWITH,
                    ),
                    PropertyNameEquals(value="alias"),
                ]
            )
        )
    ]
)

TEST_INPUT_CONSTRAINT_REGEX = EntitySatisfiesAll(
    constraints=[
        EntityHasPropertySatisfying(
            constraint=PropertySatisfiesAll(
                constraints=[
                    PropertyValueMatchesRegex(
                        regex=r"^(?!-)[A-Za-z0-9-]{1,63}\.[A-Za-z]{2,6}$"
                    )
                ]
            )
        )
    ]
)


def generate_oauth_token_request() -> str:

    from tests.example import OAUTH
    public_key = OAUTH.get_public_key()
    cipher = PKCS1_v1_5.new(public_key)
    return base64.b64encode(cipher.encrypt(b"Foo")).decode("utf-8")


def generate_jwe_oauth_token(payload: dict, public_key: RSA.RsaKey, header: dict | None = None) -> str:
    from authlib.jose import JsonWebEncryption
    jwe = JsonWebEncryption()
    header = header or {"alg": "RSA-OAEP-256", "enc": "A256GCM"}
    return jwe.serialize_compact(header, json.dumps(payload).encode(), public_key.export_key()).decode()


ENCRYPTED_OAUTH_TOKEN = generate_oauth_token_request()
MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_COUNT = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "1",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "2",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_WRONG_METADATA_ENTITY = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Person": 1},
            "entitiesTotalCount": 0,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "1",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_V3 = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        },
                        {
                            "displayName": "User ID",
                            "name": "UserId",
                            "type": "INT",
                            "value": 1,
                        },
                        {
                            "displayName": "Post Id",
                            "name": "id",
                            "type": "INT",
                            "value": 6,
                        },
                        {
                            "displayName": "daterange",
                            "name": "daterange",
                            "type": "DATE_RANGE",
                            "value": "1970-01-01T10:00:00.000+10:00/2023-02-16T10:47:47.070Z",
                        },
                        {
                            "displayName": "datetime",
                            "name": "datetime",
                            "type": "DATE_TIME",
                            "value": "1970-01-01T10:00:00.000+10:00",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}


MOCK_TRANSFORM_RUN_REQUEST_OAUTH_V3 = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [{"name": "test.oauth.token", "value": ENCRYPTED_OAUTH_TOKEN}],
}

MOCK_TRANSFORM_RUN_REQUEST_OAUTH_2_0_V3 = {
    **MOCK_TRANSFORM_RUN_REQUEST_OAUTH_V3,
    "transformSettings": [{"name": "github.token", "value": ENCRYPTED_OAUTH_TOKEN}],
}

MOCK_TRANSFORM_RUN_REQUEST_V3_UNKNOWN = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "dolorem eum magni eos aperiam quia",
                        },
                        {
                            "displayName": "User ID",
                            "name": "UserId",
                            "type": "INT",
                            "value": 1,
                        },
                        {
                            "displayName": "Post Id",
                            "name": "id",
                            "type": "INT",
                            "value": 6,
                        },
                        {
                            "displayName": "daterange",
                            "name": "daterange",
                            "type": "DATE_RANGE",
                            "value": "1970-01-01T10:00:00.000+10:00/2023-02-16T10:47:47.070Z",
                        },
                        {
                            "displayName": "datetime",
                            "name": "datetime",
                            "type": "DATE_TIME",
                            "value": "1970-01-01T10:00:00.000+10:00",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_V3_ENTITY_TYPED_PROPERTY = {
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
            "rootEntitiesCount": 5,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "person.fullname",
                    "weight": 100,
                    "properties": [
                        {
                            "name": "person.fullname",
                            "value": "John Doe",
                            "type": "STRING",
                            "displayName": "Full Name",
                            "matchingRule": "loose",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Person",
                    "overlays": [],
                    "bookmark": -1,
                    "baseEntities": [],
                    "note": "",
                },
                {
                    "id": "1",
                    "valueRef": "properties.uniqueidentifier",
                    "weight": 100,
                    "properties": [
                        {
                            "name": "properties.uniqueidentifier",
                            "value": "1477245957",
                            "type": "STRING",
                            "displayName": "UniqueIdentifier",
                            "matchingRule": "loose",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.UniqueIdentifier",
                    "overlays": [],
                    "bookmark": -1,
                    "baseEntities": [],
                    "note": "",
                },
                {
                    "id": "2",
                    "valueRef": "alias",
                    "weight": 100,
                    "properties": [
                        {
                            "name": "alias",
                            "value": "johndoe42",
                            "type": "STRING",
                            "displayName": "Alias",
                            "matchingRule": "loose",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Alias",
                    "overlays": [],
                    "bookmark": -1,
                    "baseEntities": [],
                    "note": "",
                },
                {
                    "id": "3",
                    "valueRef": "alias",
                    "weight": 100,
                    "properties": [
                        {
                            "name": "alias",
                            "value": "john.d",
                            "type": "STRING",
                            "displayName": "Alias",
                            "matchingRule": "loose",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Alias",
                    "overlays": [],
                    "bookmark": -1,
                    "baseEntities": [],
                    "note": "",
                },
                {
                    "id": "4",
                    "valueRef": "uid",
                    "weight": 100,
                    "properties": [
                        {
                            "name": "person",
                            "value": "0",
                            "type": "ENTITY",
                            "displayName": "Account Owner",
                            "matchingRule": "loose",
                        },
                        {
                            "name": "alias",
                            "value": ["2", "3"],
                            "type": "ENTITY",
                            "displayName": "Aliases",
                            "matchingRule": "loose",
                        },
                        {
                            "name": "uid",
                            "value": "1",
                            "type": "ENTITY",
                            "displayName": "UID",
                            "matchingRule": "strict",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.AffiliationComposite",
                    "overlays": [],
                    "bookmark": -1,
                    "baseEntities": [],
                    "note": "",
                },
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_MERGE_V3 = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 3},
            "entitiesTotalCount": 3,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo1",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "1",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo2",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "2",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo3",
                        },
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
            ],
            "links": [],
        },
    },
    "transformSettings": [],
    "limit": 12,
}


MOCK_TRANSFORM_RUN_REQUEST_V3_LIST_IN = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 2, "maltego.Person": 1},
            "entitiesTotalCount": 3,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "1",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "2",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Person",
                    "bookmark": None,
                },
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_GRAPH_V3 = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 2, "maltego.Person": 1},
            "entitiesTotalCount": 3,
            "linksTotalCount": 1,
            "rootEntitiesCount": 1,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "1",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                },
                {
                    "id": "2",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Person",
                    "bookmark": None,
                },
            ],
            "links": [
                {"id": "0", "sourceId": "0", "targetId": "1", "properties": []},
                {"id": "1", "sourceId": "0", "targetId": "2", "properties": []},
                {"id": "2", "sourceId": "1", "targetId": "0", "properties": []},
                {"id": "3", "sourceId": "1", "targetId": "2", "properties": []},
                {"id": "4", "sourceId": "2", "targetId": "0", "properties": []},
                {"id": "5", "sourceId": "2", "targetId": "1", "properties": []},
            ],
        },
    },
    "limit": 12,
    "transformSettings": [],
}


MOCK_TRANSFORM_RUN_REQUEST_V3_ALL_SETTINGS = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Phrase": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Phrase",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.int",
            "value": 111,
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.daterange",
            "value": "1970-01-01T10:00:00.000+10:00/2023-02-16T10:47:47.070Z",
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.str",
            "value": "Foo",
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.date",
            "value": "2023-02-16",
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.boolean",
            "value": True,
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.datetime",
            "value": "2023-02-11 21:47:51.584+10:00",
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.transform_all_settings.double",
            "value": 123.321,
        },
        {
            "name": f"{PREFIX}.{NAMESPACE}.global.global#setting_global_legacy",
            "value": "123.321",
        },
        {
            "name": f"global#{PREFIX}.{NAMESPACE}.setting_global",
            "value": "123.321",
        },
    ],
}

MOCK_TRANSFORM_RUN_REQUEST_V3_SIMPLE_ENTITY = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.simpleEntity": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.simpleEntity",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}

MOCK_TRANSFORM_RUN_REQUEST_V3_PERSON_IN = {
    "input": {
        "metadata": {
            "entitiesTypesStat": {"maltego.Person": 1},
            "entitiesTotalCount": 1,
            "linksTotalCount": 0,
            "rootEntitiesCount": 0,
        },
        "graph": {
            "entities": [
                {
                    "id": "0",
                    "valueRef": "text",
                    "iconUrl": "str",
                    "weight": 100,
                    "properties": [
                        {
                            "displayName": "Text",
                            "name": "text",
                            "type": "STRING",
                            "value": "Foo",
                        }
                    ],
                    "displayInformation": [],
                    "type": "maltego.Person",
                    "bookmark": None,
                }
            ],
            "links": [],
        },
    },
    "limit": 12,
    "transformSettings": [],
}


MOCK_TRANSFORM_RUN_REQUEST_V2 = f"""
<MaltegoMessage>
  <MaltegoTransformRequestMessage>
    <Entities>
      <Entity Type="maltego.Phrase">
        <Genealogy>
          <Type Name="maltego.Phrase" OldName="Phrase"/>
        </Genealogy>
        <AdditionalFields>
          <Field Name="text" DisplayName="Text">Some phrase</Field>
        </AdditionalFields>
        <Weight>0</Weight>
        <Value>Some phrase</Value>
      </Entity>
    </Entities>
    <TransformFields>
      <Field Name="matchSubstrings">42</Field>
      <Field Name="Test">42</Field>
      <Field Name="test.oauth.token">{ENCRYPTED_OAUTH_TOKEN}</Field>
    </TransformFields>
    <Limits HardLimit="256" SoftLimit="256"/>
  </MaltegoTransformRequestMessage>
</MaltegoMessage>
"""

MOCK_TRANSFORM_RUN_REQUEST_V2_OAUTH_2_0 = MOCK_TRANSFORM_RUN_REQUEST_V2.replace(
    'Name="test.oauth.token"',
    'Name="github.token"'
)

MOCK_TRANSFORM_RUN_REQUEST_V2_UNKNOWN = """
<MaltegoMessage>
  <MaltegoTransformRequestMessage>
    <Entities>
      <Entity Type="maltego.Unknown">
        <Genealogy>
          <Type Name="maltego.Phrase" OldName="Phrase"/>
        </Genealogy>
        <AdditionalFields>
          <Field Name="text" DisplayName="Text">Some phrase</Field>
        </AdditionalFields>
        <Weight>0</Weight>
        <Value>Some phrase</Value>
      </Entity>
    </Entities>
    <TransformFields/>
    <Limits HardLimit="256" SoftLimit="256"/>
  </MaltegoTransformRequestMessage>
</MaltegoMessage>
"""

MOCK_TRANSFORM_RUN_REQUEST_V2_PERSON_IN = """
<MaltegoMessage>
  <MaltegoTransformRequestMessage>
    <Entities>
      <Entity Type="maltego.Person">
        <Genealogy>
          <Type Name="maltego.Person" OldName="Person"/>
        </Genealogy>
        <AdditionalFields>
          <Field Name="text" DisplayName="Text">Some phrase</Field>
        </AdditionalFields>
        <Weight>0</Weight>
        <Value>Some phrase</Value>
      </Entity>
    </Entities>
    <TransformFields/>
    <Limits HardLimit="256" SoftLimit="256"/>
  </MaltegoTransformRequestMessage>
</MaltegoMessage>
"""

MOCK_TRANSFORM_RUN_REQUEST_V2_SIMPLE_ENTITY = """
<MaltegoMessage>
  <MaltegoTransformRequestMessage>
    <Entities>
      <Entity Type="maltego.simpleEntity">
        <Genealogy>
          <Type Name="maltego.simpleEntity"/>
        </Genealogy>
        <Weight>0</Weight>
        <Value></Value>
      </Entity>
    </Entities>
    <Limits SoftLimit="12" HardLimit="12"/>
  </MaltegoTransformRequestMessage>
</MaltegoMessage>
"""

MOCK_TRANSFORM_RUN_REQUEST_V2_ALL_SETTINGS = """
<MaltegoMessage>
  <MaltegoTransformRequestMessage>
    <Entities>
      <Entity Type="maltego.Phrase">
        <Genealogy>
          <Type Name="maltego.Phrase" OldName="Phrase"/>
        </Genealogy>
        <AdditionalFields>
          <Field Name="text" DisplayName="Text">Some phrase</Field>
        </AdditionalFields>
        <Weight>0</Weight>
        <Value>Some phrase</Value>
      </Entity>
    </Entities>
    <TransformFields>
      <Field Name="pytest.maltoso.transform_all_settings.int">111</Field>
      <Field Name="pytest.maltoso.transform_all_settings.daterange">.000-1676544467.070</Field>
      <Field Name="pytest.maltoso.transform_all_settings.str">asd</Field>
      <Field Name="pytest.maltoso.transform_all_settings.date">2023-02-16</Field>
      <Field Name="pytest.maltoso.transform_all_settings.boolean">true</Field>
      <Field Name="pytest.maltoso.transform_all_settings.datetime">2023-02-11 12:47:51.584 +0100</Field>
      <Field Name="onprem.com.maltego.pyjinx.transform_all_settings.daterange_relative">1686703386.087-1686746586.087</Field>
      <Field Name="pytest.maltoso.transform_all_settings.double">123.321</Field>
      <Field Name="pytest.maltoso.global.global#setting_global_legacy">123.321</Field>
      <Field Name="global#pytest.maltoso.setting_global">123.321</Field>
    </TransformFields>
    <Limits HardLimit="256" SoftLimit="256"/>
  </MaltegoTransformRequestMessage>
</MaltegoMessage>
"""

EXAMPLE_TRANSFORM_TEST_CASES: Dict[str, Any] = {
    f"{PREFIX}.{NAMESPACE}.transform": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_person": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2_PERSON_IN,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3_PERSON_IN,
    },
    f"{PREFIX}.{NAMESPACE}.transform_list": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_union": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_list_union": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_custom_entity": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2_SIMPLE_ENTITY,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3_SIMPLE_ENTITY,
    },
    f"{PREFIX}.robin.rich_transform": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_all_settings": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2_ALL_SETTINGS,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3_ALL_SETTINGS,
    },
    f"{PREFIX}.{NAMESPACE}.transform_str_annotations": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_oauth": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_OAUTH_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_oauth_2_0": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2_OAUTH_2_0,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_OAUTH_2_0_V3,
    },
    f"{PREFIX}.{NAMESPACE}.display_field_test": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_sync": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_async": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_async_gen": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.exception_test": {
        "expected_v2status": 250,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.exception_test_2": {
        "expected_v2status": 251,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.exception_test_3": {
        "expected_v2status": 252,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.exception_test_4": {
        "expected_v2status": 253,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_kwargs": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_default": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_phrase_child": {
        "expected_v2status": 200,
        "v2payload": MOCK_TRANSFORM_RUN_REQUEST_V2,
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
}

EXAMPLE_V3_TRANSFORM_TEST_CASES: Dict[str, Any] = {
    f"{PREFIX}.{NAMESPACE}.transform_add_remove_graph_entities": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_delete_all_links": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_create_mesh_links": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_add_remove_graph_links": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_update_graph_entities": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_update_graph_links": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_V3,
    },
    f"{PREFIX}.{NAMESPACE}.transform_merge_phrases": {
        "expected_v3status_run": 201,
        "expected_v3status_result": 200,  # R3-1: GET returns 200
        "v3payload": MOCK_TRANSFORM_RUN_REQUEST_MERGE_V3,
    },
}


class TestMachine(MaltegoMachine):

    code = """
    machine("maltego.testmachine",
    displayName:"maltego-transforms Test Machine",
    author:"Maltego Technologies GmbH",
    description:"Test Machine") {
        start {
            paths {
                path {
                    run("paterva.v2.datapass-poi.SocialNetBulkSearchAlias")
                }
                path {
                    run("paterva.v2.datapass-poi.maltego.constella.search_for_username")
                    paths {
                        path{
                            run("paterva.v2.datapass-poi.maltego.constella.extract_company")
                        }
                        path{
                            run("paterva.v2.datapass-poi.maltego.constella.extract_credit_card")
                        }
                    }
                }
            }
        }
    }
"""


class RichEntity(MaltegoEntity):
    TYPE_NAME = "maltego.RichEntity"
    Config = MaltegoEntityConfig(
        value_property="my_string_value",
        display_property="my_string_value",
        category="Custom1",
        display_name="My Fancy Phrase",
        description="A new fancy phrase entity",
        icon_resource=("Assemble", os.path.dirname(__file__) + "/resources/BtcBlock.png"),
    )
    my_int_value: int = MaltegoEntityProperty(sample_value=1)
    my_other_int_value: int = 23
    foo_entity: int
    bar_entity = 1
    my_float_value: float = MaltegoEntityProperty(sample_value=2.1)
    my_int_array_value: List[int] = MaltegoEntityProperty(sample_value=[1, 2, 3])
    my_float_array_value: List[float] = MaltegoEntityProperty(
        sample_value=[0.1, 0.2, 0.3]
    )
    my_bool_value: bool = MaltegoEntityProperty(sample_value=True)
    my_bool_array_value: List[bool] = MaltegoEntityProperty(sample_value=[True, False])
    my_string_by_default_value = MaltegoEntityProperty(
        sample_value="this is a string by default"
    )
    my_string_value: str = MaltegoEntityProperty(
        sample_value="this is an annotated string"
    )
    my_string_array_value: List[str] = MaltegoEntityProperty(
        sample_value="this is a string".split()
    )
    my_date_value: datetime.date = MaltegoEntityProperty(
        sample_value=datetime.date.fromtimestamp(0)
    )
    # my_date_array_value: List[datetime.date] = MaltegoEntityField(sample_value=[datetime.date.today(), datetime.date.today().replace(year=1999)])
    my_datetime_value: datetime.datetime = MaltegoEntityProperty(
        sample_value=datetime.datetime.fromtimestamp(0)
    )
    my_daterange_value: daterange = MaltegoEntityProperty(
        sample_value=daterange(
            start=datetime.datetime(
                year=1999, day=19, month=5, tzinfo=datetime.timezone.utc
            ),
            end=datetime.datetime(
                year=2021, day=19, month=5, tzinfo=datetime.timezone.utc
            ),
        )
    )
    my_other_daterange_value: daterange = MaltegoEntityProperty(
        sample_value=daterange.Ranges.previous_week
    )
    # my_datetime_array_value: List[datetime.datetime] = MaltegoEntityField(sample_value=[datetime.datetime.now(), datetime.datetime.now().replace(year=1999)])
    # my_reverse_daterange_value: daterange = MaltegoEntityField(sample_value=daterange(datetime.date.today(), datetime.date.today().replace(year=1999)))  # this breaks (intentionally!)

    property_name: str = MaltegoEntityProperty(name="property.name", value="Foo")
    _private_member: str = MaltegoEntityProperty(name="private_member", value="Foo")


class RichEntityChild(RichEntity):
    TYPE_NAME = "maltego.RichEntityChild"
    my_other_int_value: int = 42


class PhraseTest(Phrase):
    pass


def entity_of_type(type_name: str) -> Any:
    mock_transform_run_request_v3 = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {type_name: 1},
                "entitiesTotalCount": 1,
                "linksTotalCount": 0,
                "rootEntitiesCount": 0,
            },
            "graph": {
                "entities": [
                    {
                        "id": "0",
                        "value": "Foo",
                        "iconUrl": "str",
                        "weight": 100,
                        "properties": [],
                        "displayInformation": [],
                        "type": type_name,
                        "bookmark": None,
                    }
                ],
                "links": [],
            },
        },
        "limit": 12,
        "transformSettings": [],
    }
    return mock_transform_run_request_v3


@pytest.fixture
def every_type_entity() -> RichEntity:
    return RichEntity("test")


@pytest.fixture
def mock_server_settings_reverse() -> MaltegoServerSettings:
    return MaltegoServerSettings(
        server_name="",
        ns="osotlam",
        author="osotlam",
        owner="osotlam",
        version="9.9",
    )


@pytest.fixture
def mock_server_non_defaults() -> MaltegoTransformServer:  # type: ignore
    mock_server_settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix=PREFIX,
        full_host_url="https://maltoso.com/",
    )

    mock_server = MaltegoTransformServer(settings=mock_server_settings)
    mock_server.setup(mock_server_settings)
    yield mock_server
    mock_server.runner.shutdown()


@pytest.fixture
def mock_server_custom_prefix() -> MaltegoTransformServer:
    mock_server_settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        transform_prefix=True,
        transform_app_name_prefix="APPPREFIX",
        transform_display_name_prefix="DNPREFIX",
        transform_name_prefix="NAMEPREFIX",
    )

    mock_server = MaltegoTransformServer(settings=mock_server_settings)

    @mock_server.register_transform(
        display_name="Test", name="Test", description="test", transform_set="pytest"
    )
    # type: ignore
    async def mock_transform_custom_prefix_server(
        input_entity: Phrase, settings
    ) -> Phrase:
        return Phrase("Test")

    mock_server.setup(mock_server_settings)
    yield mock_server
    mock_server.runner.shutdown()


@pytest.fixture
def mock_server() -> MaltegoTransformServer:  # type: ignore
    mock_server_settings = MaltegoServerSettings(
        server_name=NAMESPACE,
        ns=NAMESPACE,
        author=NAMESPACE,
        api_prefix=PREFIX,
        full_host_url="https://maltoso.com/",
        # swagger_enabled defaults to False (PR 27696); this shared fixture is used
        # by tests that assert /openapi.json and /swagger are reachable, so opt in
        # explicitly to preserve pre-merge behavior for this fixture.
        swagger_enabled=True,
    )

    mock_server = MaltegoTransformServer(settings=mock_server_settings)

    # mock_server = maltego.server._server
    # mock_server.v2server.set_prefix(PREFIX)
    # mock_server.set_settings(mock_server_settings)

    @mock_server.register_transform(
        display_name="Test", name="Test", description="test", transform_set="pytest"
    )
    # type: ignore
    async def mock_transform_default(input_entity: Phrase, settings) -> Phrase:
        return Phrase("Test")

    @mock_server.register_transform(
        display_name="TestSetting",
        name="TestSetting",
        description="test",
        settings=[
            TransformSetting(
                name="Test", display_name="Test", type=TransformSetting.Types.int
            )
        ],
        transform_set="pytest",
    )
    # type: ignore
    async def mock_transform_settings(input_entity: Phrase, settings) -> Phrase:
        return Phrase("Test")

    @mock_server.register_transform(transform_set="pytest")
    async def dummy_transform_1_args(input_entity: Phrase) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    # type: ignore
    async def dummy_transform_2_args(input_entity: Phrase, settings) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    # type: ignore
    async def dummy_transform_3_args(
        input_entity: Phrase, settings, limit
    ) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    # type: ignore
    async def dummy_transform_4_args(
        input_entity: Phrase, settings, limit, context
    ) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    # type: ignore
    async def dummy_transform_4_args_slider(
        input_entity: Phrase, settings, slider, context
    ) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    async def dummy_transform_5_default_arg(
        input_entity: Phrase, foo: int = "foo"
    ) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    async def dummy_transform_6_default_arg(  # type: ignore
        input_entity: Phrase,
        settings,
        slider,
        context,
        foo: int = "foo",  # type: ignore
    ) -> List[Person]:
        return []

    @mock_server.register_transform(transform_set="pytest")
    # type: ignore
    async def dummy_transform_7_kwargs(
        input_entity: Phrase, settings, slider, context, **kwargs
    ) -> List[Person]:
        return []

    with pytest.raises(ValueError):

        @mock_server.register_transform(transform_set="pytest")  # type: ignore
        async def dummy_transform_incorrect_args_annotation(
            input_entity: Phrase,
            settings,
            slider,
            context,
            invalid_arg: float,
            **kwargs,
        ) -> List[Person]:
            return []

    with pytest.raises(ValueError):

        @mock_server.register_transform(transform_set="pytest")
        async def dummy_transform_incorrect_args_name(  # type: ignore
            input_entity: Phrase, settings, limit, invalid_arg
        ) -> List[Person]:
            return []

    @mock_server.register_transform(
        name="TestRegisterTransform",
        display_name="Only used for testing registration",
        description="Description",
        settings=[
            TransformSetting(
                name="suffix",
                display_name="Suffix",
                optional=False,
                type="string",
                auth=False,
                popup=True,
                default_value=None,
            ),
            TransformSetting(
                name="suffix2",
                display_name="Suffix",
                optional=False,
                type="string",
                auth=False,
                popup=True,
                default_value=None,
            ),
        ],
        version="0.0.2",
        transform_set="pytest",
    )
    async def dummy_transform_decorator(  # type: ignore
        input_entity: Phrase, settings, limit: int
    ) -> Phrase:
        return Phrase("Happy Testing")

    @mock_server.register_transform(
        name="TestNoneTypeHint", display_name="TestNoneTypeHint", transform_set="pytest"
    )
    async def dummy_transform_decorator_optional(  # type: ignore
        input_entity: Phrase, settings, limit: int
    ) -> Optional[Phrase]:
        return Phrase("Happy Testing")

    @mock_server.register_transform(
        name="TestUnionTypeHint",
        display_name="TestUnionTypeHint",
        transform_set="pytest",
    )
    async def dummy_transform_decorator_union(
        input_entity: Union[MaltegoEntity[str("maltego.Phrase")], Person],
        settings,
        limit: int,
    ) -> Optional[Phrase]:
        return Phrase("Happy Testing")

    mock_server.register_entity(PhraseTest)
    mock_server.register_entity(RichEntity)
    mock_server.register_machine(TestMachine)

    mock_server.setup(mock_server_settings)
    mock_server.runner.startup()
    if isinstance(mock_server.runner, ThreadedTransformRunner):
        assert len(mock_server.runner.loops) == 1
    yield mock_server
    mock_server.runner.shutdown()


def reload(mod_name: str) -> None:
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    module = importlib.import_module(mod_name)
    if hasattr(module, "TEST_RUN"):
        setattr(module, "TEST_RUN", True)


def reload_example() -> None:
    reload("tests.example.transforms.entities.entities")
    reload("tests.example.transforms.entities.composite_entities")
    reload("tests.example.transforms.entities.coalesce_test_entities")
    reload("tests.example.transforms.transforms")
    reload("tests.example.transforms.machines.machines")
    reload("tests.example.transforms.sets.sets")
    reload("tests.example.transforms.prompts")
    reload("tests.example.transforms.property_constraints")
    reload("tests.example.transforms.entity_typed_properties")


@pytest.fixture(scope="session")
def mock_server_example() -> MaltegoTransformServer:  # type: ignore
    mock_server_settings = MaltegoServerSettings(
        server_name="Maltego Test Transform Server",
        ns=NAMESPACE,
        author="author@example.com",
        owner="Maltego Technologies GmbH",
        version="1.2.3",
        transform_prefix=True,
        transform_app_name_prefix="Pytest ",
        transform_display_name_prefix="Pytest ",
        transform_name_prefix=PREFIX,
        entity_config_overrides=EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.nonRootEntity"],
                    clients=["desktop"],
                    overrides={"allowed_root": True}
                ),
                # Override coalesce field default_value for old desktop clients
                # Only CoalescingDisplayPropertyEntity has override - to test that override removes coalesce
                # AtomicCoalesceTestEntity has NO override - to test that coalesce filtering works
                EntityConfigOverride(
                    entities=["maltego.CoalescingDisplayPropertyEntity"],
                    clients=["desktop"],
                    overrides={"fields.display_property.default_value": "$property(name)"}
                ),
            ]
        ),
    )

    mock_server = MaltegoTransformServer(
        settings=mock_server_settings,
    )
    maltego.server._server.runner.shutdown()
    setattr(maltego.server, "_server", mock_server)
    setattr(maltego.server, "register_transform", mock_server.register_transform)
    setattr(maltego.server, "register_entity", mock_server.register_entity)
    setattr(
        maltego.server, "register_transform_set", mock_server.register_transform_set
    )
    setattr(maltego.server, "register_machine", mock_server.register_machine)
    setattr(maltego.server, "register_icon", mock_server.register_icon)

    reload_example()

    mock_server.setup(mock_server_settings)
    assert mock_server.v3server
    assert mock_server.v3server.transforms
    mock_server.runner.startup()
    if isinstance(mock_server.runner, ThreadedTransformRunner):
        assert len(mock_server.runner.loops) == 1
    yield mock_server
    mock_server.runner.shutdown()


@pytest.fixture
def async_client_mock_server(mock_server: MaltegoTransformServer) -> httpx.AsyncClient:
    client = httpx.AsyncClient(app=mock_server.app, base_url="http://test")
    return client


@pytest.fixture
def async_client_example_server(
    mock_server_example: MaltegoTransformServer,
) -> httpx.AsyncClient:
    client = httpx.AsyncClient(app=mock_server_example.app, base_url="http://test")
    return client


@pytest.fixture
def mock_transform_middleware_test_transform() -> MaltegoTransform:
    def mock_transform_middleware_test(
        input_entity: Phrase, settings, limit: int
    ) -> Phrase:
        return Phrase("")

    return MaltegoTransform(
        impl=mock_transform_middleware_test,
        name="",
        description="",
        display_name="",
        author="",
        location_relevance="",
        owner="",
        settings=[],
        transform_set="",
        transform_ns="maltoso",
    )


@pytest.fixture()
def mock_context() -> MaltegoContext:
    mock_request = MagicMock()
    mock_request.headers = {}
    return MaltegoContext(MaltegoGraph(), mock_request)  # type: ignore


@pytest.fixture(scope="session")
def dummy_tx_args() -> Any:
    return {
        "name": "",
        "display_name": "",
        "description": "",
        "author": "",
        "location_relevance": "",
        "settings": [],
        "transform_ns": "",
    }


@pytest.fixture()
def transform_input() -> Any:
    mock_request = MagicMock()
    mock_request.headers = {}
    return (
        Phrase("Some text"),
        {"a": 12},
        12,
        MaltegoContext(
            MaltegoGraph(),
            mock_request,  # type: ignore
            remote_ip="127.0.0.1",
            api_key="foo",
        ),
    )


@pytest.fixture(scope="session")
def example_graph() -> MaltegoGraph[Any]:
    data = None
    with open("src/tests/resources/graph_request.json", encoding="utf-8") as file:
        data = file.read()
    assert data
    request_dict = json.loads(data)
    transform_run_request = TransformRunRequest.model_validate(request_dict)
    entities = [
        MaltegoEntity.from_v3_run_entity(entity)
        for entity in transform_run_request.input.graph.entities
    ]
    links = [
        MaltegoLink.from_v3_run_link(link)
        for link in transform_run_request.input.graph.links
    ]
    graph: MaltegoGraph[Any] = MaltegoGraph(entities=entities, links=links)
    return graph


@pytest.fixture()
def transform_result_set() -> TransformResultSet:
    mock_request = MagicMock()
    mock_request.headers = {}
    context = MaltegoContext(MaltegoGraph(), mock_request)
    return TransformResultSet(context)


@pytest.fixture(scope="session")
def runner():  # type: ignore
    RUNNER = ThreadedTransformRunner([], 600, 600)
    RUNNER.startup()
    yield RUNNER
    RUNNER.shutdown()


def pytest_sessionfinish() -> None:
    maltego.server._server.runner.shutdown()  # pylint: disable
