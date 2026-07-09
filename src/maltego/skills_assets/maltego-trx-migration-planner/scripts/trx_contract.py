#!/usr/bin/env python3
"""
trx_contract.py — Extract a source behavior contract from a TRX project.

This is a read-only static analysis helper. It does not import project code.

CLI:
    python scripts/trx_contract.py <trx-project-path> [--output contract.json]
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from pathlib import Path
from typing import Any


TRX_BASE_CLASSES = {"DiscoverableTransform", "MaltegoTransform", "Transform"}


def _name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _string(node: ast.AST) -> str | None:
    value = _literal(node)
    return value if isinstance(value, str) else None


def _strings(node: ast.AST) -> list[str]:
    value = _literal(node)
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def _call_args(call: ast.Call) -> list[Any]:
    args = []
    for arg in call.args:
        value = _literal(arg)
        if isinstance(value, (str, int, float, bool)) or value is None:
            args.append(value)
        else:
            args.append(_name(arg) or "<dynamic>")
    return args


def _decorator_metadata(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if "register_transform" not in _name(decorator.func) and "registerTransform" not in _name(decorator.func):
            continue
        metadata["decorator"] = _name(decorator.func)
        positional = [_literal(arg) for arg in decorator.args]
        if positional:
            metadata["positional_args"] = positional
        for keyword in decorator.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg == "output_entities":
                metadata[keyword.arg] = _strings(keyword.value)
            else:
                value = _literal(keyword.value)
                metadata[keyword.arg] = value if value is not None else _name(keyword.value)
    return metadata


def _dispatch_calls(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    calls = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        args = _call_args(child)
        if len(args) < 2 or not isinstance(args[0], str) or not isinstance(args[1], str):
            continue
        call_name = _name(child.func)
        if call_name.split(".")[-1] in {
            "addEntity",
            "addProperty",
            "addUIMessage",
            "setLinkLabel",
            "setOverlay",
        }:
            continue
        calls.append(
            {
                "call": call_name,
                "args": args,
                "line": child.lineno,
            }
        )
    return calls


def _read_csv_contract(root: Path) -> list[dict[str, str]]:
    csv_path = root / "transforms.csv"
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "transform_id": (row.get("Transform id") or "").strip(),
                "description": (row.get("Description") or "").strip(),
                "input_entity": (row.get("Input type") or "").strip(),
                "transform_set": (row.get("Sets") or "").strip(),
                "output": (row.get("Output") or "").strip(),
            }
            for row in reader
            if row.get("Transform id")
        ]


def _normalise_output(value: str | None) -> str:
    if not value or value in {"None", "none"}:
        return ""
    if value.startswith("maltego.STIX2."):
        return value.removeprefix("maltego.STIX2.")
    return value


def _find_csv_row(
    csv_rows: list[dict[str, str]],
    *,
    description: str | None,
    input_entity: str | None,
    transform_set: str | None,
    wrapper_output_args: list[str],
) -> dict[str, str] | None:
    candidates = csv_rows
    if description:
        candidates = [row for row in candidates if row["description"] == description]
    if input_entity and len(candidates) != 1:
        narrowed = [row for row in candidates if row["input_entity"] == input_entity]
        if narrowed:
            candidates = narrowed
    if transform_set and len(candidates) != 1:
        narrowed = [row for row in candidates if row["transform_set"] == transform_set]
        if narrowed:
            candidates = narrowed
    if wrapper_output_args and len(candidates) != 1:
        wrapper_outputs = {_normalise_output(value) for value in wrapper_output_args}
        narrowed = [row for row in candidates if _normalise_output(row["output"]) in wrapper_outputs]
        if narrowed:
            candidates = narrowed
    return candidates[0] if len(candidates) == 1 else None


def _is_transform_class(node: ast.ClassDef) -> bool:
    bases = {_name(base).split(".")[-1] for base in node.bases}
    if bases.intersection(TRX_BASE_CLASSES):
        return True
    return bool(_decorator_metadata(node))


def _extract_transforms(root: Path, csv_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    transforms: list[dict[str, Any]] = []
    for py_file in sorted(root.rglob("*.py")):
        relative = py_file.relative_to(root).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_transform_class(node):
                continue
            metadata = _decorator_metadata(node)
            dispatch_calls = _dispatch_calls(node)
            output_args = [
                call["args"][1]
                for call in dispatch_calls
                if len(call["args"]) > 1 and isinstance(call["args"][1], str)
            ]
            unique_output_args = list(dict.fromkeys(output_args))
            csv_row = _find_csv_row(
                csv_rows,
                description=metadata.get("description"),
                input_entity=metadata.get("input_entity"),
                transform_set=metadata.get("transform_set"),
                wrapper_output_args=unique_output_args,
            )
            transforms.append(
                {
                    "class_name": node.name,
                    "file": relative,
                    "line": node.lineno,
                    "transform_id": csv_row["transform_id"] if csv_row else None,
                    "display_name": metadata.get("display_name"),
                    "description": metadata.get("description"),
                    "input_entity": metadata.get("input_entity") or (csv_row or {}).get("input_entity"),
                    "output_entities": metadata.get("output_entities", []),
                    "transform_set": metadata.get("transform_set") or (csv_row or {}).get("transform_set"),
                    "csv_output": (csv_row or {}).get("output"),
                    "decorator": metadata,
                    "dispatch_calls": dispatch_calls,
                    "wrapper_output_arg": unique_output_args[0] if unique_output_args else None,
                    "wrapper_output_args": unique_output_args,
                }
            )
    return transforms


def extract_contract(project_path: str) -> dict[str, Any]:
    root = Path(project_path).resolve()
    csv_rows = _read_csv_contract(root)
    transforms = _extract_transforms(root, csv_rows)

    drift = []
    missing_csv_rows = []
    multi_output_routes = []
    for transform in transforms:
        wrapper_outputs = [
            output
            for output in {_normalise_output(value) for value in transform.get("wrapper_output_args", [])}
            if output
        ]
        csv_output_raw = transform.get("csv_output")
        csv_output = _normalise_output(csv_output_raw)
        if transform.get("transform_id") is None:
            missing_csv_rows.append(
                {
                    "class_name": transform["class_name"],
                    "file": transform["file"],
                    "line": transform["line"],
                    "description": transform.get("description"),
                    "input_entity": transform.get("input_entity"),
                    "transform_set": transform.get("transform_set"),
                    "wrapper_output_args": transform.get("wrapper_output_args", []),
                }
            )
        if len(wrapper_outputs) > 1:
            multi_output_routes.append(
                {
                    "transform_id": transform.get("transform_id"),
                    "class_name": transform["class_name"],
                    "file": transform["file"],
                    "line": transform["line"],
                    "wrapper_output_args": transform.get("wrapper_output_args", []),
                    "csv_output": csv_output_raw or "",
                }
            )
        if csv_output_raw is not None and any(wrapper_output != csv_output for wrapper_output in wrapper_outputs):
            drift.append(
                {
                    "transform_id": transform.get("transform_id"),
                    "class_name": transform["class_name"],
                    "file": transform["file"],
                    "line": transform["line"],
                    "wrapper_output_arg": transform.get("wrapper_output_arg"),
                    "wrapper_output_args": transform.get("wrapper_output_args", []),
                    "csv_output": csv_output_raw or "",
                }
            )

    return {
        "project_path": str(root),
        "summary": {
            "csv_transforms": len(csv_rows),
            "total_transforms": len(transforms),
            "transforms_with_dispatch_args": sum(1 for item in transforms if item["dispatch_calls"]),
            "transforms_with_csv_output_drift": len(drift),
            "transforms_missing_csv_row": len(missing_csv_rows),
            "transforms_with_multiple_wrapper_outputs": len(multi_output_routes),
        },
        "warnings": {
            "csv_output_drift": drift,
            "missing_csv_row": missing_csv_rows,
            "multiple_wrapper_outputs": multi_output_routes,
        },
        "transforms": transforms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_path", help="TRX project path")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args(argv)

    contract = extract_contract(args.project_path)
    payload = json.dumps(contract, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
