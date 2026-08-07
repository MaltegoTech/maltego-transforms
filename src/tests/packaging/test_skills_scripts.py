"""
test_skills_scripts.py — Unit tests for TRX migration helper scripts.

Tests run scripts as subprocesses or import them as modules. maltego_trx
is not required to be installed; tests that need it are gracefully skipped.
"""

import json
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.packaging

# Paths — anchored to src/maltego relative to this file's location in src/tests/packaging/
_SRC = Path(__file__).parent.parent.parent
SCRIPTS_DIR_PLANNER = _SRC / "maltego" / "skills_assets" / "maltego-trx-migration-planner" / "scripts"
SCRIPTS_DIR_IMPLEMENTER = _SRC / "maltego" / "skills_assets" / "maltego-trx-migration-implementer" / "scripts"
SCRIPTS_DIR_DISCOVER = _SRC / "maltego" / "skills_assets" / "maltego-transform-discover" / "scripts"
SCRIPTS_DIR_TEST = _SRC / "maltego" / "skills_assets" / "maltego-transform-test" / "scripts"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "trx"
# Point STD_ENTITIES_SRC at a local checkout of maltego-transforms-std-entities/src
# to exercise the std-entity lookup tests; otherwise those tests are skipped.
# Unset (or empty) → None so the skip guard fires instead of falling back to ".".
_std_entities_env = os.environ.get("STD_ENTITIES_SRC", "").strip()
STD_ENTITIES_SRC = Path(_std_entities_env) if _std_entities_env else None

INVENTORY_SCRIPT = SCRIPTS_DIR_PLANNER / "trx_inventory.py"
REPORT_SCRIPT = SCRIPTS_DIR_PLANNER / "trx_migration_report.py"
CONTRACT_SCRIPT = SCRIPTS_DIR_PLANNER / "trx_contract.py"
LOOKUP_SCRIPT = SCRIPTS_DIR_PLANNER / "std_entity_lookup.py"
CANDIDATES_SCRIPT = SCRIPTS_DIR_IMPLEMENTER / "trx_to_sdk_candidates.py"
CHECK_SCRIPT = SCRIPTS_DIR_TEST / "sdk_project_check.py"
SDK_INTERNAL_TERMS = [
    "-".join(["maltego", "connectors", "python"]),
    "1" + "Password",
    " ".join(["Azure", "DevOps", "feed"]),
    "op" + "://",
]
KNOWN_TRX_EXAMPLES = (
    _SRC
    / "maltego"
    / "skills_assets"
    / "maltego-trx-migration-planner"
    / "references"
    / "known-trx-examples.md"
)


def run_script(script: Path, *args, check=False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=check,
    )


# ---------------------------------------------------------------------------
# trx_inventory.py tests
# ---------------------------------------------------------------------------

def test_trx_inventory_simple(tmp_path):
    """Inventory on simple_transform fixture must find transform with entity_strings."""
    result = run_script(INVENTORY_SCRIPT, str(FIXTURES_DIR / "simple_transform"))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["summary"]["total_transforms"] >= 1
    transforms = data["transforms"]
    assert any(t["name"] == "DomainToIP" for t in transforms)
    # entity string should be detected
    all_strings = [e for t in transforms for e in t.get("entity_strings", [])]
    assert "maltego.IPv4Address" in all_strings


def test_trx_inventory_settings(tmp_path):
    """Inventory on settings_transform fixture must detect settings."""
    result = run_script(INVENTORY_SCRIPT, str(FIXTURES_DIR / "settings_transform"))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    transforms = data["transforms"]
    assert any(t["name"] == "APILookup" for t in transforms)
    all_settings = [s for t in transforms for s in t.get("settings", [])]
    assert "api_key" in all_settings


def test_trx_inventory_complex(tmp_path):
    """Inventory on complex_transform fixture must detect ui_messages and exceptions."""
    result = run_script(INVENTORY_SCRIPT, str(FIXTURES_DIR / "complex_transform"))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    transforms = data["transforms"]
    assert any(t["name"] == "ComplexTransform" for t in transforms)
    # Check for ui_messages and exceptions
    target = next(t for t in transforms if t["name"] == "ComplexTransform")
    assert target["ui_messages"], "ui_messages should be detected"
    # overlays or properties
    assert target["overlays"] or target["properties"], "overlays/properties should be detected"


def test_trx_inventory_does_not_import_code(tmp_path):
    """Inventory should work even without maltego_trx installed (no code import)."""
    # Write a minimal transform to a temp dir that references a non-existent package
    proj = tmp_path / "fake_project"
    proj.mkdir()
    transforms_dir = proj / "transforms"
    transforms_dir.mkdir()
    (transforms_dir / "fake.py").write_text(
        "from some_nonexistent_package.transform import DiscoverableTransform\n\n"
        "class FakeTransform(DiscoverableTransform):\n"
        "    @classmethod\n"
        "    def create_entities(cls, request, response):\n"
        "        entity = response.addEntity('maltego.Domain')\n",
        encoding="utf-8",
    )
    result = run_script(INVENTORY_SCRIPT, str(proj))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    # Should still detect the transform even though the import would fail at runtime
    transforms = data["transforms"]
    assert any(t["name"] == "FakeTransform" for t in transforms)


