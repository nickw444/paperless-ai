"""Shared pytest configuration."""

import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

os.environ.setdefault("PAPERLESS_URL", "http://paperless.example")
os.environ.setdefault("PAPERLESS_API_TOKEN", "test-token")
os.environ.setdefault(
    "METADATA_GUIDANCE_FILE",
    str(FIXTURES_DIR / "metadata_guidance.yaml"),
)
