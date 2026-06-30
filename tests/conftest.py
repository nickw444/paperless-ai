"""Pytest configuration and shared fixtures."""

import os

# Ensure required settings exist when tests import application modules.
os.environ.setdefault("PAPERLESS_URL", "http://localhost:8000")
os.environ.setdefault("PAPERLESS_API_TOKEN", "test-token")
