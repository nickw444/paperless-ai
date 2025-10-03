# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

paperless-ai is a Python 3.13+ project in early development stages. The project uses uv for dependency management (indicated by pyproject.toml).

## Development Setup

The project requires Python 3.13 or higher (as specified in .python-version and pyproject.toml).

Install development dependencies:
```bash
uv sync --dev
```

## Running the Application

```bash
python main.py
```

## Linting and Formatting

The project uses ruff for linting and formatting.

Run linting:
```bash
uv run ruff check .
```

Run formatting:
```bash
uv run ruff format .
```

Check if code is formatted (without making changes):
```bash
uv run ruff format --check .
```

## Project Structure

Currently a minimal structure with a single entry point in `main.py`.
- Use dependency injection, never use monkey patching especially in tests.