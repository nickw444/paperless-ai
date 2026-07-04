"""Shared pytest configuration."""

import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

os.environ.setdefault("PAPERLESS_API_TOKEN", "test-token")
os.environ.setdefault("PAPERLESS_AI_CONFIG_FILE", str(FIXTURES_DIR / "config.yaml"))
