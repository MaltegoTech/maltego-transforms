#!/usr/bin/env python3
"""
trx_migration_report.py — Generate a migration report from a TRX inventory JSON.

Reads the JSON produced by trx_inventory.py and emits:
  - A Markdown migration report (PRP-style)
  - An optional JSON summary

CLI: python trx_migration_report.py <inventory.json> [--output report.md] [--json-summary summary.json]
"""

import argparse
import json
from pathlib import Path

# TRX class → SDK pattern mapping
TRX_CLASS_TO_SDK: dict[str, str] = {
    "DiscoverableTransform": "@register_transform async function",
    "MaltegoTransform": "@register_transform async function",
    "Transform": "@register_transform async function",
}

# TRX entity wire-type → SDK entity class
ENTITY_WIRE_TO_SDK: dict[str, str] = {
    "maltego.Phrase": "from maltego.entities import Phrase",
    "maltego.DNSName": "from maltego.entities import DNSName",
    "maltego.IPv4Address": "from maltego.entities import IPv4Address",
    "maltego.Domain": "from maltego.entities import Domain",
    "maltego.Person": "from maltego.entities import Person",
    "maltego.EmailAddress": "from maltego.entities import EmailAddress",
    "maltego.PhoneNumber": "from maltego.entities import PhoneNumber",
    "maltego.URL": "from maltego.entities import URL",
    "maltego.Website": "from maltego.entities import Website",
    "maltego.Alias": "from maltego.entities import Alias",
}


def _risk(transform: dict) -> str:
    """Classify a transform as simple / medium / complex."""
    if transform.get("overlays") or transform.get("links") or transform.get("properties"):
        return "complex"
    if transform.get("oauth_settings") or transform.get("ui_messages") or transform.get("exceptions"):
        return "medium"
    if transform.get("settings"):
        return "medium"
    return "simple"


