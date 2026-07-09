import importlib.util

import pytest

import maltego.server

pytestmark = pytest.mark.packaging


def test_default_sdk_does_not_package_maltego_trx_namespace() -> None:
    assert importlib.util.find_spec("maltego_trx") is None


def test_default_sdk_does_not_package_classic_protocol_modules() -> None:
    assert importlib.util.find_spec("maltego.server.trx") is None
    assert importlib.util.find_spec("maltego.server.v2") is None
    assert not hasattr(maltego.server, "TrxTransformRegistry")
    assert not hasattr(maltego.server, "DiscoverableTransform")