def test_trx_fixture_modules_import_without_maltego_trx():
    """TRX migration fixtures are sample inputs and must not require TRX at test collection time."""
    fixture_files = sorted(FIXTURES_DIR.glob("*/transforms/*.py"))
    assert fixture_files

    for fixture_file in fixture_files:
        module_name = f"trx_fixture_{fixture_file.parent.parent.name}_{fixture_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, fixture_file)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


# ---------------------------------------------------------------------------
# trx_migration_report.py tests
# ---------------------------------------------------------------------------

def test_trx_migration_report_basic(tmp_path):
    """Run report on inventory JSON from simple fixture; check markdown output."""
    inv_result = run_script(INVENTORY_SCRIPT, str(FIXTURES_DIR / "simple_transform"))
    assert inv_result.returncode == 0, inv_result.stderr

    inv_file = tmp_path / "inventory.json"
    inv_file.write_text(inv_result.stdout, encoding="utf-8")

    report_result = run_script(REPORT_SCRIPT, str(inv_file))
    assert report_result.returncode == 0, report_result.stderr
    md = report_result.stdout
    assert "# TRX → SDK Migration Report" in md
    assert "DomainToIP" in md
    assert "maltego.IPv4Address" in md
    assert "Risk" in md


def test_trx_contract_extracts_wrapper_dispatch_args(tmp_path):
    """Contract extraction must read wrapper code, not only discovery CSVs."""
    project = tmp_path / "trx_project"
    transforms_dir = project / "trx" / "gunicorn" / "transforms"
    transforms_dir.mkdir(parents=True)
    (project / "transforms.csv").write_text(
        "Transform id,Description,Input type,Sets,Output\n"
        "opencti.attack-pattern.StixDomainEntityToStixObservable,"
        "OpenCTI: Attack Pattern to all Observables,"
        "maltego.STIX2.attack-pattern,To Observables [OpenCTI],\n",
        encoding="utf-8",
    )
    (transforms_dir / "openctiattackpattern.py").write_text(
        """
from maltego_trx.transform import DiscoverableTransform
from trx.gunicorn.extensions import global_registry, global_settings
from trx.gunicorn.opencti.openctitransform import opencti_transform

@global_registry.register_transform(
    settings=global_settings,
    display_name="Attack Pattern to all Observables",
    input_entity="maltego.STIX2.attack-pattern",
    description="OpenCTI: Attack Pattern to all Observables",
    output_entities=["maltego.STIX2.stix-cyber-observable"],
    transform_set="To Observables [OpenCTI]",
)
class openctiattackpatternStixDomainEntityToStixObservable(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        opencti_transform("StixDomainEntityToStixObservable", "stix-cyber-observable", request, response)
""",
        encoding="utf-8",
    )

    result = run_script(CONTRACT_SCRIPT, str(project))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert data["summary"]["total_transforms"] == 1
    assert data["summary"]["transforms_with_dispatch_args"] == 1
    transform = data["transforms"][0]
    assert transform["transform_id"] == "opencti.attack-pattern.StixDomainEntityToStixObservable"
    assert transform["input_entity"] == "maltego.STIX2.attack-pattern"
    assert transform["output_entities"] == ["maltego.STIX2.stix-cyber-observable"]
    assert transform["dispatch_calls"][0]["args"][:2] == [
        "StixDomainEntityToStixObservable",
        "stix-cyber-observable",
    ]
    assert transform["csv_output"] == ""
    assert transform["wrapper_output_args"] == ["stix-cyber-observable"]


def test_sdk_project_check_has_no_builtin_internal_term_defaults():
    text = CHECK_SCRIPT.read_text(encoding="utf-8")

    for term in SDK_INTERNAL_TERMS:
        assert term not in text


def test_sdk_project_check_scans_only_caller_supplied_terms(tmp_path):
    project_dir = tmp_path / "project"
    agents_dir = project_dir / ".agents"
    agents_dir.mkdir(parents=True)
    (project_dir / "project.py").write_text("print('ok')\n", encoding="utf-8")
    (agents_dir / "note.md").write_text("PRIVATE_MARKER\n", encoding="utf-8")

    without_terms = run_script(CHECK_SCRIPT, str(project_dir))
    assert without_terms.returncode == 0, without_terms.stderr
    assert "Internal terms: 0" in without_terms.stdout

    with_terms = run_script(CHECK_SCRIPT, str(project_dir), "--terms", "PRIVATE_MARKER")
    assert with_terms.returncode == 0, with_terms.stderr
    assert "Internal terms: 1" in with_terms.stdout
    assert "PRIVATE_MARKER" in with_terms.stdout


def test_trx_contract_flags_csv_output_drift(tmp_path):
    """If wrapper output args and CSV Output disagree, the report should expose it."""
    project = tmp_path / "trx_project"
    transforms_dir = project / "transforms"
    transforms_dir.mkdir(parents=True)
    (project / "transforms.csv").write_text(
        "Transform id,Description,Input type,Sets,Output\n"
        "example.domain.ToThing,Domain to Thing,maltego.Domain,Example,\n",
        encoding="utf-8",
    )
    (transforms_dir / "domain_to_thing.py").write_text(
        """
from maltego_trx.transform import DiscoverableTransform

@registry.register_transform(
    display_name="Domain to Thing",
    input_entity="maltego.Domain",
    output_entities=["maltego.Phrase"],
    transform_set="Example",
)
class ToThing(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        shared_dispatch("ToThing", "phrase", request, response)
""",
        encoding="utf-8",
    )

    result = run_script(CONTRACT_SCRIPT, str(project))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert data["summary"]["transforms_with_csv_output_drift"] == 1
    drift = data["warnings"]["csv_output_drift"][0]
    assert drift["wrapper_output_arg"] == "phrase"
    assert drift["csv_output"] == ""


