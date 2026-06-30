"""Shared pytest configuration."""

import os

os.environ.setdefault("PAPERLESS_URL", "http://paperless.example")
os.environ.setdefault("PAPERLESS_API_TOKEN", "test-token")
os.environ.setdefault("AI_AGENT", "codex")
