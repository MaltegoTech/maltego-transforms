#!/usr/bin/env python3
"""Generate a release SBOM for the built SDK artifact set."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


DEFAULT_OUTPUT = Path("dist/maltego-transforms-sbom.cdx.json")
CYCLONEDX_BINARIES = (
    "cyclonedx-py",  # cyclonedx-bom 7.x entrypoint
    "cyclonedx-bom",  # older entrypoint name, kept as a helpful fallback
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="generate_sbom",
        description="Generate a CycloneDX JSON SBOM for release artifacts.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"SBOM output path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def resolve_output_path(output: Optional[str]) -> Path:
    output_path = Path(output) if output is not None else DEFAULT_OUTPUT
    if output_path.is_absolute():
        raise ValueError("SBOM output path must be relative.")
    if ".." in output_path.parts or output_path.parts[:1] != ("dist",):
        raise ValueError("SBOM output path must stay under the dist directory.")
    return output_path


def find_cyclonedx_binary() -> Optional[str]:
    for binary in CYCLONEDX_BINARIES:
        path = shutil.which(binary)
        if path is not None:
            return path
    return None


def main() -> int:
    args = parse_args()
    try:
        output_path = resolve_output_path(args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cyclonedx = find_cyclonedx_binary()
    if cyclonedx is None:
        print(
            "cyclonedx-py is required to generate the release SBOM. "
            "Install the cyclonedx-bom dev dependency in the release pipeline image.",
            file=sys.stderr,
        )
        return 2

    command = [
        cyclonedx,
        "poetry",
        "--no-dev",
        "--output-reproducible",
        "--output-format",
        "JSON",
        "--output-file",
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