def test_trx_contract_uses_wrapper_output_to_disambiguate_csv_rows(tmp_path):
    """Generated TRX projects can reuse description/input/set across output-specific rows."""
    project = tmp_path / "trx_project"
    transforms_dir = project / "transforms"
    transforms_dir.mkdir(parents=True)
    (project / "transforms.csv").write_text(
        "Transform id,Description,Input type,Sets,Output\n"
        "opencti.report.StixDomainEntityToReports,"
        "OpenCTI: Report to Reports,maltego.STIX2.report,To Reports [OpenCTI],\n"
        "opencti.report.report.ReportToStixDomainEntities,"
        "OpenCTI: Report to Reports,maltego.STIX2.report,To Reports [OpenCTI],report\n",
        encoding="utf-8",
    )
    (transforms_dir / "report_to_reports.py").write_text(
        """
from maltego_trx.transform import DiscoverableTransform

@registry.register_transform(
    display_name="Report to Reports",
    input_entity="maltego.STIX2.report",
    description="OpenCTI: Report to Reports",
    output_entities=["maltego.STIX2.report"],
    transform_set="To Reports [OpenCTI]",
)
class ReportToReports(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        opencti_transform("ReportToStixDomainEntities", "report", request, response)
""",
        encoding="utf-8",
    )

    result = run_script(CONTRACT_SCRIPT, str(project))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    transform = data["transforms"][0]
    assert transform["transform_id"] == "opencti.report.report.ReportToStixDomainEntities"
    assert transform["csv_output"] == "report"
    assert data["summary"]["transforms_with_csv_output_drift"] == 0


def test_trx_contract_does_not_treat_missing_csv_as_output_drift(tmp_path):
    """CSV-less projects should emit missing-csv evidence, not false drift."""
    project = tmp_path / "trx_project"
    transforms_dir = project / "transforms"
    transforms_dir.mkdir(parents=True)
    (transforms_dir / "domain_to_thing.py").write_text(
        """
from maltego_trx.transform import DiscoverableTransform

@registry.register_transform(
    display_name="Domain to Thing",
    input_entity="maltego.Domain",
    output_entities=["maltego.Phrase"],
    transform_set="Example",
)
class ToThing(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        shared_dispatch("ToThing", "phrase", request, response)
""",
        encoding="utf-8",
    )

    result = run_script(CONTRACT_SCRIPT, str(project))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert data["summary"]["transforms_with_csv_output_drift"] == 0
    assert data["summary"]["transforms_missing_csv_row"] == 1
    missing = data["warnings"]["missing_csv_row"][0]
    assert missing["wrapper_output_args"] == ["phrase"]


def test_trx_contract_flags_multiple_wrapper_outputs(tmp_path):
    """Multi-branch wrapper routing should not be hidden behind the first call."""
    project = tmp_path / "trx_project"
    transforms_dir = project / "transforms"
    transforms_dir.mkdir(parents=True)
    (project / "transforms.csv").write_text(
        "Transform id,Description,Input type,Sets,Output\n"
        "example.domain.ToThing,Domain to Thing,maltego.Domain,Example,phrase\n",
        encoding="utf-8",
    )
    (transforms_dir / "domain_to_thing.py").write_text(
        """
from maltego_trx.transform import DiscoverableTransform

@registry.register_transform(
    display_name="Domain to Thing",
    input_entity="maltego.Domain",
    description="Domain to Thing",
    output_entities=["maltego.Phrase"],
    transform_set="Example",
)
class ToThing(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        if request.Slider > 100:
            shared_dispatch("ToThing", "phrase", request, response)
        else:
            shared_dispatch("ToOtherThing", "alias", request, response)
""",
        encoding="utf-8",
    )

    result = run_script(CONTRACT_SCRIPT, str(project))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    transform = data["transforms"][0]
    assert transform["wrapper_output_args"] == ["phrase", "alias"]
    assert data["summary"]["transforms_with_multiple_wrapper_outputs"] == 1
    assert data["summary"]["transforms_with_csv_output_drift"] == 1
    assert data["warnings"]["csv_output_drift"][0]["wrapper_output_args"] == ["phrase", "alias"]


# ---------------------------------------------------------------------------
# std_entity_lookup.py tests
# ---------------------------------------------------------------------------

def test_std_entity_lookup_phrase():
    """Lookup maltego.Phrase — must not error; found=true or false but valid JSON."""
    result = run_script(LOOKUP_SCRIPT, "maltego.Phrase")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    # Must have 'found' key
    assert "found" in data
    if data["found"]:
        assert data["class_name"] == "Phrase"
    else:
        # Fallback to builtin mapping should still give found=true
        # (only fails if even the builtin mapping missed it — which it shouldn't)
        # So this path should not normally be hit for Phrase
        assert "suggestions" in data


