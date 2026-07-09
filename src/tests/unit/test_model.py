# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Dict, List, Optional
from datetime import datetime, date, timezone
import pytest
from tests.conftest import Phrase

from maltego.model.transform import MaltegoTransform, MaltegoContext
from maltego.model.transform.setting import TransformSetting
from maltego.model.types import daterange

pytestmark = pytest.mark.unit


async def dummy_transform_no_out_args(input_entity: Phrase):
    assert isinstance(input_entity, Phrase)
    return [input_entity, Phrase(None), Phrase(None), Phrase(None)]


async def dummy_transform_1_args(input_entity: Phrase) -> List[Optional[Phrase]]:
    assert isinstance(input_entity, Phrase)
    return [input_entity, Phrase(None), Phrase(None), Phrase(None)]


async def dummy_transform_2_args(input_entity: Phrase, settings: Dict[str, Any]) -> List[Optional[Phrase]]:
    assert isinstance(input_entity, Phrase)
    assert isinstance(settings, dict)

    return [input_entity, Phrase(str(settings)), Phrase(None), Phrase(None)]


async def dummy_transform_3_args(input_entity: Phrase, settings, limit: int) -> List[Optional[Phrase]]:
    assert isinstance(input_entity, Phrase)
    assert isinstance(limit, int)
    assert isinstance(settings, dict)

    return [input_entity, Phrase(str(settings)), Phrase(None), Phrase(str(limit))]


async def dummy_transform_4_args(input_entity: Phrase, settings, limit, context: MaltegoContext) -> List[Phrase]:
    assert isinstance(input_entity, Phrase)
    assert isinstance(context, MaltegoContext)
    assert isinstance(limit, int)
    assert isinstance(settings, dict)

    return [input_entity, Phrase(str(settings)), Phrase(str(context.remote_ip)), Phrase(str(limit))]


async def dummy_transform_4_args_slider(input_entity: Phrase, settings, slider, context) -> List[Phrase]:
    assert isinstance(input_entity, Phrase)
    assert isinstance(context, MaltegoContext)
    assert isinstance(slider, int)
    assert isinstance(settings, dict)

    return [input_entity, Phrase(str(settings)), Phrase(str(context.remote_ip)), Phrase(str(slider))]


async def dummy_transform_4_reversed(input_entity: Phrase, context, slider, settings) -> List[Phrase]:
    assert isinstance(input_entity, Phrase)
    assert isinstance(context, MaltegoContext)
    assert isinstance(slider, int)
    assert isinstance(settings, dict)

    return [input_entity, Phrase(str(settings)), Phrase(str(context.remote_ip)), Phrase(str(slider))]


async def dummy_transform_4_annotation(
    arg1: Phrase,
    arg2: MaltegoContext,
    arg3: int,
    arg4: Dict[str, Any]
) -> List[Phrase]:
    assert isinstance(arg1, Phrase)
    assert isinstance(arg2, MaltegoContext)
    assert isinstance(arg3, int)
    assert isinstance(arg4, dict)
    return [arg1, Phrase(str(arg4)), Phrase(str(arg2.remote_ip)), Phrase(str(arg3))]


async def dummy_transform_incorrect_args(input_entity: Phrase, settings, limit, invalid_arg) -> List[Phrase]:
    assert input_entity
    assert settings
    assert limit
    assert invalid_arg
    assert False


async def dummy_transform_double_args_1(input_entity: Phrase, settings, limit, slider) -> List[Phrase]:
    assert input_entity
    assert settings
    assert limit
    assert slider
    assert False


async def dummy_transform_double_args_2(input_entity: Phrase, settings, limit, invalid_arg: int) -> List[Phrase]:
    assert input_entity
    assert settings
    assert limit
    assert invalid_arg
    assert False


async def dummy_transform_0_args():
    assert False


def test_settings_instantiation():
    # Given a valid property type
    # Then no exception is thrown
    TransformSetting(name="test", display_name="Test", type="daterange")

    # Given a valid property enum
    # Then no exception is thrown
    TransformSetting(name="test", display_name="Test",
                     type=TransformSetting.Types.int)

    # Given an invalid property type
    # Then a ValueError exception is thrown
    with pytest.raises(ValueError):
        TransformSetting(name="test", display_name="Test", type="invalid")


