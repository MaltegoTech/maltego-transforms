import importlib.util
import os
import py_compile
import subprocess
from pathlib import Path
import sys

import pytest

import maltego._cli as cli
from maltego._cli import (
    LOCAL_SKILLS_BOOTSTRAP_MARKER,
    run_start,
    find_skills_dir,
    parse_skills_options,
)

pytestmark = pytest.mark.template

REPO_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TEMPLATE_DEPENDENCIES = [
    "maltego-transforms>=1.0.1",
    "maltego-transforms-std-entities>=1.0.0",
]


def test_start_generates_demo_project_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli.run_start(["demo_project"])

    project_dir = tmp_path / "demo_project"
    assert (project_dir / "project.py").is_file()
    assert (project_dir / "transforms" / "quickstart_example.py").is_file()
    assert "transforms.quickstart_example" in (project_dir / "project.py").read_text()
    assert (project_dir / "requirements.txt").read_text().splitlines() == EXPECTED_TEMPLATE_DEPENDENCIES


def test_start_minimal_generates_setup_only_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli.run_start(["--minimal", "minimal_project"])

    project_dir = tmp_path / "minimal_project"
    transform_files = sorted(path.name for path in (project_dir / "transforms").iterdir())

    assert (project_dir / "project.py").is_file()
    assert transform_files == ["__init__.py"]
    assert "transforms.quickstart_example" not in (project_dir / "project.py").read_text()
    assert "start --minimal" in (project_dir / "README.md").read_text()
    assert (project_dir / "requirements.txt").read_text().splitlines() == EXPECTED_TEMPLATE_DEPENDENCIES


@pytest.mark.parametrize("project_manager", ["bare", "poetry", "uv"])
def test_start_supports_explicit_project_manager(tmp_path, monkeypatch, project_manager):
    monkeypatch.chdir(tmp_path)

    args = ["--project-manager", project_manager, "managed_project"]
    cli.run_start(args)

    project_dir = tmp_path / "managed_project"
    assert (project_dir / "project.py").is_file()
    assert (project_dir / "README.md").is_file()

    pyproject_path = project_dir / "pyproject.toml"
    if project_manager == "bare":
        assert not pyproject_path.exists()
        assert (project_dir / "requirements.txt").read_text().splitlines() == EXPECTED_TEMPLATE_DEPENDENCIES
    else:
        pyproject = pyproject_path.read_text()
        assert 'name = "managed-project"' in pyproject
        assert '    "maltego-transforms>=1.0.1",' in pyproject
        assert '    "maltego-transforms-std-entities>=1.0.0",' in pyproject
        if project_manager == "poetry":
            assert "[tool.poetry]" in pyproject
        else:
            assert "[project]" in pyproject
            assert "[tool.poetry]" not in pyproject


@pytest.mark.parametrize("project_manager", ["bare", "poetry", "uv"])
def test_init_supports_explicit_project_manager(tmp_path, monkeypatch, project_manager):
    project_dir = tmp_path / "init_project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    args = ["--project-manager", project_manager]
    cli.run_start(args, create_dir=False)

    pyproject_path = project_dir / "pyproject.toml"
    if project_manager == "bare":
        assert not pyproject_path.exists()
    else:
        pyproject = pyproject_path.read_text()
        assert 'name = "init-project"' in pyproject
        if project_manager == "poetry":
            assert "[tool.poetry]" in pyproject
        else:
            assert "[project]" in pyproject


@pytest.mark.parametrize("project_manager", ["bare", "poetry", "uv"])
def test_generated_demo_project_compiles_for_all_project_managers(tmp_path, monkeypatch, project_manager):
    monkeypatch.chdir(tmp_path)

    args = ["demo_project"]
    if project_manager != "bare":
        args = ["--project-manager", project_manager, "demo_project"]
    cli.run_start(args)

    project_dir = tmp_path / "demo_project"

    compile_generated_python_files(project_dir)
    import_generated_project_module_in_subprocess(project_dir, stub_standard_entities=True)


def compile_generated_python_files(project_dir: Path) -> None:
    for path in project_dir.rglob("*.py"):
        py_compile.compile(str(path), doraise=True)


