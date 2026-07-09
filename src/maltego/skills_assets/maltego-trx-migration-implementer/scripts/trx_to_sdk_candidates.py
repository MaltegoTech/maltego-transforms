#!/usr/bin/env python3
"""
trx_to_sdk_candidates.py — Generate SDK candidate rewrites for simple TRX transforms.

Identifies simple rewrite candidates (class-based DiscoverableTransform with create_entities)
and emits async @register_transform function stubs.

Default: dry-run only (print to stdout).
--write: write to output-dir (requires --report).
NEVER writes to the original source tree.

CLI: python trx_to_sdk_candidates.py <project-path> [--report migration-report.json]
         [--output-dir ./migrated] [--write]
"""

import argparse
import json
import sys
from pathlib import Path


def _is_simple_candidate(transform_info: dict) -> bool:
    """A transform is a simple candidate if it has no overlays, links, or oauth."""
    return (
        not transform_info.get("overlays")
        and not transform_info.get("links")
        and not transform_info.get("oauth_settings")
    )


def _entity_class_from_wire(wire_type: str) -> str:
    """Convert wire type to entity class name."""
    mapping = {
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
    return mapping.get(wire_type, f"CustomEntity  # was: {wire_type}")


def _generate_stub(transform: dict) -> str:
    """Generate an SDK async transform stub from inventory entry."""
    name = transform.get("name", "unknown_transform")
    func_name = name[0].lower() + name[1:] if name else "transform"
    # Convert CamelCase → snake_case
    import re
    func_name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    entity_strings = transform.get("entity_strings", [])
    settings = transform.get("settings", [])

    # Pick first entity string as output entity (heuristic)
    output_entities = [_entity_class_from_wire(e) for e in entity_strings] if entity_strings else []
    primary_output = output_entities[0] if output_entities else "MaltegoEntity"
    primary_output_clean = primary_output.split("#")[0].strip()

    # Collect entity imports
    entity_imports: list[str] = []
    for wire in entity_strings:
        cls = _entity_class_from_wire(wire)
        if "#" not in cls:
            entity_imports.append(cls)

    imports_block = "from typing import Any, Dict\nfrom maltego.server import register_transform, MaltegoEntity\nfrom maltego.model.context import MaltegoContext\nfrom maltego.model.graph import MaltegoGraph"
    if entity_imports:
        imports_block += f"\nfrom maltego.entities import {', '.join(sorted(set(entity_imports)))}"

    settings_block = ""
    settings_param = ""
    if settings:
        settings_param = ", settings: Dict[str, Any]"
        settings_block = "\n    # Settings (via settings: Dict[str, Any] parameter)\n"
        for s in settings:
            settings_block += f"    {s} = settings.get(\"{s}\", \"\")  # TODO: define in @register_transform settings=[...]\n"

    ui_messages = transform.get("ui_messages", [])
    ui_block = ""
    if ui_messages:
        ui_block = "\n    # UI messages (was response.addUIMessage)\n"
        ui_block += "    # context.log.inform(\"...\")\n"

    exceptions_block = ""
    if transform.get("exceptions"):
        exceptions_block = "\n    # Exceptions (raise MaltegoException instead of response.addException)\n"
        exceptions_block += "    # from maltego.model.exception import MaltegoException\n"
        exceptions_block += "    # raise MaltegoException(\"message\")\n"

    properties_block = ""
    if transform.get("properties"):
        properties_block = "\n    # Properties (map to entity field definitions in SDK)\n"

    output_block = f"    result = MaltegoGraph()\n"
    if primary_output_clean and primary_output_clean != "MaltegoEntity":
        output_block += f"    # Example: graph.add_entity({primary_output_clean}(value=\"...\"))\n"
    output_block += "    return result\n"

    stub = f"""{imports_block}


@register_transform(
    display_name="{name}",
)
async def {func_name}(entity: MaltegoEntity{settings_param}, context: MaltegoContext) -> MaltegoGraph:
    # TODO: replace MaltegoEntity with the specific input type, e.g. entity: Domain
    \"\"\"Migrated from TRX {name}. TODO: implement.\"\"\"{settings_block}{ui_block}{exceptions_block}{properties_block}
{output_block}"""

    return stub


def main():
    parser = argparse.ArgumentParser(
        description="Generate SDK candidate rewrites for simple TRX transforms."
    )
    parser.add_argument("project_path", help="Path to the TRX project root.")
    parser.add_argument("--report", metavar="FILE", help="Path to migration-report.json.")
    parser.add_argument("--output-dir", metavar="DIR", default="./migrated",
                        help="Directory to write migrated files (default: ./migrated).")
    parser.add_argument("--write", action="store_true",
                        help="Write candidate stubs to output-dir (dry-run by default).")
    args = parser.parse_args()

    # --write requires --report
    if args.write and not args.report:
        print("ERROR: --write requires --report", file=sys.stderr)
        sys.exit(1)

    project_root = Path(args.project_path).resolve()
    output_dir = Path(args.output_dir).resolve()

    # Safety: never write into the original source tree
    try:
        output_dir.relative_to(project_root)
        print("ERROR: --output-dir must not be inside the original project tree.", file=sys.stderr)
        sys.exit(1)
    except ValueError:
        pass

    # Import trx_inventory — look in this dir, then in the sibling planner scripts dir
    scripts_dir = Path(__file__).parent
    planner_scripts_dir = (
        scripts_dir.parent.parent / "maltego-trx-migration-planner" / "scripts"
    )
    for d in [scripts_dir, planner_scripts_dir]:
        if str(d) not in sys.path and d.exists():
            sys.path.insert(0, str(d))

    try:
        from trx_inventory import inventory_project  # type: ignore[import]
    except ImportError:
        # Fallback: run as subprocess to get inventory JSON
        import subprocess
        script = planner_scripts_dir / "trx_inventory.py"
        if not script.exists():
            script = scripts_dir / "trx_inventory.py"
        result = subprocess.run(
            [sys.executable, str(script), str(project_root)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"ERROR running trx_inventory.py: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        inventory = json.loads(result.stdout)

        transforms = inventory.get("transforms", [])
        candidates = []
        for t in transforms:
            is_candidate = bool(t.get("base_classes")) and _is_simple_candidate(t)
            reason = "ok" if is_candidate else "complex (overlays/links/oauth present)"
            stub = _generate_stub(t) if is_candidate else None
            candidates.append({"transform": t, "is_candidate": is_candidate, "reason": reason, "stub": stub})

        _output_candidates(candidates, args, output_dir)
        return

    inventory = inventory_project(str(project_root))

    candidates = []
    for t in inventory.get("transforms", []):
        is_candidate = bool(t.get("base_classes")) and _is_simple_candidate(t)
        reason = "ok" if is_candidate else "complex (overlays/links/oauth present)"
        stub = _generate_stub(t) if is_candidate else None
        candidates.append({"transform": t, "is_candidate": is_candidate, "reason": reason, "stub": stub})

    _output_candidates(candidates, args, output_dir)


def _output_candidates(candidates: list[dict], args, output_dir: Path):
    import re
    for item in candidates:
        t = item["transform"]
        name = t.get("name", "unknown")
        func_name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        print(f"\n{'='*60}")
        print(f"Transform: {name}  (file: {t.get('file', '?')})")
        print(f"Candidate: {item['is_candidate']}  ({item['reason']})")
        if item["stub"]:
            print(f"\n--- Generated stub ---")
            print(item["stub"])
        else:
            print("  [skipped — manual rewrite required]")

        if args.write and item["is_candidate"] and item["stub"]:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_file = output_dir / f"{func_name}.py"
            if out_file.exists():
                existing = out_file.read_text(encoding="utf-8")
                if existing == item["stub"]:
                    print(f"  [idempotent — {out_file} unchanged]")
                    continue
            out_file.write_text(item["stub"], encoding="utf-8")
            print(f"  Written to: {out_file}")


if __name__ == "__main__":
    main()
