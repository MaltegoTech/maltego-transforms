import os
import re
import shutil
import sys
from typing import List, Optional, Tuple

import maltego

"""
Receive commands run to start a new project.
"""
FORCE_OVERWRITE = False
DEMO_TEMPLATE = "template_dir"
MINIMAL_TEMPLATE = "template_minimal_dir"
DEFAULT_PROJECT_MANAGER = "bare"
PROJECT_MANAGERS = {"bare", "poetry", "uv"}
START_USAGE = """Usage:
  maltego-transforms start [options] <project_name>

Create a new Maltego Transform SDK project.

Options:
  --minimal                         Generate the compact starter template.
  --demo                            Generate the example-rich starter template (default).
  --project-manager bare|poetry|uv  Add project metadata for the selected tool.
  --with-skills                     Add local SDK agent skills under .agents/skills/.
  --skills-scope local|global       Install skills into the project (local) or your global
                                    agent skills directory. Implies --with-skills.

Examples:
  maltego-transforms start my_transforms
  maltego-transforms start --minimal --with-skills --project-manager uv my_transforms

Add SDK skills to an existing project:
  maltego-transforms install-skills --target .
"""
INIT_USAGE = """Usage:
  maltego-transforms init [options]

Initialize the current directory as a Maltego Transform SDK project.

Options:
  --minimal                         Generate the compact starter template.
  --demo                            Generate the example-rich starter template (default).
  --project-manager bare|poetry|uv  Add project metadata for the selected tool.
  --with-skills                     Add local SDK agent skills under .agents/skills/.
  --skills-scope local|global       Install skills into the project (local) or your global
                                    agent skills directory. Implies --with-skills.

Examples:
  maltego-transforms init --minimal --with-skills
  maltego-transforms init --project-manager poetry
"""
INSTALL_SKILLS_USAGE = """Usage:
  maltego-transforms install-skills [--scope local|global] [--target DIR]

Install Maltego SDK agent skills without generating or changing starter files.

Options:
  --target DIR              Existing project directory to receive local skills.
                            Defaults to the current directory.
  --scope local|global      local installs into DIR/.agents/skills and adds
                            project bootstrap notes. global installs into the
                            configured global agent skills directory.

Examples:
  maltego-transforms install-skills --target .
  maltego-transforms install-skills --scope global
"""
COMMAND_USAGE = f"""Usage:
  maltego-transforms <command> [options]

Commands:
  start           Create a new SDK project.
  init            Initialize the current directory as an SDK project.
  install-skills  Add SDK agent skills to an existing project or global skills directory.

Run `maltego-transforms <command> --help` for command-specific options.
"""
LOCAL_SKILLS_BOOTSTRAP_MARKER = "<!-- maltego-transforms-skills -->"
LOCAL_SKILLS_BOOTSTRAP = f"""{LOCAL_SKILLS_BOOTSTRAP_MARKER}

## Maltego Transform SDK Skills

This project includes local Maltego SDK skills under `.agents/skills`.
When working on transforms in this project, first read:

`.agents/skills/maltego-transform-skill-index/SKILL.md`

That index routes agents to focused skills for SDK v3 authoring, TRX migration,
server discovery, docs lookup, and testing.
"""
LOCAL_SKILLS_README = """# Maltego Transform SDK Skills

This project includes local skills in `.agents/skills`.

Agents that support project-local skills can load them when started from this
project directory. If skills are not auto-discovered, read:

`.agents/skills/maltego-transform-skill-index/SKILL.md`
"""


def execute_from_command_line() -> None:
    args = sys.argv[1:]
    try:
        args, with_skills, skills_scope = parse_skills_options(args)
    except ValueError as e:
        print(f"ERROR: {e}")
        return

    if not args:
        print(COMMAND_USAGE)
    elif args[0].lower() == "start":
        run_start(args[1:], with_skills=with_skills, skills_scope=skills_scope)
    elif args[0].lower() == "init":
        run_start(args[1:], create_dir=False, with_skills=with_skills,
                  skills_scope=skills_scope)
    elif args[0].lower() == "install-skills":
        run_install_skills(args[1:])
    else:
        print(COMMAND_USAGE)