def import_generated_project_module(project_dir: Path) -> None:
    src_dir = Path(__file__).resolve().parents[2]
    original_path = list(sys.path)
    sys.path[:0] = [str(project_dir), str(src_dir)]
    try:
        spec = importlib.util.spec_from_file_location("generated_project", project_dir / "project.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path


def import_generated_project_module_in_subprocess(project_dir: Path, stub_standard_entities: bool = False) -> None:
    src_dir = Path(__file__).resolve().parents[2]
    code = f"""
import importlib.util
import sys
import types

sys.path[:0] = [{str(project_dir)!r}, {str(src_dir)!r}]

if {stub_standard_entities!r}:
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

spec = importlib.util.spec_from_file_location("generated_project", {str(project_dir / "project.py")!r})
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load generated project module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize("project_manager", ["bare", "poetry", "uv"])
def test_generated_minimal_project_compiles_and_imports_for_all_project_managers(tmp_path, monkeypatch, project_manager):
    monkeypatch.chdir(tmp_path)

    args = ["--minimal"]
    if project_manager != "bare":
        args.extend(["--project-manager", project_manager])
    cli.run_start(args, create_dir=False)

    compile_generated_python_files(tmp_path)
    import_generated_project_module(tmp_path)


@pytest.mark.parametrize(
    "args",
    [
        ["--project-manager", "hatch", "demo_project"],
        ["--project-manager"],
    ],
)
def test_start_rejects_invalid_project_manager_with_usage_error(
    tmp_path, monkeypatch, capsys, args
):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        cli.run_start(args)

    assert excinfo.value.code == 2
    assert not (tmp_path / "demo_project").exists()
    assert "bare|poetry|uv" in capsys.readouterr().out


@pytest.mark.parametrize("project_manager", ["poetry", "uv"])
def test_start_rejects_project_name_that_normalizes_to_empty_for_pyproject_manager(
    tmp_path, monkeypatch, capsys, project_manager
):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        cli.run_start(["--project-manager", project_manager, "!!!"])

    assert excinfo.value.code == 2
    assert not (tmp_path / "!!!").exists()
    assert "valid pyproject name" in capsys.readouterr().out


@pytest.mark.parametrize("project_manager", ["poetry", "uv"])
def test_init_rejects_current_directory_name_that_normalizes_to_empty_for_pyproject_manager(
    tmp_path, monkeypatch, capsys, project_manager
):
    project_dir = tmp_path / "!!!"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    with pytest.raises(SystemExit) as excinfo:
        cli.run_start(["--project-manager", project_manager], create_dir=False)

    assert excinfo.value.code == 2
    assert not (project_dir / "pyproject.toml").exists()
    assert "valid pyproject name" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("project_name", "unexpected_path"),
    [
        ("../outside", lambda tmp_path: tmp_path.parent / "outside"),
        ("nested/project", lambda tmp_path: tmp_path / "nested"),
        ("nested\\project", lambda tmp_path: tmp_path / "nested\\project"),
    ],
)
def test_start_rejects_project_names_that_escape_the_current_directory(
    tmp_path, monkeypatch, capsys, project_name, unexpected_path
):
    monkeypatch.chdir(tmp_path)

    cli.run_start([project_name])

    assert not unexpected_path(tmp_path).exists()
    assert "simple directory name" in capsys.readouterr().out


def test_start_rejects_absolute_project_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.run_start([str(tmp_path / "absolute_project")])

    assert not (tmp_path / "absolute_project").exists()
    assert "simple directory name" in capsys.readouterr().out


def test_start_help_prints_usage_without_creating_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.run_start(["--help"])

    assert not (tmp_path / "--help").exists()
    output = capsys.readouterr().out
    assert "maltego-transforms start" in output
    assert "--with-skills" in output
    assert "--skills-scope local|global" in output
    assert "maltego-transforms install-skills --target ." in output


def test_init_help_documents_skills_options(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.run_start(["--help"], create_dir=False)

    output = capsys.readouterr().out
    assert "maltego-transforms init" in output
    assert "--with-skills" in output
    assert "--skills-scope local|global" in output


def test_install_skills_help_documents_existing_project_flow(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.run_install_skills(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "maltego-transforms install-skills" in output
    assert "--target DIR" in output
    assert "--scope local|global" in output
    assert "without generating or changing starter files" in output


def test_top_level_help_lists_install_skills_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["maltego-transforms"])

    cli.execute_from_command_line()

    output = capsys.readouterr().out
    assert "maltego-transforms <command>" in output
    assert "install-skills" in output


def test_demo_template_readme_documents_project_manager_modes():
    readme = (REPO_ROOT / "src/maltego/template_dir/README.md").read_text()
    lowered = readme.lower()

    assert "bare is" in lowered
    assert "default project manager" in lowered
    assert "maltego-transforms start --project-manager poetry" in lowered
    assert "maltego-transforms start --project-manager uv" in lowered


def test_minimal_template_readme_documents_project_manager_modes():
    readme = (REPO_ROOT / "src/maltego/template_minimal_dir/README.md").read_text()
    lowered = readme.lower()

    assert "bare is" in lowered
    assert "default project manager" in lowered
    assert "maltego-transforms start --project-manager poetry" in lowered
    assert "maltego-transforms start --project-manager uv" in lowered


def test_init_minimal_generates_in_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli.run_start(["--minimal"], create_dir=False)

    assert (tmp_path / "project.py").is_file()
    assert (tmp_path / "transforms" / "__init__.py").is_file()
    assert not list((tmp_path / "transforms").glob("*_example.py"))


class TestStartCommand:
    def test_start_creates_project(self, tmp_path):
        """Without --with-skills, project is created without .agents/skills."""
        project_name = "test_project"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=False)
            project_dir = tmp_path / project_name
            assert project_dir.exists()
            agents_dir = project_dir / ".agents"
            assert not agents_dir.exists(), ".agents/ should NOT exist without --with-skills"
        finally:
            os.chdir(original_cwd)

    def test_start_with_skills_creates_agents_dir(self, tmp_path):
        """With --with-skills, project includes .agents/skills/."""
        project_name = "test_project_with_skills"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=True)
            project_dir = tmp_path / project_name
            assert project_dir.exists()
            skills_dir = project_dir / ".agents" / "skills"
            assert skills_dir.exists(), ".agents/skills/ should exist with --with-skills"
        finally:
            os.chdir(original_cwd)

    def test_start_with_skills_creates_local_bootstrap_files(self, tmp_path, capsys):
        """Local skills install tells agents how to load project-local skills."""
        project_name = "test_project_with_bootstrap"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=True)
            project_dir = tmp_path / project_name
            agents_md = project_dir / "AGENTS.md"
            agents_readme = project_dir / ".agents" / "README.md"

            assert agents_md.exists()
            assert agents_readme.exists()
            assert ".agents/skills/maltego-transform-skill-index/SKILL.md" in agents_md.read_text()
            assert ".agents/skills/maltego-transform-skill-index/SKILL.md" in agents_readme.read_text()

            output = capsys.readouterr().out
            assert "Agents that start in this project directory can load them" in output
            assert "maltego-transform-skill-index/SKILL.md" in output
        finally:
            os.chdir(original_cwd)

    def test_start_with_skills_appends_existing_agents_md_once(self, tmp_path):
        """Existing project AGENTS.md is preserved and not duplicated on repeated init."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Existing Agent Guide\n\nKeep me.\n")
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([], create_dir=False, with_skills=True)
            run_start([], create_dir=False, with_skills=True)

            text = agents_md.read_text()
            assert "# Existing Agent Guide" in text
            assert "Keep me." in text
            assert text.count(LOCAL_SKILLS_BOOTSTRAP_MARKER) == 1
        finally:
            os.chdir(original_cwd)

    def test_start_with_global_skills_installs_global_only(self, tmp_path):
        """Global skills scope installs to the configured global skills dir."""
        project_name = "test_project_global_skills"
        global_skills = tmp_path / "global" / "skills"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start(
                [project_name],
                with_skills=True,
                skills_scope="global",
                skills_home=str(global_skills),
            )
            project_dir = tmp_path / project_name
            assert (global_skills / "maltego-transform-skill-index" / "SKILL.md").exists()
            assert not (project_dir / ".agents" / "skills").exists()
            assert not (project_dir / "AGENTS.md").exists()
        finally:
            os.chdir(original_cwd)

    def test_start_with_skills_contains_all_expected_skill_dirs(self, tmp_path):
        """With --with-skills, all expected skill directories are present."""
        expected_skills = [
            "maltego-transforms",
            "maltego-transform-skill-index",
            "maltego-transform-docs",
            "maltego-transform-design",
            "maltego-transform-build",
            "maltego-transform-test",
            "maltego-transform-discover",
            "maltego-trx-migration-planner",
            "maltego-trx-migration-implementer",
        ]
        project_name = "test_project_full_skills"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=True)
            skills_dir = tmp_path / project_name / ".agents" / "skills"
            for skill_name in expected_skills:
                skill_path = skills_dir / skill_name
                assert skill_path.exists(), f"Expected skill dir '{skill_name}' not found"
        finally:
            os.chdir(original_cwd)

    def test_start_without_skills_keeps_current_behavior(self, tmp_path):
        """Without --with-skills, original template files are still created."""
        project_name = "test_project_no_skills"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=False)
            project_dir = tmp_path / project_name
            assert project_dir.exists()
            assert any(project_dir.iterdir()), "Project directory should not be empty"
        finally:
            os.chdir(original_cwd)

    def test_find_skills_dir_returns_path(self):
        """find_skills_dir() returns a valid path that exists."""
        skills_dir = find_skills_dir()
        assert os.path.isdir(skills_dir), f"skills_assets dir not found at {skills_dir}"

    def test_gitkeep_not_copied_to_project(self, tmp_path):
        """.gitkeep files are not included in generated project."""
        project_name = "test_no_gitkeep"
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            run_start([project_name], with_skills=True)
            project_dir = tmp_path / project_name
            gitkeep_files = list(project_dir.rglob(".gitkeep"))
            assert len(gitkeep_files) == 0, f".gitkeep files should not appear in project: {gitkeep_files}"
        finally:
            os.chdir(original_cwd)

    def test_parse_skills_options_supports_scope(self):
        """CLI parser supports explicit local/global skills scopes."""
        args, with_skills, scope = parse_skills_options([
            "start",
            "example",
            "--skills-scope",
            "global",
        ])
        assert args == ["start", "example"]
        assert with_skills is True
        assert scope == "global"

        args, with_skills, scope = parse_skills_options([
            "start",
            "example",
            "--with-skills",
            "--skills-scope=local",
        ])
        assert args == ["start", "example"]
        assert with_skills is True
        assert scope == "local"

    def test_parse_skills_options_rejects_invalid_scope(self):
        """Invalid scope values should fail before project generation."""
        with pytest.raises(ValueError, match="local"):
            parse_skills_options(["start", "example", "--skills-scope", "workspace"])

    def test_install_skills_local_target_installs_without_scaffolding(self, tmp_path, capsys):
        """install-skills adds local skill files to an existing project only."""
        cli.run_install_skills(["--target", str(tmp_path)])

        assert (tmp_path / ".agents" / "skills" / "maltego-transform-skill-index" / "SKILL.md").exists()
        assert (tmp_path / ".agents" / "README.md").exists()
        agents_md = tmp_path / "AGENTS.md"
        assert agents_md.exists()
        assert ".agents/skills/maltego-transform-skill-index/SKILL.md" in agents_md.read_text()
        assert not (tmp_path / "project.py").exists()

        output = capsys.readouterr().out
        assert "Successfully added SDK skills to" in output
        assert "maltego-transform-skill-index/SKILL.md" in output

    def test_install_skills_global_scope_installs_global_only(self, tmp_path):
        """install-skills --scope global installs to the configured global skills dir."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        global_skills = tmp_path / "global" / "skills"

        cli.run_install_skills(
            ["--scope", "global", "--target", str(project_dir)],
            skills_home=str(global_skills),
        )

        assert (global_skills / "maltego-transform-skill-index" / "SKILL.md").exists()
        assert not (project_dir / ".agents").exists()
        assert not (project_dir / "AGENTS.md").exists()

    def test_install_skills_rejects_missing_local_target(self, tmp_path):
        """Local install must target an existing directory."""
        missing_target = tmp_path / "missing"

        with pytest.raises(SystemExit) as exc_info:
            cli.run_install_skills(["--target", str(missing_target)])

        assert exc_info.value.code == 2


class TestInternalTermSmoke:
    """Smoke test: verify shipped skill assets don't contain internal-only terms."""

    INTERNAL_TERMS = [
        "jinx-py-starter",
        "-".join(["maltego", "connectors", "python"]),
        "TXS",
        "CCS",
        "ZED",
        "1" + "Password",
        " ".join(["Azure", "DevOps", "feed"]),
        "Azure tracing",
        "op" + "://",
    ]

    def test_no_internal_terms_in_skills_assets(self):
        """Shipped skill assets must not contain internal-only terms."""
        skills_dir = find_skills_dir()
        EXCLUDED_FILES = {"sdk_project_check.py"}
        violations = []
        for root, dirs, files in os.walk(skills_dir):
            for fname in files:
                if fname in EXCLUDED_FILES:
                    continue
                if fname.endswith(('.md', '.py', '.yaml', '.yml')):
                    fpath = os.path.join(root, fname)
                    with open(fpath, encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    for term in self.INTERNAL_TERMS:
                        if term in content:
                            violations.append((fpath, term))
        assert not violations, (
            "Internal-only terms found in skill assets:\n" +
            "\n".join(f"  {path}: '{term}'" for path, term in violations)
        )
