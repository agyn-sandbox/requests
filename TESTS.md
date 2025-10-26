# TESTS

This document describes how to set up a local environment and run the test suite for this repository.

Prerequisites:
- Python >= 3.10
- pip
- Dependencies: pytest; optional pytest-cov

Setup:
- pip install -e .
- pip install -r requirements-dev.txt

Run tests:
- Unit tests: python -m pytest tests
- Coverage: python -m pytest --cov-config .coveragerc --verbose --cov-report term --cov-report xml --cov=src/requests tests

Troubleshooting:
- Test server-related tests can be flaky under pytest-xdist; avoid using `-n auto`.
- Some tests use httpbin and may require internet; skip network-dependent tests via markers if needed.