def parse_skills_options(args: List[str]) -> Tuple[List[str], bool, str]:
    """Extract skills-related CLI options from argv-style input."""
    cleaned_args: List[str] = []
    with_skills = False
    skills_scope = "local"
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--with-skills":
            with_skills = True
        elif arg == "--skills-scope":
            if i + 1 >= len(args):
                raise ValueError("--skills-scope requires 'local' or 'global'")
            skills_scope = args[i + 1].lower()
            with_skills = True
            i += 1
        elif arg.startswith("--skills-scope="):
            skills_scope = arg.split("=", 1)[1].lower()
            with_skills = True
        else:
            cleaned_args.append(arg)
        i += 1

    if skills_scope not in {"local", "global"}:
        raise ValueError("--skills-scope must be 'local' or 'global'")
    return cleaned_args, with_skills, skills_scope


def find_template_dir(template_name: str = DEMO_TEMPLATE) -> str:
    """Find a project template directory in the maltego namespace paths."""
    for path in maltego.__path__:
        template_path = os.path.join(path, template_name)
        if os.path.isdir(template_path):
            return template_path
    raise FileNotFoundError(f"Could not find {template_name} in maltego package paths")


def parse_start_args(args: List[str], create_dir: bool) -> Optional[Tuple[Optional[str], str, str]]:
    template_name = DEMO_TEMPLATE
    project_manager = DEFAULT_PROJECT_MANAGER
    project_args = []
    index = 0

    while index < len(args):
        arg = args[index]
        if arg in {"-h", "--help"}:
            print(START_USAGE if create_dir else INIT_USAGE)
            return None
        if arg == "--minimal":
            template_name = MINIMAL_TEMPLATE
        elif arg == "--demo":
            template_name = DEMO_TEMPLATE
        elif arg == "--project-manager":
            index += 1
            if index >= len(args):
                print(START_USAGE if create_dir else INIT_USAGE)
                sys.exit(2)
            project_manager = args[index].lower()
            if project_manager not in PROJECT_MANAGERS:
                print(START_USAGE if create_dir else INIT_USAGE)
                sys.exit(2)
        else:
            project_args.append(arg)
        index += 1

    if create_dir:
        if len(project_args) != 1:
            print(START_USAGE)
            return None
        if not is_safe_project_directory_name(project_args[0]):
            print("Project name must be a simple directory name without path separators.")
            return None
        if project_manager != DEFAULT_PROJECT_MANAGER and not normalize_project_name(project_args[0]):
            print(
                "Project name must contain at least one alphanumeric character "
                "for a valid pyproject name."
            )
            sys.exit(2)
        return project_args[0], template_name, project_manager

    if project_args:
        print(INIT_USAGE)
        return None
    return None, template_name, project_manager


def normalize_project_name(project_name: str) -> str:
    normalized_name = re.sub(r"[^a-z0-9]+", "-", project_name.lower())
    return normalized_name.strip("-")


def is_safe_project_directory_name(project_name: str) -> bool:
    return (
        bool(project_name)
        and project_name not in {".", ".."}
        and not project_name.startswith("-")
        and not os.path.isabs(project_name)
        and "/" not in project_name
        and "\\" not in project_name
    )


def render_pyproject(project_name: str, project_manager: str) -> Optional[str]:
    if project_manager == DEFAULT_PROJECT_MANAGER:
        return None

    normalized_name = normalize_project_name(project_name)
    pyproject_lines = [
        "[project]",
        f'name = "{normalized_name}"',
        'version = "0.1.0"',
        'requires-python = ">=3.10"',
        "dependencies = [",
        '    "maltego-transforms>=1.0.0",',
        '    "maltego-transforms-std-entities>=1.0.0",',
        "]",
    ]

    if project_manager == "poetry":
        pyproject_lines.extend(["", "[tool.poetry]", "package-mode = false"])

    return "\n".join(pyproject_lines) + "\n"