def test_std_entity_lookup_ipv4():
    """Lookup maltego.IPv4Address."""
    result = run_script(LOOKUP_SCRIPT, "maltego.IPv4Address")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "found" in data
    if data["found"]:
        assert data["class_name"] == "IPv4Address"


def test_std_entity_lookup_not_found():
    """Lookup a nonexistent entity; expect found=false."""
    result = run_script(LOOKUP_SCRIPT, "maltego.NonExistentEntity12345")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["found"] is False
    assert "query" in data
    assert "suggestions" in data


def test_std_entity_lookup_matches_local_standard_entities_checkout():
    """When the std-entities checkout is available, validate key wire-type mappings against it."""
    if STD_ENTITIES_SRC is None or not STD_ENTITIES_SRC.exists():
        pytest.skip("set STD_ENTITIES_SRC to a local maltego-transforms-std-entities/src checkout to run this test")

    expected = {
        "maltego.Phrase": "Phrase",
        "maltego.DNSName": "DNSName",
        "maltego.IPv4Address": "IPv4Address",
        "maltego.Domain": "Domain",
        "maltego.Person": "Person",
        "maltego.EmailAddress": "EmailAddress",
        "maltego.PhoneNumber": "PhoneNumber",
        "maltego.URL": "URL",
        "maltego.Website": "Website",
        "maltego.Alias": "Alias",
    }
    for wire_type, class_name in expected.items():
        result = run_script(LOOKUP_SCRIPT, wire_type, "--local-src", str(STD_ENTITIES_SRC))
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["found"] is True
        assert data["class_name"] == class_name
        assert data["type_name"] == wire_type
        assert data["source"] == "local"


# ---------------------------------------------------------------------------
# trx_to_sdk_candidates.py tests
# ---------------------------------------------------------------------------