@pytest.mark.asyncio
async def test_transform_interface_no_out_annotation(dummy_tx_args, transform_input, runner):
    # Given a transform with 1 arg, When getting the transform config
    transform = MaltegoTransform(dummy_transform_no_out_args, **dummy_tx_args)
    # Then the correct config is returned
    assert transform.annotation.output.annotation is None
    assert transform.annotation.context_param is None
    assert transform.annotation.slider_param is None
    assert transform.annotation.settings_param is None
    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value is None
    assert result[2].value is None
    assert result[3].value is None


@pytest.mark.asyncio
async def test_transform_interface_single_input_entity(dummy_tx_args, transform_input, runner):
    # Given a transform with 1 arg, When getting the transform config
    transform = MaltegoTransform(dummy_transform_1_args, **dummy_tx_args)
    # Then the correct config is returned
    assert transform.annotation.context_param is None
    assert transform.annotation.slider_param is None
    assert transform.annotation.settings_param is None

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value is None
    assert result[2].value is None
    assert result[3].value is None


@pytest.mark.asyncio
async def test_transform_interface_with_setting(dummy_tx_args, transform_input, runner):
    # Given a transform with 2 args, When getting the transform config
    transform = MaltegoTransform(dummy_transform_2_args, **dummy_tx_args)
    # Then the correct args are returned
    assert transform.annotation.context_param is None
    assert transform.annotation.slider_param is None
    assert transform.annotation.settings_param == "settings"

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value is None
    assert result[3].value is None


@pytest.mark.asyncio
async def test_transform_interface_with_settings_limit(dummy_tx_args, transform_input, runner):
    # Given a transform with 3 args, When getting the transform config
    transform = MaltegoTransform(dummy_transform_3_args, **dummy_tx_args)
    # Then the correct args are returned
    assert transform.annotation.context_param is None
    assert transform.annotation.slider_param == "limit"
    assert transform.annotation.settings_param == "settings"

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value is None
    assert result[3].value == str(transform_input[2])


@pytest.mark.asyncio
async def test_transform_interface_with_context_limit_settings(dummy_tx_args, transform_input, runner):
    # Given a transform with 4 args, When getting the transform config
    transform = MaltegoTransform(dummy_transform_4_args, **dummy_tx_args)
    # Then the correct args are returned
    assert transform.annotation.context_param == "context"
    assert transform.annotation.slider_param == "limit"
    assert transform.annotation.settings_param == "settings"

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value == transform_input[3].remote_ip
    assert result[3].value == str(transform_input[2])


@pytest.mark.asyncio
async def test_transform_interface_with_context_slider_settings(dummy_tx_args, transform_input, runner):
    # Given a transform with 4 args and 'slider' instead of a 'limit', When getting the transform config
    transform = MaltegoTransform(
        dummy_transform_4_args_slider, **dummy_tx_args)
    # Then the correct args are returned
    assert transform.annotation.context_param == "context"
    assert transform.annotation.slider_param == "slider"
    assert transform.annotation.settings_param == "settings"

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value == transform_input[3].remote_ip
    assert result[3].value == str(transform_input[2])


@pytest.mark.asyncio
async def test_transform_interface_ordering(dummy_tx_args, transform_input, runner):
    # Given a transform with 4 args and ordering mixed, When getting the transform config
    transform = MaltegoTransform(dummy_transform_4_reversed, **dummy_tx_args)
    # Then the correct args are returned
    assert transform.annotation.context_param == "context"
    assert transform.annotation.slider_param == "slider"
    assert transform.annotation.settings_param == "settings"

    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value == transform_input[3].remote_ip
    assert result[3].value == str(transform_input[2])


@pytest.mark.asyncio
async def test_transform_interface_annotation_vs_naming(dummy_tx_args, transform_input, runner):
    # Given a transform with 4 args with non standard names, When getting the transform config
    transform = MaltegoTransform(dummy_transform_4_annotation, **dummy_tx_args)
    assert transform.annotation.context_param == "arg2"
    assert transform.annotation.slider_param == "arg3"
    assert transform.annotation.settings_param == "arg4"
    run_id = runner.schedule_transform(transform, *transform_input)
    await runner.run(run_id)

    result = runner.output_entities(run_id)
    assert result
    assert len(result) == 4
    assert result[0] == transform_input[0]
    assert result[1].value == str(transform_input[1])
    assert result[2].value == transform_input[3].remote_ip
    assert result[3].value == str(transform_input[2])


