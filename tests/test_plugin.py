"""Tests for pytest-playwright-artifacts plugin."""

import re
from typing import cast

import pytest
from playwright.sync_api import Page

from pytest_playwright_artifacts import assert_no_console_errors
from pytest_playwright_artifacts.plugin import (
    PlaywrightConfig,
    StructuredConsoleLog,
)


def test_console_logging_capture(page: Page, request: pytest.FixtureRequest):
    """Test that console messages are captured."""
    page.set_content("<h1>Test</h1>")
    page.evaluate("console.log('test message')")
    page.evaluate("console.warn('warning message')")

    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])

    assert len(logs) >= 2
    assert any(log["type"] == "log" for log in logs)
    assert any(log["type"] == "warning" for log in logs)


def test_console_error_detection(page: Page, request: pytest.FixtureRequest):
    """Test that console errors are detected by assert_no_console_errors."""
    page.set_content("<h1>Test</h1>")
    page.evaluate("console.error('error message')")

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(request)


def test_no_console_errors_passes(page: Page, request: pytest.FixtureRequest):
    """Test that assert_no_console_errors passes when no errors."""
    page.set_content("<h1>Test</h1>")
    page.evaluate("console.log('test message')")

    assert_no_console_errors(request)


def test_console_ignore_patterns(
    page: Page, request: pytest.FixtureRequest, pytestconfig
):
    """Test console log filtering with ignore patterns."""
    page.set_content("<h1>Test</h1>")
    page.evaluate("console.log('should be captured')")
    page.evaluate("console.log('Invalid Sentry Dsn: something')")

    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])

    log_texts = [log["text"] for log in logs]
    assert "should be captured" in log_texts

    if hasattr(pytestconfig, "_playwright_console_ignore_patterns"):
        patterns = pytestconfig._playwright_console_ignore_patterns
        if any(p.pattern == "Invalid Sentry Dsn:.*" for p in patterns):
            assert "Invalid Sentry Dsn: something" not in log_texts


def test_ansi_stripping():
    """Test that ANSI escape sequences are stripped."""
    from pytest_playwright_artifacts.plugin import strip_ansi

    text_with_ansi = "\x1b[31mRed text\x1b[0m"
    clean_text = strip_ansi(text_with_ansi)

    assert clean_text == "Red text"
    assert "\x1b" not in clean_text


def test_sanitize_for_artifacts():
    """Test sanitization of test node IDs for directory names."""
    from pytest_playwright_artifacts.plugin import sanitize_for_artifacts

    nodeid = "tests/test_file.py::TestClass::test_method[param]"
    sanitized = sanitize_for_artifacts(nodeid)

    assert "/" not in sanitized
    assert "::" not in sanitized
    assert "[" not in sanitized
    assert "]" not in sanitized
    assert re.match(r"^[A-Za-z0-9-]+$", sanitized)


def test_format_console_msg():
    """Test console message formatting."""
    from pytest_playwright_artifacts.plugin import format_console_msg

    msg: StructuredConsoleLog = {
        "type": "log",
        "text": "test message",
        "args": ["arg1", "arg2"],
        "location": {"url": "http://example.com", "lineNumber": 1},
    }

    formatted = format_console_msg(msg)

    assert "Type: log" in formatted
    assert "Text: test message" in formatted
    assert "arg1" in formatted
    assert "arg2" in formatted


def test_plugin_without_page_fixture(request: pytest.FixtureRequest):
    """Test that plugin gracefully handles tests without page fixture."""
    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])

    assert logs == []
