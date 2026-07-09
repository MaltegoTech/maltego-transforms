#!/usr/bin/env python3
"""
trx_inventory.py — Static AST-based inventory of TRX transform projects.

Parses Python files to discover transform classes, entity usage, settings,
UI messages, exceptions, overlays, links, and properties without importing
any project code. Safe to run on untrusted codebases.

CLI: python trx_inventory.py <project-path> [--output inventory.json]
"""

import argparse
import ast
import json
import sys
from pathlib import Path

TRX_BASE_CLASSES = {
    "DiscoverableTransform",
    "MaltegoTransform",
    "Transform",
}

ENTITY_STRING_PATTERN_PREFIXES = (
    "maltego.",
    "Maltego.",
)

# AST helper utilities


def _get_name(node) -> str:
    """Extract a dotted name string from an AST Name or Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return ""


def _get_string_value(node) -> str | None:
    """Return string value if the node is a string constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class TransformInventoryVisitor(ast.NodeVisitor):
    """Visits an AST and collects transform-related information."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.transforms: list[dict] = []
        self._current_class: dict | None = None
        self._imports: dict[str, str] = {}  # local name → full dotted name

    # ------------------------------------------------------------------
    # Import tracking

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            local = alias.asname if alias.asname else alias.name.split(".")[0]
            self._imports[local] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            local = alias.asname if alias.asname else alias.name
            self._imports[local] = f"{module}.{alias.name}"
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Class detection

    def visit_ClassDef(self, node: ast.ClassDef):
        bases = [_get_name(b) for b in node.bases]
        short_bases = [b.split(".")[-1] for b in bases]
        if any(b in TRX_BASE_CLASSES for b in short_bases):
            entry = {
                "name": node.name,
                "class": node.name,
                "file": self.filepath,
                "line": node.lineno,
                "base_classes": bases,
                "registry_registrations": [],
                "entity_imports": self._collect_entity_imports(),
                "entity_strings": [],
                "settings": [],
                "oauth_settings": [],
                "request_fields": [],
                "ui_messages": [],
                "exceptions": [],
                "overlays": [],
                "links": [],
                "properties": [],
            }
            prev = self._current_class
            self._current_class = entry
            self.generic_visit(node)
            self._current_class = prev
            self.transforms.append(entry)
        else:
            self.generic_visit(node)

    def _collect_entity_imports(self) -> list[str]:
        return [
            full
            for local, full in self._imports.items()
            if "entit" in full.lower()
        ]

    # ------------------------------------------------------------------
    # Call analysis within class bodies

    def visit_Call(self, node: ast.Call):
        if self._current_class is not None:
            self._analyse_call(node)
        self.generic_visit(node)

    def _analyse_call(self, node: ast.Call):
        func_name = _get_name(node.func)
        short = func_name.split(".")[-1]
        c = self._current_class

        # entity strings: response.addEntity("maltego.X")
        if short == "addEntity" and node.args:
            val = _get_string_value(node.args[0])
            if val and any(val.startswith(p) for p in ENTITY_STRING_PATTERN_PREFIXES):
                if val not in c["entity_strings"]:
                    c["entity_strings"].append(val)

        # settings
        if short == "getTransformSetting" and node.args:
            val = _get_string_value(node.args[0])
            if val and val not in c["settings"]:
                c["settings"].append(val)

        # oauth settings
        if short in ("getOAuthToken", "getOAuthSetting", "getOAuthAccessToken") and node.args:
            val = _get_string_value(node.args[0])
            entry = val or f"<{short}>"
            if entry not in c["oauth_settings"]:
                c["oauth_settings"].append(entry)
        elif "oauth" in short.lower() or "OAuth" in short:
            marker = short
            if marker not in c["oauth_settings"]:
                c["oauth_settings"].append(marker)

        # request fields: request.Value, request.Params, etc.
        if isinstance(node.func, ast.Attribute):
            obj_name = _get_name(node.func.value)
            if obj_name in ("request", "self.request"):
                field = node.func.attr
                if field not in c["request_fields"]:
                    c["request_fields"].append(field)

        # ui messages
        if short == "addUIMessage":
            msg = _get_string_value(node.args[0]) if node.args else None
            entry = {"text": msg or "<dynamic>", "line": node.lineno}
            c["ui_messages"].append(entry)

        # exceptions
        if short == "addException":
            msg = _get_string_value(node.args[0]) if node.args else None
            entry = {"text": msg or "<dynamic>", "line": node.lineno}
            c["exceptions"].append(entry)

        # overlays
        if short == "setOverlay":
            args = [_get_string_value(a) for a in node.args]
            c["overlays"].append({"args": args, "line": node.lineno})

        # links
        if short in ("addLink", "setLinkColor", "setLinkLabel", "setLinkThickness", "setLinkStyle"):
            c["links"].append({"call": short, "line": node.lineno})

        # properties
        if short == "addProperty":
            args = [_get_string_value(a) for a in node.args]
            c["properties"].append({"args": args, "line": node.lineno})

        # registry registrations
        if short in ("register_transform", "registerTransform"):
            args = [_get_string_value(a) for a in node.args]
            c["registry_registrations"].append({"call": short, "args": args, "line": node.lineno})

    def visit_Attribute(self, node: ast.Attribute):
        """Catch attribute accesses like request.Value."""
        if self._current_class is not None:
            if isinstance(node.value, ast.Name) and node.value.id in ("request",):
                field = node.attr
                c = self._current_class
                if field not in c["request_fields"]:
                    c["request_fields"].append(field)
        self.generic_visit(node)


def inventory_project(project_path: str) -> dict:
    """Walk all Python files and build an inventory dict."""
    root = Path(project_path).resolve()
    all_transforms: list[dict] = []

    for py_file in sorted(root.rglob("*.py")):
        relative = str(py_file.relative_to(root))
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        visitor = TransformInventoryVisitor(filepath=relative)
        visitor.visit(tree)
        all_transforms.extend(visitor.transforms)

    # Registry decorators: scan for @registry.register_transform on non-class functions
    # (already captured inside class bodies; here capture module-level)
    for py_file in sorted(root.rglob("*.py")):
        relative = str(py_file.relative_to(root))
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for dec in node.decorator_list:
                    dec_name = _get_name(dec) if not isinstance(dec, ast.Call) else _get_name(dec.func)
                    if "register_transform" in dec_name:
                        entry = {
                            "name": node.name,
                            "class": None,
                            "file": relative,
                            "line": node.lineno,
                            "base_classes": [],
                            "registry_registrations": [{"call": dec_name, "line": node.lineno}],
                            "entity_imports": [],
                            "entity_strings": [],
                            "settings": [],
                            "oauth_settings": [],
                            "request_fields": [],
                            "ui_messages": [],
                            "exceptions": [],
                            "overlays": [],
                            "links": [],
                            "properties": [],
                        }
                        all_transforms.append(entry)

    # Build summary
    all_entity_strings: list[str] = []
    all_settings: list[str] = []
    has_oauth = False
    has_overlays = False
    has_links = False
    for t in all_transforms:
        all_entity_strings.extend(t.get("entity_strings", []))
        all_settings.extend(t.get("settings", []))
        if t.get("oauth_settings"):
            has_oauth = True
        if t.get("overlays"):
            has_overlays = True
        if t.get("links"):
            has_links = True

    return {
        "project_path": str(root),
        "transforms": all_transforms,
        "summary": {
            "total_transforms": len(all_transforms),
            "entity_strings": sorted(set(all_entity_strings)),
            "unique_settings": sorted(set(all_settings)),
            "has_oauth": has_oauth,
            "has_overlays": has_overlays,
            "has_links": has_links,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Static inventory of TRX transform projects.")
    parser.add_argument("project_path", help="Path to the project root to scan.")
    parser.add_argument("--output", metavar="FILE", help="Write JSON output to FILE instead of stdout.")
    args = parser.parse_args()

    result = inventory_project(args.project_path)
    output = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