def test_transform_interface_invalid_arg(dummy_tx_args):
    # Given a transform with invalid arguments, When getting the transform config
    with pytest.raises(ValueError):
        MaltegoTransform(dummy_transform_incorrect_args, **dummy_tx_args)


def test_transform_interface_double_arg(dummy_tx_args):
    # Given a transform with slider arguments set twice, When getting the transform config
    with pytest.raises(ValueError):
        MaltegoTransform(dummy_transform_double_args_1, **dummy_tx_args)


def test_transform_interface_double_arg_by_annotation(dummy_tx_args):
    # Given a transform with slider arguments set twice (one by name one by int annotation),
    # When getting the transform config
    with pytest.raises(ValueError):
        MaltegoTransform(dummy_transform_double_args_2, **dummy_tx_args)


def test_transform_interface_no_arg(dummy_tx_args):
    # Given a transform with no args, When getting the transform config
    with pytest.raises(ValueError):
        MaltegoTransform(dummy_transform_0_args, **dummy_tx_args)
    # Then a ValueError is raised


def test_prepare_tf_input_args():
    # Given a valid transform args config
    # When preparing transforms settings
    transform_input = Phrase("Some text"), {"a": 12}, None, 12
    args = {
        "name": "",
        "display_name": "",
        "description": "",
        "author": "",
        "location_relevance": "",
        "settings": [],
        "transform_ns": "",
    }
    transform = MaltegoTransform(dummy_transform_4_annotation, **args)

    tf_settings = transform.prepare_tf_input_args(*transform_input)
    # Then the correct settings are returned
    assert tf_settings["arg3"] == 12

    # Given a valid transform args config
    # When preparing transforms settings
    tf_settings = transform.prepare_tf_input_args(*transform_input)
    # Then the correct settings are returned
    assert tf_settings["arg3"] == 12
    assert len(tf_settings) == 4


def test_prepare_settings():
    def test(input_entity):
        assert input_entity

    # If settings is not a List except ValueError
    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=test,
            name="MaltegoTransform",
            display_name="MaltegoTransform",
            description="MaltegoTransform",
            author="pytest",
            location_relevance=None,
            transform_ns="pytest",
            settings={},
        )

    mock_transforms = MaltegoTransform(
        impl=test,
        name="MaltegoTransform",
        display_name="MaltegoTransform",
        description="MaltegoTransform",
        author="pytest",
        location_relevance=None,
        transform_ns="pytest",
        settings=[
            TransformSetting(
                name='int', display_name='int', type='int'
            ),
            TransformSetting(
                name='int_list', display_name='int_list', type=TransformSetting.Types.int_list
            ),
            TransformSetting(
                name='datetime', display_name='datetime', type=TransformSetting.Types.datetime
            ),
            TransformSetting(
                name='date_list', display_name='date_list', type=TransformSetting.Types.date_list
            )
        ],
    )

    # If input value is an empty list expect output value is None
    prepared_settings = mock_transforms.prepare_settings(
        proto_settings_raw={},
        transform=mock_transforms
    )
    assert (prepared_settings.keys()) == {
        "int", "int_list", "datetime", "date_list"}
    assert list(prepared_settings.values())[0] is None
    assert list(prepared_settings.values())[1] is None
    assert list(prepared_settings.values())[2] is None
    assert list(prepared_settings.values())[3] is None

    # Test valid inputs
    prepared_settings = mock_transforms.prepare_settings(
        proto_settings_raw={
            'int': 42,
            'int_list': [0, 1, 2],
            'datetime': "1992-05-21T00:00:00.000Z",
            'date_list': ['1992-05-21', "2023-06-28"],
        },
        transform=mock_transforms
    )
    assert (prepared_settings.keys()) == {
        "int", "int_list", "datetime", "date_list"}
    assert isinstance(list(prepared_settings.values())[0], int)
    assert list(prepared_settings.values())[0] == 42
    assert list(prepared_settings.values())[1] == [0, 1, 2]
    assert list(prepared_settings.values())[2] == datetime(
        year=1992, month=5, day=21, hour=0, minute=0, second=0, tzinfo=timezone.utc
    )
    assert list(prepared_settings.values())[3] == [
        date(year=1992, month=5, day=21), date(year=2023, month=6, day=28)
    ]

    # Test invalid inputs
    prepared_settings = mock_transforms.prepare_settings(
        proto_settings_raw={
            'int': "foo",
            'int_list': [0, "bar", "baz"],
            'datetime': "foo",
            'date_list': ['foo', "bar"],
        },
        transform=mock_transforms
    )
    assert (prepared_settings.keys()) == {
        "int", "int_list", "datetime", "date_list"}
    assert list(prepared_settings.values())[0] is None
    assert list(prepared_settings.values())[1] == [0]
    assert list(prepared_settings.values())[2] is None
    assert list(prepared_settings.values())[3] == [
    ]

    # Test invalid input types
    prepared_settings = mock_transforms.prepare_settings(
        proto_settings_raw={
            'int': "42",
            'int_list': [0, "1", "2"],
            'datetime': 1,
            'date_list': [0, 1],
        },
        transform=mock_transforms
    )
    assert (prepared_settings.keys()) == {
        "int", "int_list", "datetime", "date_list"}
    assert isinstance(list(prepared_settings.values())[0], int)
    assert list(prepared_settings.values())[0] == 42
    assert list(prepared_settings.values())[1] == [0, 1, 2]
    assert list(prepared_settings.values())[2] is None
    assert list(prepared_settings.values())[3] == [
    ]


