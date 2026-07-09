# Implementation Scripts

## Available Scripts

This script ships with the skill in this `scripts/` directory.

---

### `trx_to_sdk_candidates.py`

Safe rewrite tool for TRX-to-SDK migration. Generates SDK candidate files from TRX transform classes without modifying originals.

**Usage:**
```bash
# Dry run — inspect output without writing files
python scripts/trx_to_sdk_candidates.py <project-path>

# Write candidate files to a separate output directory
python scripts/trx_to_sdk_candidates.py <project-path> --report migration-report.json --output-dir ./migrated --write

# Inspect only transforms or entities after generation by reviewing the printed candidate sections
python scripts/trx_to_sdk_candidates.py <project-path> --report migration-report.json
```

**Safety rules:**
- Omit `--write` first to review generated output; dry-run is the default.
- `--write` requires `--report` and writes only to `--output-dir`.
- `--output-dir` must be outside the original source tree.
- Never overwrite existing SDK files — use new filenames.
- Review generated candidates before committing.
- Generated code is a starting point — review for correctness.

---

## Usage in Migration Implementation

1. Read the migration plan (from `maltego-trx-migration-planner`).
2. Run `trx_to_sdk_candidates.py <project-path>` for Simple transforms.
3. Review output, accept or modify.
4. Re-run with `--report <summary.json> --output-dir <new-dir> --write` if you want generated files.
5. Syntax-check: `python -m py_compile <file>`.
6. Move to next transform batch.
