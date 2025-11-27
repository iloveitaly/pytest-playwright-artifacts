"""Test pytest-playwright-artifacts."""

import pytest_playwright_artifacts


def test_import() -> None:
    """Test that the  can be imported."""
    assert isinstance(pytest_playwright_artifacts.__name__, str)