def test_boolean_list_parse():
    def test(input_entity):
        assert input_entity

    # If settings is not a List except ValueError
    with pytest.raises(ValueError):
        MaltegoTransform(
            impl=test,
            name="MaltegoTransform",
            display_name="MaltegoTransform",
            description="MaltegoTransform",
            author="pytest",
            location_relevance=None,
            transform_ns="pytest",
            settings={},
        )

    mock_transforms = MaltegoTransform(
        impl=test,
        name="MaltegoTransform",
        display_name="MaltegoTransform",
        description="MaltegoTransform",
        author="pytest",
        location_relevance=None,
        transform_ns="pytest",
        settings=[
            TransformSetting(
                name='boolean_list', display_name='boolean_list', type=TransformSetting.Types.boolean_list
            ),
        ],
    )

    prepared_settings = mock_transforms.prepare_settings(
        proto_settings_raw={
            'boolean_list': [True, False, "foo", 0, 22],
        },
        transform=mock_transforms
    )
    assert (prepared_settings.keys()) == {"boolean_list"}
    assert isinstance(list(prepared_settings.values())[0], list)
    assert list(prepared_settings.values())[0] == [
        True, False, True, False, True]


def test_empty_string_handling_v3():
    """Test empty string handling for V3 protocol."""
    assert TransformSetting(name='t', display_name='t', type=TransformSetting.Types.boolean).transform_setting_from_blueprint("") is None
    assert TransformSetting(name='t', display_name='t', type=TransformSetting.Types.int).transform_setting_from_blueprint("") is None
    assert TransformSetting(name='t', display_name='t', type=TransformSetting.Types.datetime_range).transform_setting_from_blueprint("") is None

    assert TransformSetting(name='t', display_name='t', type=TransformSetting.Types.str).transform_setting_from_blueprint("") == ""

    # Empty string raises ValueError for list types (type mismatch)
    with pytest.raises(ValueError):
        TransformSetting(name='t', display_name='t', type=TransformSetting.Types.int_list).transform_setting_from_blueprint("")


def test_daterange_str_uses_current_wire_format() -> None:
    value = daterange(
        start=datetime(1992, 5, 21, tzinfo=timezone.utc),
        end=datetime(2023, 6, 28, tzinfo=timezone.utc),
    )

    assert str(value) == "1992-05-21T00:00:00.000Z/2023-06-28T00:00:00.000Z"
