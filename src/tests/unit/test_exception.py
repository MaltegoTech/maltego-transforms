import pytest

from maltego.model.exception import MaltegoHTTPTransformNotFound

pytestmark = pytest.mark.unit


def test_classic_status_code_preserves_v2_status_code_alias() -> None:
    exc = MaltegoHTTPTransformNotFound()

    assert exc.classic_status_code == 241
    assert getattr(exc, "v2_status_code", None) == exc.classic_status_code