def apply_project_manager(project_dir: str, project_name: str, project_manager: str) -> None:
    pyproject_text = render_pyproject(project_name, project_manager)
    if pyproject_text is None:
        return

    pyproject_path = os.path.join(project_dir, "pyproject.toml")
    with open(pyproject_path, "w", encoding="utf-8") as pyproject_file:
        pyproject_file.write(pyproject_text)


def find_skills_dir() -> str:
    """Find skills_assets in the maltego namespace paths."""
    for path in maltego.__path__:
        skills_path = os.path.join(path, "skills_assets")
        if os.path.isdir(skills_path):
            return skills_path
    raise FileNotFoundError("Could not find skills_assets in maltego package paths")


def find_global_skills_dir(skills_home: str | None = None) -> str:
    """Return the provider-agnostic global skills directory."""
    if skills_home:
        return skills_home
    return os.path.join(os.path.expanduser("~"), ".agents", "skills")


def write_local_skills_bootstrap(project_dir: str) -> None:
    """Create local pointers that tell agents how to load generated skills."""
    agents_dir = os.path.join(project_dir, ".agents")
    os.makedirs(agents_dir, exist_ok=True)

    readme_path = os.path.join(agents_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(LOCAL_SKILLS_README)

    agents_md_path = os.path.join(project_dir, "AGENTS.md")
    if os.path.exists(agents_md_path):
        with open(agents_md_path, encoding="utf-8") as f:
            existing = f.read()
        if LOCAL_SKILLS_BOOTSTRAP_MARKER in existing:
            return
        separator = "" if existing.endswith("\n") else "\n"
        with open(agents_md_path, "a", encoding="utf-8") as f:
            f.write(f"{separator}\n{LOCAL_SKILLS_BOOTSTRAP}")
    else:
        with open(agents_md_path, "w", encoding="utf-8") as f:
            f.write(f"# Agent Guide\n\n{LOCAL_SKILLS_BOOTSTRAP}")


def install_skills(project_dir: str, skills_scope: str = "local", skills_home: str | None = None) -> str:
    """Install SDK agent skills into an existing project or global skills directory."""
    if skills_scope not in {"local", "global"}:
        raise ValueError("skills_scope must be 'local' or 'global'")

    skills_dir_path = find_skills_dir()
    if skills_scope == "global":
        skills_dst = find_global_skills_dir(skills_home)
    else:
        skills_dst = os.path.join(project_dir, ".agents", "skills")
    os.makedirs(skills_dst, exist_ok=True)
    copytree(src=skills_dir_path, dst=skills_dst, dirs_exist_ok=True)
    if skills_scope == "local":
        write_local_skills_bootstrap(project_dir)
    return skills_dst


def parse_install_skills_args(args: List[str]) -> Tuple[str, str]:
    """Parse install-skills arguments into (scope, target directory)."""
    skills_scope = "local"
    target_dir = os.getcwd()
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-h", "--help"}:
            print(INSTALL_SKILLS_USAGE)
            sys.exit(0)
        if arg == "--scope":
            index += 1
            if index >= len(args):
                print(INSTALL_SKILLS_USAGE)
                sys.exit(2)
            skills_scope = args[index].lower()
        elif arg.startswith("--scope="):
            skills_scope = arg.split("=", 1)[1].lower()
        elif arg == "--target":
            index += 1
            if index >= len(args):
                print(INSTALL_SKILLS_USAGE)
                sys.exit(2)
            target_dir = args[index]
        elif arg.startswith("--target="):
            target_dir = arg.split("=", 1)[1]
        else:
            print(INSTALL_SKILLS_USAGE)
            sys.exit(2)
        index += 1

    if skills_scope not in {"local", "global"}:
        print(INSTALL_SKILLS_USAGE)
        sys.exit(2)
    return skills_scope, target_dir


def run_install_skills(args: List[str], skills_home: str | None = None) -> None:
    """Install SDK skills without generating a starter project."""
    skills_scope, target_dir = parse_install_skills_args(args)
    project_dir = os.path.abspath(target_dir)
    if skills_scope == "local" and not os.path.isdir(project_dir):
        print(f"ERROR: target directory does not exist: {target_dir}")
        sys.exit(2)

    skills_dst = install_skills(project_dir, skills_scope, skills_home)
    if skills_scope == "global":
        print(f"Successfully installed SDK skills to '{skills_dst}'.")
        print("Agents that use this global skills directory can load the Maltego SDK skills from any project.")
    else:
        print(f"Successfully added SDK skills to '{skills_dst}'.")
        print("Agents that start in this project directory can load them from '.agents/skills/'.")
        print("If skills are not auto-discovered, read '.agents/skills/maltego-transform-skill-index/SKILL.md' first.")


def run_start(
    args: List[str],
    create_dir: bool = True,
    with_skills: bool = False,
    skills_scope: str = "local",
    skills_home: str | None = None,
) -> None:
    if skills_scope not in {"local", "global"}:
        raise ValueError("skills_scope must be 'local' or 'global'")

    parsed_args = parse_start_args(args, create_dir)
    if parsed_args is None:
        return

    project, template_name, project_manager = parsed_args
    if create_dir:
        assert project is not None
        project_dir = os.path.join(os.getcwd(), project)
        # Confine the generated project to the current working directory; reject
        # names that escape it (e.g. absolute paths or "../").
        cwd = os.path.abspath(os.getcwd())
        if os.path.commonpath([cwd, os.path.abspath(project_dir)]) != cwd:
            print(f"ERROR: project name must stay within the current directory: {project!r}")
            sys.exit(1)
        try:
            os.makedirs(project_dir)
        except FileExistsError:
            if not FORCE_OVERWRITE:
                print(f"Project directory {project_dir} already exists. Overwrite? [y/n]", end=" ")
                choice = input().lower()
                if choice in ['yes', 'y']:
                    pass
                else:
                    sys.exit(1)
    else:
        project_dir = os.getcwd()
        project = os.path.basename(project_dir)
        if project_manager != DEFAULT_PROJECT_MANAGER and not normalize_project_name(project):
            print(
                "Project name must contain at least one alphanumeric character "
                "for a valid pyproject name."
            )
            sys.exit(2)
    try:
        template_dir_path = find_template_dir(template_name)
        copytree(src=template_dir_path, dst=project_dir, dirs_exist_ok=True)
        apply_project_manager(project_dir, project, project_manager)
        print(f"Successfully created a new project in the '{project}' folder.")

        if with_skills:
            skills_dst = install_skills(project_dir, skills_scope, skills_home)
            if skills_scope == "global":
                print(f"Successfully installed SDK skills to '{skills_dst}'.")
                print("Agents that use this global skills directory can load the Maltego SDK skills from any project.")
            else:
                print("Successfully added SDK skills to '.agents/skills/'.")
                print("Agents that start in this project directory can load them from '.agents/skills/'.")
                print("If skills are not auto-discovered, read '.agents/skills/maltego-transform-skill-index/SKILL.md' first.")
    except FileExistsError:
        print(f"ERROR: '{project_dir}' already exists")
    except OSError as e:
        print(f"ERROR: {e}")


def copytree(src: str, dst: str, symlinks: bool = False, dirs_exist_ok: bool = False) -> None:
    os.makedirs(dst, exist_ok=dirs_exist_ok)
    for item in os.listdir(src):
        if "__pycache__" not in item and ".pyc" not in item and item != ".gitkeep":
            source_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)
            if os.path.isdir(source_path):
                copytree(src=source_path, dst=dst_path, symlinks=symlinks, dirs_exist_ok=dirs_exist_ok)
            else:
                shutil.copy2(source_path, dst_path)
