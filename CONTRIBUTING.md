# Contributing to DataMendry

Thanks for helping improve data quality tools for everyone.

## Setup

1. Fork and clone the repository; install Python 3.11+.
2. Run `python -m pip install -r requirements-dev.txt`.
3. Run `python -m pytest -q` before and after changing code.
4. For API changes, add an integration test in `tests/test_api.py`. For engine changes, add cases in `tests/test_engine.py`.
5. Create a focused pull request describing motivation, behavior, risks, and tests performed.

## Good first contributions

- Better CSV import errors and text encoding support.
- Accessibility and keyboard testing for the user interface.
- Automated browser tests.
- Test cases for tricky whitespace, date, numeric, and CSV quoting inputs.
- Performance benchmarks with synthetic data.

## Data policy

Do not commit personal, customer, private, or regulated datasets, authentication tokens, generated SQLite files, or log files. Use `examples/` synthetic data and temporary directories.

## Design principles

Keep original data immutable, require explicit user choice before destructive changes, document performance trade-offs, and never silently impute unknown values.
