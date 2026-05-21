# AGENTS.md

Project-level guidance for AI agents working in this project.

## Environment

- This project is managed with Poetry.
- Run commands and tests with Poetry from this directory.
- Keep this project separate from the parent `agent/` `uv` environment.

## Tests

- Place new tests under module-aligned folders instead of directly under `tests/`.
- Map source paths by directory. For example, `pyasic/web/antminer.py` should use `tests/test_web/test_antminer.py`.
- Use the path style `tests/test_<module_dir>/test_<module_file>.py`.
- Mirror the source module layout as closely as practical when choosing the test directory.
- Keep test filenames unique across the suite to avoid pytest import-file mismatch issues.