def test_trx_to_sdk_candidates_dryrun(tmp_path):
    """Dry-run on simple fixture must not write any files."""
    output_dir = tmp_path / "migrated"
    result = run_script(
        CANDIDATES_SCRIPT,
        str(FIXTURES_DIR / "simple_transform"),
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stderr
    # No --write flag → output_dir should not be created or be empty
    assert not output_dir.exists() or not any(output_dir.iterdir()), \
        "dry-run should not write files"
    # stdout should mention the transform
    assert "DomainToIP" in result.stdout or "domain_to_i_p" in result.stdout


def test_trx_to_sdk_candidates_write_requires_report(tmp_path):
    """--write without --report must exit non-zero with a clear error."""
    output_dir = tmp_path / "migrated"
    result = run_script(
        CANDIDATES_SCRIPT,
        str(FIXTURES_DIR / "simple_transform"),
        "--output-dir", str(output_dir),
        "--write",  # no --report provided
    )
    assert result.returncode != 0, "Expected non-zero exit when --write given without --report"
    assert "ERROR" in result.stdout or "ERROR" in result.stderr or "report" in result.stdout.lower()


def test_trx_to_sdk_candidates_graph_transform(tmp_path):
    """Candidate stub for a transform with multiple output entity types should compile cleanly."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_IMPLEMENTER))
    _sys.path.insert(0, str(SCRIPTS_DIR_PLANNER))
    try:
        from trx_to_sdk_candidates import _generate_stub  # type: ignore
    finally:
        _sys.path.pop(0)
        _sys.path.pop(0)

    # Transform returning two entity type strings (multi-entity / graph-like)
    transform = {
        "name": "DomainProfile",
        "class": "DomainProfile",
        "entity_strings": ["maltego.EmailAddress", "maltego.Person"],
        "settings": [],
        "ui_messages": [],
        "exceptions": [],
        "overlays": [],
        "links": [],
        "properties": ["fullname"],
    }
    stub = _generate_stub(transform)
    # Must compile without syntax errors
    compile(stub, "<DomainProfile stub>", "exec")
    # Must use MaltegoGraph for multi-entity return
    assert "MaltegoGraph" in stub
    assert "add_entity" in stub, "stub must use add_entity(), not add()"
    assert "result.add(" not in stub, "result.add() does not exist on MaltegoGraph; use result.add_entity()"


def test_trx_to_v3_candidate_stub_imports_and_registers(monkeypatch):
    """Generated simple stubs should import and register with the SDK."""
    import sys as _sys
    from tests.conftest import Domain, Person

    fake_entities = types.ModuleType("maltego.entities")
    fake_entities.Domain = Domain
    fake_entities.Person = Person
    monkeypatch.setitem(_sys.modules, "maltego.entities", fake_entities)

    _sys.path.insert(0, str(SCRIPTS_DIR_IMPLEMENTER))
    _sys.path.insert(0, str(SCRIPTS_DIR_PLANNER))
    try:
        from trx_to_sdk_candidates import _generate_stub  # type: ignore
    finally:
        _sys.path.pop(0)
        _sys.path.pop(0)

    transform = {
        "name": "DomainProfile",
        "class": "DomainProfile",
        "entity_strings": ["maltego.Domain", "maltego.Person"],
        "settings": [],
        "ui_messages": [],
        "exceptions": [],
        "overlays": [],
        "links": [],
        "properties": [],
    }
    stub = _generate_stub(transform)
    namespace: dict = {}
    exec(compile(stub, "<DomainProfile stub>", "exec"), namespace)

    assert callable(namespace["domain_profile"])


def test_discover_server_queries_v3_discovery_paths():
    """Discovery helper must query the SDK discovery endpoints, not root TRX-era paths."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_DISCOVER))
    try:
        import discover_server  # type: ignore
    finally:
        _sys.path.pop(0)

    requested_urls = []

    def fake_get_json(url):
        requested_urls.append(url)
        if url.endswith("/transforms"):
            return [{"id": "example.transform"}]
        if url.endswith("/assets/entities"):
            return [{"id": "maltego.Domain"}]
        if url.endswith("/health"):
            return {"status": "ok"}
        raise AssertionError(f"unexpected URL: {url}")

    with patch.object(discover_server, "_get_json", side_effect=fake_get_json):
        result = discover_server.discover("127.0.0.1", 8080)

    assert requested_urls == [
        "http://127.0.0.1:8080/api/v3/transforms",
        "http://127.0.0.1:8080/api/v3/assets/entities",
        "http://127.0.0.1:8080/health",
    ]
    assert result["transforms"] == [{"id": "example.transform"}]
    assert result["entities"] == [{"id": "maltego.Domain"}]


def test_discover_server_normalizes_custom_api_prefix():
    """Custom SDK api_prefix values are prepended before the JSON protocol discovery suffix."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_DISCOVER))
    try:
        import discover_server  # type: ignore
    finally:
        _sys.path.pop(0)

    requested_urls = []

    def fake_get_json(url):
        requested_urls.append(url)
        if url.endswith("/transforms"):
            return []
        if url.endswith("/assets/entities"):
            return []
        if url.endswith("/health"):
            return {"status": "ok"}
        raise AssertionError(f"unexpected URL: {url}")

    with patch.object(discover_server, "_get_json", side_effect=fake_get_json):
        discover_server.discover("127.0.0.1", 8080, api_prefix="/custom/")

    assert requested_urls[:2] == [
        "http://127.0.0.1:8080/custom/api/v3/transforms",
        "http://127.0.0.1:8080/custom/api/v3/assets/entities",
    ]


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", "http://localhost:8080"),
        ("127.0.0.1", "http://127.0.0.1:8080"),
        ("[::1]", "http://[::1]:8080"),
        ("2001:db8::1", "http://[2001:db8::1]:8080"),
    ],
)
def test_discover_server_builds_urls_from_valid_host_literals(host, expected):
    """The CLI accepts normal remote hosts but constructs an unambiguous URL
    authority rather than interpolating command-line text into one."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_DISCOVER))
    try:
        import discover_server  # type: ignore
    finally:
        _sys.path.pop(0)

    assert discover_server._build_base_url(host, 8080) == expected


@pytest.mark.parametrize(
    "host",
    [
        "http://example.test",
        "example.test/path",
        "example.test?query=value",
        "user@example.test",
        "example.test:1234",
        "example.test#fragment",
        "example.test whitespace",
    ],
)
def test_discover_server_rejects_url_authority_injection(host):
    """A CLI host is a hostname/IP literal, never a complete URL or authority
    fragment that could redirect discovery requests."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_DISCOVER))
    try:
        import discover_server  # type: ignore
    finally:
        _sys.path.pop(0)

    with pytest.raises(ValueError, match="host"):
        discover_server._build_base_url(host, 8080)


# ---------------------------------------------------------------------------
# sdk_project_check.py tests
# ---------------------------------------------------------------------------

def test_sdk_project_check_stale_imports(tmp_path):
    """Create a temp project with import maltego_trx; verify it flags the stale import."""
    proj = tmp_path / "stale_project"
    proj.mkdir()
    (proj / "transform.py").write_text(
        "import maltego_trx\nfrom maltego_trx.transform import DiscoverableTransform\n",
        encoding="utf-8",
    )
    result = run_script(CHECK_SCRIPT, str(proj))
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "import maltego_trx" in output or "Stale TRX Imports" in output
    # Parse the JSON summary at the end
    json_start = output.find("--- JSON Summary ---")
    assert json_start != -1
    json_part = output[json_start:].replace("--- JSON Summary ---", "").strip()
    summary = json.loads(json_part)
    assert summary["stale_imports"] >= 2  # two stale import lines


def test_sdk_project_check_queries_v3_discovery_paths():
    """check_server must query the SDK /api/v3 discovery endpoints, not bare paths."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_TEST))
    try:
        import sdk_project_check  # type: ignore
    finally:
        _sys.path.pop(0)

    requested_urls = []

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    def fake_urlopen(url, timeout=5):
        requested_urls.append(url)
        return _FakeResp()

    with patch.object(sdk_project_check.urllib.request, "urlopen", side_effect=fake_urlopen):
        sdk_project_check.check_server("http://127.0.0.1:8080")

    assert requested_urls == [
        "http://127.0.0.1:8080/api/v3/transforms",
        "http://127.0.0.1:8080/api/v3/assets/entities",
    ]


def test_sdk_project_check_rejects_non_http_server_url():
    """check_server must refuse non-http(s) schemes (e.g. file://) before opening the URL (N8)."""
    import sys as _sys
    _sys.path.insert(0, str(SCRIPTS_DIR_TEST))
    try:
        import sdk_project_check  # type: ignore
    finally:
        _sys.path.pop(0)

    def fake_urlopen(url, timeout=5):
        raise AssertionError(f"urlopen should not be called for non-http(s) URL, got: {url}")

    with patch.object(sdk_project_check.urllib.request, "urlopen", side_effect=fake_urlopen):
        with pytest.raises(SystemExit) as exc_info:
            sdk_project_check.check_server("file:///etc/passwd")

    assert exc_info.value.code == 2


import glob
import os

def test_no_unsupported_graph_api_in_skills():
    """Ensure that result.add( or result.add_ui_message( is never used in skills assets."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    for filepath in glob.glob(f"{assets_dir}/**/*.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
            assert "result.add(" not in content, f"Found unsupported result.add( in {filepath}"
            assert "result.add_ui_message(" not in content, f"Found unsupported result.add_ui_message( in {filepath}"
            assert "result.add_entity(" not in content, f"Found unsupported result.add_entity( in {filepath}"
            assert "MaltegoGraph.add_ui_message" not in content, f"Found unsupported MaltegoGraph.add_ui_message in {filepath}"

def test_no_context_integration_client_in_skills():
    """Ensure that context.integration_client() is not used in skills."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    for filepath in glob.glob(f"{assets_dir}/**/*.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
            assert "context.integration_client()" not in content, f"Found unsupported context.integration_client() in {filepath}"


def test_skill_docs_explain_transform_setting_global_flags():
    """Skill docs should prevent confusion between current and compatibility global flags."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    required = [
        "`is_global=True` is the current SDK flag",
        "`is_global_setting=True` is a compatibility flag",
        "Runtime access remains `settings.get(\"<name>\")`",
    ]
    for filepath in glob.glob(f"{assets_dir}/**/transform-authoring-patterns.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
        missing = [phrase for phrase in required if phrase not in content]
        assert not missing, f"{filepath} missing TransformSetting global flag guidance: {missing}"


def test_transform_basics_is_canonical_authoring_reference():
    """Surface-level authoring mechanics should live in one basics skill, not copied everywhere."""
    assets_root = _SRC / "maltego" / "skills_assets"
    basics_reference = (
        assets_root
        / "maltego-transform-basics"
        / "references"
        / "transform-authoring-patterns.md"
    )
    assert basics_reference.exists(), "maltego-transform-basics must own the authoring reference"

    authoring_refs = list(assets_root.glob("**/transform-authoring-patterns.md"))
    assert authoring_refs == [basics_reference]

    stale_refs = list(assets_root.glob("**/sdk-authoring-patterns.md"))
    assert stale_refs == [], f"Remove duplicated sdk-authoring-patterns.md files: {stale_refs}"


def test_no_root_v3_discovery_or_run_paths_in_skills():
    """SDK skill docs should use /api/v3 discovery and run endpoints."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    stale_patterns = [
        "127.0.0.1:8080/transforms",
        "127.0.0.1:8080/entities",
        "BASE_URL/transforms",
        "BASE_URL/entities",
        'client.get("/transforms")',
        'client.get("/entities")',
        "/run/<transform_id>",
        "/run/{transform_id}",
        "/run/domain_to_ip",
    ]
    for filepath in glob.glob(f"{assets_dir}/**/*.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
        found = [pattern for pattern in stale_patterns if pattern in content]
        assert not found, f"Found stale JSON protocol endpoint patterns in {filepath}: {found}"


def test_no_unsupported_context_members_in_skills():
    """Skill docs should not teach nonexistent MaltegoContext/logging members."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    stale_patterns = [
        "context.input_constraints",
        "context.logger",
        "message_type=",
    ]
    for filepath in glob.glob(f"{assets_dir}/**/*", recursive=True):
        if not filepath.endswith((".md", ".py")):
            continue
        with open(filepath, 'r') as f:
            content = f.read()
        found = [pattern for pattern in stale_patterns if pattern in content]
        assert not found, f"Found unsupported context/logging patterns in {filepath}: {found}"


def test_skill_docs_map_logs_to_status_message_events_not_ui_messages():
    """context.log guidance should describe V3 status-message events, not uiMessages."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    required = [
        "result.events[].data.statusMessage",
        "not `status.uiMessages`",
    ]
    combined = ""
    for filepath in glob.glob(f"{assets_dir}/**/*.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
        combined += content + "\n"

    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Skill docs missing status-message event guidance: {missing}"

    stale_patterns = [
        "return with UI message annotation",
        "populate `status.uiMessages`",
        "populates `status.uiMessages`",
    ]
    found = [pattern for pattern in stale_patterns if pattern in combined]
    assert not found, f"Skill docs still use stale uiMessages framing: {found}"


def test_skill_docs_do_not_claim_plain_dict_annotation_matches_settings():
    """Settings are matched by name or typing.Dict-style annotation, not plain dict alone."""
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "maltego", "skills_assets")
    for filepath in glob.glob(f"{assets_dir}/**/*.md", recursive=True):
        with open(filepath, 'r') as f:
            content = f.read()
        stale_patterns = [
            "`Dict[str, ...]` / `dict`",
            "`Dict[...]` / `dict`",
            "or `dict` annotation",
        ]
        found = [pattern for pattern in stale_patterns if pattern in content]
        assert not found, f"Skill docs overstate plain dict settings matching in {filepath}: {found}"


