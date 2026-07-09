# Migration Planning Scripts

## Available Scripts

These scripts ship with the skill in this `scripts/` directory.

---

### `trx_inventory.py`

Inventories all TRX transform classes in a project.

**Usage:**
```bash
python scripts/trx_inventory.py <trx-project-path> --output inventory.json
```

**Output:** A list of transform classes with their `create_entities` method signatures, entity strings used, and settings accessed.

---

### `trx_contract.py`

Extracts the source migration contract from decorator metadata, CSV metadata,
and wrapper dispatch calls.

**Usage:**
```bash
python scripts/trx_contract.py <trx-project-path> --output source-contract.json
```

**Output:** JSON with transform IDs, decorator metadata, output entities,
wrapper dispatch calls, and `csv_output_drift` warnings when wrapper output
arguments disagree with CSV/discovery metadata.

---

### `trx_migration_report.py`

Generates a structured migration report for a TRX project.

**Usage:**
```bash
python scripts/trx_migration_report.py inventory.json --output migration-report-draft.md
```

**Output:** A Markdown migration report with transform mapping table, entity mapping, difficulty classification, and flagged idioms.

---

### `std_entity_lookup.py`

Maps TRX entity strings found in the project to standard `maltego.entities` classes.

**Usage:**
```bash
python scripts/std_entity_lookup.py <entity-name-or-type>
```

**Output:** A mapping table: TRX entity string → SDK class → import statement. Flags unknown entity strings.

---

## Usage in Migration Planning

Run the project-level scripts in sequence for a complete read-only analysis,
then look up unknown entity wire types individually:

```bash
python scripts/trx_contract.py <trx-project-path> --output source-contract.json
python scripts/trx_inventory.py <trx-project-path> --output inventory.json
python scripts/trx_migration_report.py inventory.json --output migration-report-draft.md
python scripts/std_entity_lookup.py maltego.Phrase
```

These scripts are **read-only** — they do not modify any source files.
