set windows-shell := ["powershell", "-NoProfile", "-Command"]

# Default: list tasks
default:
    @just --list

# Run tests
test:
    uv run pytest

# Release a version (bump version number, update lock file)
bump:
    uv run cz bump
    uv lock

# Generate changelog
changelog:
    uv run git-cliff --latest

# Install pre-commit hooks
hooks:
    uv run prek install

# Lint
lint:
    uv run ruff check . --fix

# Format code
format:
    uv run ruff format .

# Type check
check:
    uv run basedpyright

# Update pre-commit hooks
update:
    uv run prek auto-update