def test_trx_candidate_readme_matches_cli_contract():
    """Candidate helper README should document the actual project-path based CLI."""
    readme = (SCRIPTS_DIR_IMPLEMENTER / "README.md").read_text(encoding="utf-8")
    stale_flags = ["--transform", "--module", "--dry-run"]
    found = [flag for flag in stale_flags if flag in readme]
    assert not found, f"README documents unsupported trx_to_sdk_candidates flags: {found}"
    assert "trx_to_sdk_candidates.py <project-path>" in readme
    assert "--write" in readme
    assert "--report" in readme


def test_trx_implementer_skill_matches_candidate_cli_contract():
    """Implementer skill should document the actual project-path based candidate CLI."""
    skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(encoding="utf-8")
    stale_flags = ["--transform", "--module", "--dry-run"]
    found = [flag for flag in stale_flags if flag in skill]
    assert not found, f"Implementer skill documents unsupported trx_to_sdk_candidates flags: {found}"
    assert "trx_to_sdk_candidates.py <trx-project-path>" in skill
    assert "--write --report <migration-report.json> --output-dir <new-dir>" in skill


def test_trx_migration_skills_include_pilot_feedback_guardrails():
    """Pilot feedback guardrails should be documented in migration skills."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(encoding="utf-8")

    implementer_required = [
        "The `name=` argument to `@register_transform` is the canonical transform ID suffix.",
        "Do not use absolute paths in planning or migration artifacts.",
    ]
    planner_required = [
        "Use workspace-relative paths in JSON, YAML, and Markdown planning artifacts.",
        "Cite SDK evidence with public `https://` docs URLs or repository paths.",
    ]

    missing_implementer = [
        phrase for phrase in implementer_required
        if phrase not in implementer_skill
    ]
    missing_planner = [
        phrase for phrase in planner_required
        if phrase not in planner_skill
    ]

    assert not missing_implementer, f"Implementer skill missing guardrails: {missing_implementer}"
    assert not missing_planner, f"Planner skill missing guardrails: {missing_planner}"


def test_trx_migration_skills_define_default_migration_contract():
    """Migration intent should live in skills, not only in pilot prompts."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(encoding="utf-8")

    planner_required = [
        "## Default Migration Contract",
        "Preserve externally visible transform behavior",
        "Preserve transform IDs/names unless incompatible with SDK naming",
        "Preserve input/output entity types and key properties",
        "Preserve settings semantics",
        "Preserve API/client behavior",
        "rewrite transform authoring to SDK-native APIs",
        "Do not preserve TRX registry/wrapper/discovery artifacts unless explicitly requested",
        "## Public SDK Evidence",
        "## Migration Contract",
        "## Source Behavior Evidence",
        "## Assumptions",
    ]
    implementer_required = [
        "Read and follow the `## Migration Contract` section",
        "Preserve the behavior contract before preserving source shape",
        "Do not invent transform IDs, settings, entity mappings, or client behavior",
        "Do not copy TRX registry/wrapper/discovery artifacts unless the migration contract explicitly asks for compatibility-mode execution",
        "Document every contract deviation in `migration-report.md`",
    ]

    missing_planner = [
        phrase for phrase in planner_required
        if phrase not in planner_skill
    ]
    missing_implementer = [
        phrase for phrase in implementer_required
        if phrase not in implementer_skill
    ]

    assert not missing_planner, f"Planner skill missing migration contract defaults: {missing_planner}"
    assert not missing_implementer, f"Implementer skill missing migration contract rules: {missing_implementer}"


