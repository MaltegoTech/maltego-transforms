#!/usr/bin/env python3
"""
sdk_project_check.py — Validate an SDK project for common issues.

Checks:
- Syntax/imports for all .py files (via py_compile)
- Stale TRX imports (maltego_trx, maltego.server.v2, maltego.server.trx)
- Custom entity classes that may duplicate standard entities
- Missing @register_transform imports
- Optionally checks /api/v3/transforms and /api/v3/assets/entities discovery endpoints

CLI: python sdk_project_check.py <project-path> [--server-url http://localhost:8080]
"""

import argparse
import ast
import json
import py_compile
import sys
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

STALE_TRX_PATTERNS = [
    "import maltego_trx",
    "from maltego_trx",
    "from maltego.server.v2",
    "from maltego.server.trx",
]

KNOWN_ENTITY_TYPE_NAMES = {
    "maltego.Phrase", "maltego.DNSName", "maltego.IPv4Address", "maltego.Domain",
    "maltego.Person", "maltego.EmailAddress", "maltego.PhoneNumber", "maltego.URL",
    "maltego.Website", "maltego.Alias",
}

DEFAULT_FORBIDDEN_TERMS: tuple[str, ...] = ()


def check_file_syntax(py_file: Path) -> str | None:
    """Return error message if file has syntax errors, else None."""
    try:
        py_compile.compile(str(py_file), doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)


def find_stale_imports(py_file: Path) -> list[dict]:
    """Return list of stale TRX import occurrences."""
    results = []
    try:
        lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return results
    for i, line in enumerate(lines, 1):
        for pattern in STALE_TRX_PATTERNS:
            if pattern in line:
                results.append({"file": str(py_file), "line": i, "pattern": pattern, "text": line.strip()})
    return results


def find_duplicate_entity_classes(py_file: Path) -> list[dict]:
    """Find class definitions whose TYPE_NAME matches a known standard entity."""
    results = []
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except (SyntaxError, OSError):
        return results

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in ast.walk(node):
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "TYPE_NAME":
                            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                if item.value.value in KNOWN_ENTITY_TYPE_NAMES:
                                    results.append({
                                        "file": str(py_file),
                                        "line": node.lineno,
                                        "class": node.name,
                                        "type_name": item.value.value,
                                        "issue": "Duplicates a standard entity",
                                    })
    return results


def find_missing_register_transform_imports(py_file: Path) -> list[dict]:
    """Detect @register_transform usage without an import for it."""
    results = []
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except (SyntaxError, OSError):
        return results

    has_decorator = False
    has_import = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_str = ""
                if isinstance(dec, ast.Name):
                    dec_str = dec.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    dec_str = dec.func.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    dec_str = dec.func.attr
                if "register_transform" in dec_str:
                    has_decorator = True

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if "register_transform" in alias.name:
                    has_import = True

    if has_decorator and not has_import:
        results.append({
            "file": str(py_file),
            "issue": "Uses @register_transform but does not import it",
        })
    return results


def scan_internal_terms(path: Path, terms: list[str]) -> list[dict]:
    """Scan a directory for caller-supplied terms."""
    results = []
    if not terms:
        return results

    for py_file in path.rglob("*"):
        if not py_file.is_file():
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for term in terms:
            if term in text:
                results.append({"file": str(py_file), "term": term})
    return results


def check_server(server_url: str) -> dict:
    """Check discovery endpoints on a running transform server."""
    # Only ever fetch over http(s). urllib also supports file:// and other
    # schemes, so guard the (CLI-supplied) URL before opening it.
    if urlparse(server_url).scheme not in ("http", "https"):
        print(f"ERROR: refusing to fetch non-http(s) URL: {server_url}", file=sys.stderr)
        sys.exit(2)
    result: dict = {"server_url": server_url, "transforms": None, "entities": None, "error": None}
    for endpoint, key in [("/api/v3/transforms", "transforms"), ("/api/v3/assets/entities", "entities")]:
        url = server_url.rstrip("/") + endpoint
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result[key] = data
        except urllib.error.URLError as e:
            result["error"] = str(e)
            break
        except Exception as e:
            result["error"] = str(e)
            break
    return result


