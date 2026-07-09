# Fixture Modules

This directory is reserved for extracting cohesive fixture modules out of `src/tests/conftest.py`.

Keep the migration incremental:

- Move one cohesive fixture group at a time.
- Preserve existing fixture names unless the call sites are migrated in the same change.
- Re-export migrated fixtures from `conftest.py` while older tests still import them implicitly.
- Keep generated keys, config files, and temporary resources local to the fixture module that owns them.

Suggested modules are documented in `src/tests/README.md`.