def test_trx_migration_skills_require_completion_quality_gates():
    """TRX migrations should not pass on transform count and smoke tests alone."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(
        encoding="utf-8"
    )
    test_skill = (SCRIPTS_DIR_TEST.parent / "SKILL.md").read_text(encoding="utf-8")
    parity_reference = (SCRIPTS_DIR_TEST.parent / "references" / "testing-and-parity.md").read_text(
        encoding="utf-8"
    )
    combined = f"{planner_skill}\n{implementer_skill}\n{test_skill}\n{parity_reference}"

    required = [
        "## Migration Completion Gates",
        "Source contract extraction",
        "Do not rely on CSV/discovery metadata alone",
        "Exact discovery parity",
        "Behavior-routing parity",
        "Deliverable hygiene",
        "Runtime entrypoint parity",
        "Report truthfulness",
        "A matching transform count is not sufficient",
        "wrapper output arguments",
        "No `.agents/`, starter example transforms, `.venv/`, `wheelhouse/`, `__pycache__/`, MTZ/XML discovery artifacts",
    ]
    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Migration skills missing completion gates: {missing}"


def test_trx_migration_planner_routes_to_contract_helper():
    """Planner should point agents at the source-contract helper before planning."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    scripts_readme = (SCRIPTS_DIR_PLANNER / "README.md").read_text(encoding="utf-8")
    combined = f"{planner_skill}\n{scripts_readme}"

    required = [
        "trx_contract.py <trx-project-path>",
        "source-contract extraction",
        "decorator metadata",
        "wrapper dispatch calls",
        "csv_output_drift",
    ]
    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Planner missing contract helper routing: {missing}"