def check_project(
    project_path: str,
    server_url: str | None = None,
    forbidden_terms: list[str] | None = None,
) -> dict:
    root = Path(project_path).resolve()
    terms = list(forbidden_terms or DEFAULT_FORBIDDEN_TERMS)
    syntax_errors: list[dict] = []
    stale_imports: list[dict] = []
    duplicate_entities: list[dict] = []
    missing_imports: list[dict] = []

    for py_file in sorted(root.rglob("*.py")):
        err = check_file_syntax(py_file)
        if err:
            syntax_errors.append({"file": str(py_file), "error": err})

        stale_imports.extend(find_stale_imports(py_file))
        duplicate_entities.extend(find_duplicate_entity_classes(py_file))
        missing_imports.extend(find_missing_register_transform_imports(py_file))

    # Scan internal terms in skills/agents folders
    internal_issues: list[dict] = []
    for special_dir in [".agents", "skills", ".skills"]:
        target = root / special_dir
        if target.exists():
            internal_issues.extend(scan_internal_terms(target, terms))

    server_result: dict | None = None
    if server_url:
        server_result = check_server(server_url)

    result = {
        "project_path": str(root),
        "syntax_errors": syntax_errors,
        "stale_imports": stale_imports,
        "duplicate_entities": duplicate_entities,
        "missing_register_transform_imports": missing_imports,
        "internal_only_terms": internal_issues,
        "server_check": server_result,
        "summary": {
            "syntax_errors": len(syntax_errors),
            "stale_imports": len(stale_imports),
            "duplicate_entities": len(duplicate_entities),
            "missing_imports": len(missing_imports),
            "internal_issues": len(internal_issues),
            "has_issues": bool(syntax_errors or stale_imports or duplicate_entities or missing_imports or internal_issues),
        }
    }
    return result


def _render_text_report(data: dict) -> str:
    lines: list[str] = []
    lines.append(f"SDK Project Check: {data['project_path']}")
    lines.append("=" * 60)

    def section(title: str, items: list, item_fmt):
        lines.append(f"\n[{title}] ({len(items)} found)")
        if not items:
            lines.append("  ✓ None")
        for item in items:
            lines.append(f"  ✗ {item_fmt(item)}")

    section("Syntax Errors", data["syntax_errors"],
            lambda x: f"{x['file']}: {x['error']}")
    section("Stale TRX Imports", data["stale_imports"],
            lambda x: f"{x['file']}:{x['line']} — {x['text']}")
    section("Duplicate Standard Entities", data["duplicate_entities"],
            lambda x: f"{x['file']}:{x['line']} class {x['class']} shadows {x['type_name']}")
    section("Missing @register_transform Imports", data["missing_register_transform_imports"],
            lambda x: f"{x['file']}: {x['issue']}")
    section("Internal-Only Terms", data["internal_only_terms"],
            lambda x: f"{x['file']}: contains '{x['term']}'")

    if data.get("server_check"):
        sc = data["server_check"]
        lines.append(f"\n[Server Check] {sc['server_url']}")
        if sc.get("error"):
            lines.append(f"  ✗ Error: {sc['error']}")
        else:
            lines.append(f"  ✓ /transforms: {sc.get('transforms')}")
            lines.append(f"  ✓ /entities: {sc.get('entities')}")

    summary = data["summary"]
    lines.append(f"\n{'='*60}")
    lines.append(f"SUMMARY: {'ISSUES FOUND' if summary['has_issues'] else 'OK'}")
    lines.append(f"  Syntax errors: {summary['syntax_errors']}")
    lines.append(f"  Stale imports: {summary['stale_imports']}")
    lines.append(f"  Duplicate entities: {summary['duplicate_entities']}")
    lines.append(f"  Missing imports: {summary['missing_imports']}")
    lines.append(f"  Internal terms: {summary['internal_issues']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate an SDK project for common issues.")
    parser.add_argument("project_path", help="Path to the project root.")
    parser.add_argument("--server-url", metavar="URL",
                        help="Optional running transform server URL to check discovery endpoints.")
    parser.add_argument("--terms", nargs="*", default=[],
                        help="Caller-supplied terms to scan for in .agents, skills, and .skills directories.")
    args = parser.parse_args()

    data = check_project(args.project_path, server_url=args.server_url, forbidden_terms=args.terms)
    print(_render_text_report(data))
    print("\n--- JSON Summary ---")
    print(json.dumps(data["summary"], indent=2))


if __name__ == "__main__":
    main()
