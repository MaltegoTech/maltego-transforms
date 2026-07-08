# Copyright (c) Maltego Technologies GmbH.
from typing import Dict, Any

import pytest

from maltego.server import MaltegoTransform, MaltegoEntity, MaltegoContext, MaltegoGraph

pytestmark = pytest.mark.unit


class Foo:
    pass


def test_invalid_input_annotation():
    def transform(input: Foo) -> None:
        pass

    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=transform,
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


def test_invalid_output_annotation():

    def transform(input: MaltegoEntity) -> Foo:
        pass

    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=transform,
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


def test_duplicate_context_annotation():

    def transform(input: MaltegoEntity, context: MaltegoContext, foo: MaltegoContext) -> None:
        pass

    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=transform,
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


def test_duplicate_setting_annotation():

    def transform(input: MaltegoEntity, settings, foo: Dict[str, Any]) -> None:
        pass

    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=transform,
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


def test_graph_payload_annotation():

    def transform(input: MaltegoGraph) -> None:
        pass

    tx = MaltegoTransform(
        impl=transform,
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
    assert tx.annotation.uses_graph_payload()


def test_entity_payload_annotation():

    def transform(input: MaltegoEntity) -> None:
        pass

    tx = MaltegoTransform(
        impl=transform,
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

    assert not tx.annotation.uses_graph_payload()
    assert tx.__repr__() == ""


def test_missing_input_annotation():

    def transform() -> None:
        pass

    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=transform,
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