def generate_report(inventory: dict) -> tuple[str, dict]:
    """Return (markdown_text, summary_dict)."""
    transforms = inventory.get("transforms", [])
    summary = inventory.get("summary", {})
    project_path = inventory.get("project_path", "unknown")

    lines: list[str] = []

    lines.append("# TRX → SDK Migration Report")
    lines.append("")
    lines.append(f"**Project:** `{project_path}`")
    lines.append(f"**Total transforms:** {summary.get('total_transforms', len(transforms))}")
    lines.append(f"**Has OAuth:** {summary.get('has_oauth', False)}")
    lines.append(f"**Has overlays:** {summary.get('has_overlays', False)}")
    lines.append(f"**Has links:** {summary.get('has_links', False)}")
    lines.append("")

    # --- Transform mapping table ---
    lines.append("## Transform-by-Transform Mapping")
    lines.append("")
    lines.append("| Transform | File | TRX Base Class | SDK Pattern | Risk |")
    lines.append("|-----------|------|----------------|----------------|------|")
    risk_summary: dict[str, list[str]] = {"simple": [], "medium": [], "complex": []}
    for t in transforms:
        name = t.get("name", "?")
        file_ = t.get("file", "?")
        bases = ", ".join(t.get("base_classes", [])) or "?"
        sdk_pattern = TRX_CLASS_TO_SDK.get(
            bases.split(",")[0].strip().split(".")[-1],
            "@register_transform async function"
        )
        risk = _risk(t)
        risk_summary[risk].append(name)
        lines.append(f"| `{name}` | `{file_}` | `{bases}` | `{sdk_pattern}` | **{risk}** |")
    lines.append("")

    # --- Entity string mapping table ---
    lines.append("## Entity Wire-Type → SDK Entity Class Mapping")
    lines.append("")
    lines.append("| TRX Entity String | SDK Import |")
    lines.append("|-------------------|---------------|")
    for wire in sorted(summary.get("entity_strings", [])):
        sdk_import = ENTITY_WIRE_TO_SDK.get(wire, f"Custom entity — check for `{wire.split('.')[-1]}`")
        lines.append(f"| `{wire}` | `{sdk_import}` |")
    # Also list all known mappings not seen in project (for reference)
    seen = set(summary.get("entity_strings", []))
    not_seen = [w for w in ENTITY_WIRE_TO_SDK if w not in seen]
    if not_seen:
        lines.append("")
        lines.append("_Additional standard entities available (not used in this project):_")
        for wire in not_seen:
            lines.append(f"- `{wire}` → `{ENTITY_WIRE_TO_SDK[wire]}`")
    lines.append("")

    # --- Migration idiom taxonomy ---
    lines.append("## Migration Idiom Taxonomy")
    lines.append("")
    idioms: dict[str, list[str]] = {
        "overlays": [],
        "links": [],
        "properties": [],
        "ui_messages": [],
        "exceptions": [],
        "oauth_settings": [],
    }
    for t in transforms:
        name = t.get("name", "?")
        for key in idioms:
            if t.get(key):
                idioms[key].append(name)

    for idiom, affected in idioms.items():
        if affected:
            lines.append(f"### {idiom.replace('_', ' ').title()}")
            lines.append(f"Affects: {', '.join(f'`{n}`' for n in affected)}")
            if idiom == "overlays":
                lines.append("ℹ️ Entity overlays (`addOverlayRow`) map to `entity.add_overlay()` in SDK.")
            elif idiom == "links":
                lines.append("⚠️ Link customization API differs in SDK — review `MaltegoGraph.add_link()`.")
            elif idiom == "properties":
                lines.append("ℹ️ Properties map to entity field definitions in SDK.")
            elif idiom == "ui_messages":
                lines.append("ℹ️ Use `context.log.inform()` / `.debug()` / `.partial()` / `.fatal()` for SDK user-visible messages.")
            elif idiom == "exceptions":
                lines.append("ℹ️ Raise `MaltegoException` instead of `response.addException()`.")
            elif idiom == "oauth_settings":
                lines.append("⚠️ OAuth flow is different in SDK — see OAuth middleware docs.")
            lines.append("")

    # --- Risk classification summary ---
    lines.append("## Risk Classification Summary")
    lines.append("")
    for risk_level in ("simple", "medium", "complex"):
        names = risk_summary[risk_level]
        if names:
            lines.append(f"**{risk_level.title()} ({len(names)}):** {', '.join(f'`{n}`' for n in names)}")
    lines.append("")

    # --- Parity expectations ---
    lines.append("## Parity Expectations")
    lines.append("")
    lines.append("The following behaviours should work identically after migration:")
    lines.append("- Input entity value available via `entity.value` (was `request.Value`)")
    lines.append("- Output entities added to `MaltegoGraph` (was `response.addEntity()`)")
    lines.append("- Transform settings available via `settings.get('key')` (was `request.getTransformSetting()`; inject as `settings: Dict[str, Any]` param)")
    lines.append("- Transform discovery and registration via `@register_transform` decorator")
    lines.append("")

    # --- Suggested manual decisions ---
    lines.append("## Suggested Manual Decisions")
    lines.append("")
    lines.append("1. **Entity class ownership**: Decide whether to use standard `maltego.entities` classes or define custom entity classes.")
    lines.append("2. **Settings migration**: Map each TRX transform setting to a Pydantic settings model field.")
    if summary.get("has_oauth"):
        lines.append("3. **OAuth flow**: Replace `getOAuthToken()` calls with SDK OAuth middleware.")
    if summary.get("has_overlays"):
        lines.append("4. **Overlays**: Determine if overlays are required; implement via custom entity properties or drop feature.")
    if summary.get("has_links"):
        lines.append("5. **Links**: Port link customization to `MaltegoGraph.add_link()` API.")
    lines.append("")

    # --- Focused references ---
    lines.append("## Suggested References for Implementer Skill")
    lines.append("")
    lines.append("- SDK overview: `https://docs.maltego.com/en/support/solutions/articles/15000062349-maltego-transforms-sdk-overview`")
    lines.append("- SDK quickstart: Freshdesk article `Writing Your First Transform (Quickstart)`")
    lines.append("- Transform decorator: Freshdesk article `Moving from TRX to the current SDK`")
    lines.append("- Standard entities: Freshdesk article `Standard Entities Overview`")
    lines.append("- Settings: Freshdesk article `Transform Settings`")
    lines.append("- Graph / entity features: Freshdesk article `Entity Features (Overlays, Links, Notes)`")
    if summary.get("has_oauth"):
        lines.append("- OAuth: Freshdesk article `OAuth Authentication`")
    lines.append("")

    markdown = "\n".join(lines)

    json_summary = {
        "project_path": project_path,
        "total_transforms": len(transforms),
        "risk_simple": risk_summary["simple"],
        "risk_medium": risk_summary["medium"],
        "risk_complex": risk_summary["complex"],
        "entity_wire_types": summary.get("entity_strings", []),
        "unique_settings": summary.get("unique_settings", []),
        "has_oauth": summary.get("has_oauth", False),
        "has_overlays": summary.get("has_overlays", False),
        "has_links": summary.get("has_links", False),
        "migration_idioms": {k: v for k, v in idioms.items() if v},
    }

    return markdown, json_summary


def main():
    parser = argparse.ArgumentParser(description="Generate migration report from TRX inventory JSON.")
    parser.add_argument("inventory", help="Path to inventory.json produced by trx_inventory.py.")
    parser.add_argument("--output", metavar="FILE", help="Write Markdown report to FILE.")
    parser.add_argument("--json-summary", metavar="FILE", help="Write JSON summary to FILE.")
    args = parser.parse_args()

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    markdown, json_summary = generate_report(inventory)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    if args.json_summary:
        Path(args.json_summary).write_text(json.dumps(json_summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