def test_trx_migration_skills_reject_stale_success_reports():
    """Reports should not claim success if commands or file names are stale."""
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(
        encoding="utf-8"
    )
    test_reference = (SCRIPTS_DIR_TEST.parent / "references" / "testing-and-parity.md").read_text(
        encoding="utf-8"
    )
    combined = f"{implementer_skill}\n{test_reference}"

    required = [
        "Re-run verification after cleanup edits",
        "documented command must exist and start the server",
        "migration-report.md and eval-run-log.md must not reference deleted files",
        "Do not mark the migration complete while verification artifacts are stale",
    ]
    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Migration skills missing stale-report guardrails: {missing}"


def test_trx_migration_skills_keep_support_skills_optional_and_outcomes_required():
    """Agents should be guided by outcomes without being forced through every support skill."""
    index_skill = (
        _SRC
        / "maltego"
        / "skills_assets"
        / "maltego-transform-skill-index"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(
        encoding="utf-8"
    )

    required = [
        "Recommended path",
        "Optional deep dives",
        "Required outcomes",
        "Load `maltego-transform-discover` only when direct discovery needs deeper debugging",
        "Direct SDK discovery through `/api/v3/transforms`",
    ]
    combined = f"{index_skill}\n{implementer_skill}"
    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Migration skills missing optional/outcome guidance: {missing}"

    forbidden = [
        "Load `maltego-transform-discover` before verification",
        "Always load `maltego-transform-test`",
    ]
    found = [phrase for phrase in forbidden if phrase in combined]
    assert not found, f"Migration skills make support skills mandatory: {found}"


def test_trx_migration_skills_route_public_trx_examples_to_local_reference():
    """Public TRX example-shaped migrations should route to the bundled local comparison guide."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(
        encoding="utf-8"
    )

    planner_required = [
        "references/known-trx-examples.md",
        "load `references/known-trx-examples.md`",
        "register_transform_function",
        "MaltegoTransform().returnOutput()",
        "request.Slider",
        "sidecar CSV",
    ]
    implementer_required = [
        "references/known-trx-examples.md",
        "load the same reference",
        "function-style TRX transforms",
        "public-example-shaped migrations",
    ]

    missing_planner = [phrase for phrase in planner_required if phrase not in planner_skill]
    missing_implementer = [
        phrase for phrase in implementer_required if phrase not in implementer_skill
    ]

    assert not missing_planner, f"Planner skill missing public TRX routing guidance: {missing_planner}"
    assert not missing_implementer, (
        f"Implementer skill missing public TRX routing guidance: {missing_implementer}"
    )


def test_trx_migration_skills_map_request_slider_to_sdk_slider_param():
    """TRX request.Slider should map to the SDK slider parameter, not only settings."""
    planner_skill = (SCRIPTS_DIR_PLANNER.parent / "SKILL.md").read_text(encoding="utf-8")
    implementer_skill = (SCRIPTS_DIR_IMPLEMENTER.parent / "SKILL.md").read_text(
        encoding="utf-8"
    )
    mapping_reference = (
        SCRIPTS_DIR_PLANNER.parent / "references" / "trx-to-sdk-mapping.md"
    ).read_text(encoding="utf-8")
    examples_reference = KNOWN_TRX_EXAMPLES.read_text(encoding="utf-8")

    required = [
        "`request.Slider` | `slider: int`",
        "async def fetch_dummyjson_products(",
        "slider: int",
        "maps the Maltego slider input to that argument",
    ]
    combined = f"{planner_skill}\n{implementer_skill}\n{mapping_reference}\n{examples_reference}"
    missing = [phrase for phrase in required if phrase not in combined]
    assert not missing, f"Migration skills missing request.Slider guidance: {missing}"

    forbidden = [
        "explicit settings instead of `request.Slider`",
        "model that input as an explicit transform setting when the transform still needs",
    ]
    found = [phrase for phrase in forbidden if phrase in combined]
    assert not found, f"Migration skills still misclassify request.Slider as settings-only: {found}"


def test_known_trx_examples_reference_is_local_and_compact():
    """The bundled reference should cover the public examples without telling agents to fetch them."""
    assert KNOWN_TRX_EXAMPLES.exists(), "known-trx-examples.md must exist"
    content = KNOWN_TRX_EXAMPLES.read_text(encoding="utf-8")

    required = [
        "MaltegoTech/maltego-trx-examples",
        "GreetPerson",
        "DNSToIP",
        "NameFromCSV",
        "legacy_transform.py",
        "register_transform_function",
        "MaltegoTransform",
        "returnOutput",
        "request.Slider",
        "phone_to_names.csv",
        "@register_transform",
        "/api/v3/transforms",
    ]
    missing = [phrase for phrase in required if phrase not in content]
    assert not missing, f"known-trx-examples.md missing coverage: {missing}"

    forbidden = [
        "fetch GitHub",
        "clone the public examples repo",
        "clone the public examples",
        "fetch the public examples",
    ]
    found = [phrase for phrase in forbidden if phrase in content]
    assert not found, f"Reference should not direct agents to external fetch/clone steps: {found}"
