"""Pytest plugin for enhanced Playwright testing with artifact capture."""

from pytest_playwright_artifacts.plugin import (
    PlaywrightConfig,
    StructuredConsoleLog,
    assert_no_console_errors,
    pytest_addoption,
    pytest_configure,
    pytest_runtest_makereport,
)

__all__ = [
    "PlaywrightConfig",
    "StructuredConsoleLog",
    "assert_no_console_errors",
    "pytest_addoption",
    "pytest_configure",
    "pytest_runtest_makereport",
]
