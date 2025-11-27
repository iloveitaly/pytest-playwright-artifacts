"""Pytest plugin for enhanced Playwright testing with artifact capture."""

from pytest_playwright_artifacts.plugin import (
    PlaywrightConfig,
    StructuredConsoleLog,
    _should_ignore_console_log,
    assert_no_console_errors,
    extract_structured_log,
    format_console_msg,
    pytest_addoption,
    pytest_configure,
    pytest_runtest_makereport,
)

__all__ = [
    "PlaywrightConfig",
    "StructuredConsoleLog",
    "_should_ignore_console_log",
    "assert_no_console_errors",
    "extract_structured_log",
    "format_console_msg",
    "pytest_addoption",
    "pytest_configure",
    "pytest_runtest_makereport",
]
