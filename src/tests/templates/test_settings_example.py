# Copyright (c) Maltego Technologies GmbH.
"""
Smoke tests for the transform_settings_example.py template.

Verifies:
  - The module compiles without syntax errors.
  - All TransformSetting instances are constructed without errors.
  - All setting types are represented.
  - Global, required/optional, and popup/persistent patterns are present.
  - The scaffolder copies the file into a generated project and it imports cleanly.
"""
import importlib.util
import py_compile
import subprocess
import sys
import types
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import maltego._cli as cli
from maltego.model.transform.setting import TransformSetting
from maltego.model.types import daterange

pytestmark = pytest.mark.template

TEMPLATE_FILE = (
    Path(__file__).resolve().parents[3]
    / "src/maltego/template_dir/transforms/transform_settings_example.py"
)


# ---------------------------------------------------------------------------
# Unit-level smoke: import the template module directly
# ---------------------------------------------------------------------------

def _load_template_module():
    """Import transform_settings_example from the template_dir as a module."""
    src_dir = Path(__file__).resolve().parents[2]

    # Reuse the Phrase already registered by conftest (or the existing maltego.entities
    # stub) so we don't hit "Entity Phrase already exists in registry".
    if "maltego.entities" not in sys.modules:
        from maltego.model.entity import MaltegoEntity, MaltegoEntityConfig
        from maltego.model.entity.property import MaltegoEntityProperty as MEF

        # conftest defines Phrase; reuse it from the tests package if available
        try:
            from tests.conftest import Phrase  # type: ignore[import]
        except ImportError:
            class Phrase(MaltegoEntity):  # type: ignore[no-redef]
                TYPE_NAME = "maltego.Phrase"
                Config = MaltegoEntityConfig(
                    value_property="value", display_name="Phrase"
                )
                value: str = MEF(name="value", display_name="Value", value="")

        entities_stub = types.ModuleType("maltego.entities")
        entities_stub.Phrase = Phrase
        sys.modules["maltego.entities"] = entities_stub

    original_path = list(sys.path)
    # template_dir needs its own "transforms" package on sys.path
    template_dir = TEMPLATE_FILE.parent.parent
    sys.path[:0] = [str(template_dir), str(src_dir)]
    try:
        # Use a unique module name to avoid caching collisions in repeated test runs
        mod_name = f"_tse_smoke_{id(TEMPLATE_FILE)}"
        spec = importlib.util.spec_from_file_location(mod_name, TEMPLATE_FILE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_path


def test_template_settings_example_file_exists():
    assert TEMPLATE_FILE.is_file(), f"Expected template at {TEMPLATE_FILE}"


def test_template_settings_example_compiles():
    """py_compile catches syntax errors without executing the module."""
    py_compile.compile(str(TEMPLATE_FILE), doraise=True)


def test_template_settings_example_imports_without_error():
    """Full import of the template: registers transforms, instantiates settings."""
    mod = _load_template_module()
    # Module-level constant should be a TransformSetting
    assert hasattr(mod, "GLOBAL_API_KEY")
    assert isinstance(mod.GLOBAL_API_KEY, TransformSetting)


# ---------------------------------------------------------------------------
# Validate all setting types are instantiable
# ---------------------------------------------------------------------------

ALL_SETTING_TYPES = [
    (TransformSetting.Types.str,          str,            "default text"),
    (TransformSetting.Types.int,          int,            42),
    (TransformSetting.Types.float,        float,          3.14),
    (TransformSetting.Types.boolean,      bool,           True),
    (TransformSetting.Types.date,         date,           date(2024, 1, 1)),
    (TransformSetting.Types.datetime,     datetime,       datetime(2024, 1, 1, tzinfo=timezone.utc)),
    (TransformSetting.Types.datetime_range, daterange,    daterange(date_range=daterange.Ranges.last_7_days)),
    (TransformSetting.Types.str_list,     list,           ["a", "b"]),
    (TransformSetting.Types.int_list,     list,           [1, 2]),
    (TransformSetting.Types.float_list,   list,           [1.0, 2.0]),
    (TransformSetting.Types.boolean_list, list,           [True, False]),
    (TransformSetting.Types.date_list,    list,           [date(2024, 1, 1)]),
]


@pytest.mark.parametrize("setting_type,python_type,default_value", ALL_SETTING_TYPES)
def test_all_setting_types_instantiate(setting_type, python_type, default_value):
    """Each of the TransformSetting.Types can be constructed without error."""
    setting = TransformSetting(
        name=f"test_{setting_type.name}",
        display_name=f"Test {setting_type.name}",
        type=setting_type,
        default_value=default_value,
        optional=True,
        popup=False,
    )
    assert setting.type == setting_type
    assert setting.default_value is not None


def test_setting_type_count():
    """Confirm there are exactly 12 non-auth named enum members (auth is a flag, not a type)."""
    # datetime_range is the 7th type; all list variants bring it to 12
    types_count = len(TransformSetting.Types)
    assert types_count == 12, (
        f"Expected 12 TransformSetting.Types members, got {types_count}. "
        "Update this test if the SDK adds new types."
    )


# ---------------------------------------------------------------------------
# Required vs optional
# ---------------------------------------------------------------------------

def test_optional_setting_default_is_true():
    setting = TransformSetting(name="opt", display_name="Opt", optional=True)
    assert setting.optional is True


def test_required_setting():
    setting = TransformSetting(name="req", display_name="Req", optional=False)
    assert setting.optional is False


# ---------------------------------------------------------------------------
# Popup vs persistent
# ---------------------------------------------------------------------------

def test_popup_setting():
    setting = TransformSetting(name="popup", display_name="Popup", popup=True)
    assert setting.popup is True


def test_persistent_setting():
    setting = TransformSetting(name="persist", display_name="Persist", popup=False)
    assert setting.popup is False


# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

def test_global_setting_is_global_flag():
    setting = TransformSetting(
        name="api_key",
        display_name="API Key",
        is_global=True,
    )
    assert setting.is_global is True
    # name is serialized with global# prefix
    assert setting.serialize_name(ns="acme", transform_name="tx") == "global#acme.api_key"


def test_is_global_setting_deprecated_warns():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        setting = TransformSetting(
            name="workspace",
            display_name="Workspace",
            is_global_setting=True,
        )
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "is_global_setting is deprecated" in str(w[0].message)
    assert setting.is_global_setting is True


# ---------------------------------------------------------------------------
# Absolute daterange
# ---------------------------------------------------------------------------

def test_absolute_daterange_setting():
    dr = daterange(start=date(2024, 1, 1), end=date(2024, 3, 31))
    setting = TransformSetting(
        name="abs_range",
        display_name="Absolute Range",
        type=TransformSetting.Types.datetime_range,
        default_value=dr,
    )
    assert setting.default_value is not None
    assert isinstance(setting.default_value, daterange)
    assert setting.default_value.range is None  # absolute, not relative


def test_relative_daterange_setting():
    dr = daterange(date_range=daterange.Ranges.last_30_days)
    setting = TransformSetting(
        name="rel_range",
        display_name="Relative Range",
        type=TransformSetting.Types.datetime_range,
        default_value=dr,
    )
    assert isinstance(setting.default_value, daterange)
    assert setting.default_value.range == daterange.Ranges.last_30_days


# ---------------------------------------------------------------------------
# Auth flag
# ---------------------------------------------------------------------------

def test_auth_setting():
    setting = TransformSetting(
        name="api_token",
        display_name="API Token",
        auth=True,
        optional=False,
        popup=True,
    )
    assert setting.auth is True
    assert setting.optional is False
    assert setting.popup is True


# ---------------------------------------------------------------------------
# Scaffolder: generated demo project includes the settings example
# ---------------------------------------------------------------------------

def test_scaffolder_copies_settings_example(tmp_path, monkeypatch):
    """``maltego-transforms start`` should copy transform_settings_example.py."""
    monkeypatch.chdir(tmp_path)
    cli.run_start(["demo_project"])

    project_dir = tmp_path / "demo_project"
    settings_file = project_dir / "transforms" / "transform_settings_example.py"
    assert settings_file.is_file(), (
        "transform_settings_example.py was not copied by the scaffolder"
    )
    # The project.py should import it
    project_py = (project_dir / "project.py").read_text()
    assert "transform_settings_example" in project_py


def test_scaffolder_generated_project_imports_settings_example(tmp_path, monkeypatch):
    """The generated project containing the settings example imports cleanly."""
    monkeypatch.chdir(tmp_path)
    cli.run_start(["demo_project"])

    project_dir = tmp_path / "demo_project"
    src_dir = Path(__file__).resolve().parents[2]

    code = f"""
import importlib.util
import sys
import types

sys.path[:0] = [{str(project_dir)!r}, {str(src_dir)!r}]

from maltego.model.entity import MaltegoEntity, MaltegoEntityConfig
from maltego.model.entity.property import MaltegoEntityProperty as MEF

entities = types.ModuleType("maltego.entities")

class Phrase(MaltegoEntity):
    TYPE_NAME = "maltego.Phrase"
    Config = MaltegoEntityConfig(value_property="value", display_name="Phrase")
    value: str = MEF(name="value", display_name="Value", value="")

class Person(MaltegoEntity):
    TYPE_NAME = "maltego.Person"
    Config = MaltegoEntityConfig(value_property="person.fullname", display_name="Person")
    fullname: str = MEF(name="person.fullname", display_name="Full name", value="")

class Image(MaltegoEntity):
    TYPE_NAME = "maltego.Image"
    Config = MaltegoEntityConfig(value_property="url", display_name="Image")
    url: str = MEF(name="url", display_name="URL", value="")

class Domain(MaltegoEntity):
    TYPE_NAME = "maltego.Domain"
    Config = MaltegoEntityConfig(value_property="fqdn", display_name="Domain")
    fqdn: str = MEF(name="fqdn", display_name="Domain", value="")

entities.Phrase = Phrase
entities.Person = Person
entities.Image = Image
entities.Domain = Domain
sys.modules["maltego.entities"] = entities

spec = importlib.util.spec_from_file_location(
    "generated_project", {str(project_dir / "project.py")!r}
)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load generated project module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
