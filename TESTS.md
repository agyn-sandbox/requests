# TESTS

This document describes how to set up a local environment and run the test suite for this repository.

Prerequisites:
- Python >= 3.10
- python -m pip
- Optional: make (for convenience targets)

Create and activate a virtual environment:
- python -m venv .venv
- Activate:
  - Linux/macOS: . .venv/bin/activate
  - Windows: .venv\Scripts\activate
- Upgrade pip: python -m pip install --upgrade pip

Install dependencies:
- Using Makefile: make init
- Or manually:
  - python -m pip install -r requirements-dev.txt
  - python -m pip install -e .

Run tests:
- Using Makefile: make test
- Or manually: python -m pytest tests

Coverage:
- Using Makefile: make coverage
- Or manually: python -m pytest --cov-config .coveragerc --verbose --cov-report term --cov-report xml --cov=src/requests tests

Offline vs. httpbin-dependent tests:
- Most tests rely on a local httpbin server provided by pytest-httpbin and are accessed via fixtures defined in tests/conftest.py:
  - httpbin and httpbin_secure wrap the plugin fixtures to normalize URLs.
  - nosan_server starts a local HTTPS server with a certificate lacking subjectAltName for specific TLS tests.
- A small number of tests reference the public httpbin.org service (e.g., in tests/test_lowlevel.py) and therefore require internet access. When running fully offline, you may need to deselect those specific tests.

Troubleshooting:
- Test server-related tests can be flaky under pytest-xdist; avoid using -n auto.
