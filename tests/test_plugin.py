"""Tests for the pytest-playwright-artifacts plugin."""

import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from pytest_playwright_artifacts.plugin import (
    _compile_ignore_patterns,
    _should_ignore_console_log,
    assert_no_console_errors,
    extract_failure_info,
    extract_structured_log,
    format_console_msg,
    strip_ansi,
    write_console_logs,
    write_failure_summary,
)


def test_strip_ansi():
    """Verify ANSI escape sequences are removed."""
    text_with_ansi = "\x1b[31mRed Text\x1b[0m"
    assert strip_ansi(text_with_ansi) == "Red Text"

    text_without_ansi = "Plain Text"
    assert strip_ansi(text_without_ansi) == "Plain Text"


def test_format_console_msg():
    """Verify console message formatting."""
    msg = {
        "type": "log",
        "text": "test message",
        "args": ["arg1", "arg2"],
        "location": {"url": "http://example.com", "lineNumber": 10},
    }

    formatted = format_console_msg(msg)
    assert "Type: log" in formatted
    assert "Text: test message" in formatted
    assert "Args: arg1, arg2" in formatted


def test_extract_structured_log():
    """Verify console message extraction."""
    mock_msg = Mock()
    mock_msg.type = "error"
    mock_msg.text = "error message"
    mock_msg.location = {"url": "http://example.com", "lineNumber": 5}

    mock_arg = Mock()
    mock_arg.json_value.return_value = "test_value"
    mock_msg.args = [mock_arg]

    result = extract_structured_log(mock_msg)

    assert result["type"] == "error"
    assert result["text"] == "error message"
    assert result["args"] == ["test_value"]
    assert result["location"] == {"url": "http://example.com", "lineNumber": 5}


def test_compile_ignore_patterns():
    """Verify ignore patterns are compiled from config."""
    mock_config = Mock()
    # Explicitly set CLI option to None so it falls back to INI
    mock_config.option.playwright_console_ignore = None
    mock_config.getini.return_value = ["pattern1.*", "pattern2.*", "pattern1.*"]

    patterns = _compile_ignore_patterns(mock_config)

    assert len(patterns) == 2
    assert all(isinstance(p, re.Pattern) for p in patterns)


def test_should_ignore_console_log_with_patterns():
    """Verify console logs are filtered based on patterns."""
    log = {
        "type": "log",
        "text": "ignored pattern message",
        "args": [],
        "location": {},
    }

    patterns = [re.compile("ignored.*pattern")]
    assert _should_ignore_console_log(log, patterns) is True


def test_should_ignore_console_log_without_match():
    """Verify console logs are not filtered when no patterns match."""
    log = {
        "type": "log",
        "text": "visible message",
        "args": [],
        "location": {},
    }

    patterns = [re.compile("ignored.*pattern")]
    assert _should_ignore_console_log(log, patterns) is False


def test_should_ignore_console_log_no_patterns():
    """Verify console logs are not filtered when no patterns configured."""
    log = {
        "type": "log",
        "text": "any message",
        "args": [],
        "location": {},
    }

    assert _should_ignore_console_log(log, []) is False


def test_assert_no_console_errors_raises():
    """Verify assert_no_console_errors raises when errors present."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {"type": "error", "text": "error message", "args": [], "location": {}},
        ]
    }
    mock_request.config = mock_config

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(mock_request)


def test_assert_no_console_errors_passes():
    """Verify assert_no_console_errors passes when no errors."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {"type": "log", "text": "info message", "args": [], "location": {}},
        ]
    }
    mock_request.config = mock_config

    assert_no_console_errors(mock_request)


def test_assert_no_console_errors_no_logs():
    """Verify assert_no_console_errors passes when no logs at all."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {}
    mock_request.config = mock_config

    assert_no_console_errors(mock_request)


def test_extract_failure_info_with_reprcrash():
    mock_rep = Mock()
    mock_rep.longrepr.reprcrash.message = "AssertionError: test failed"
    mock_rep.longrepr.reprcrash.path = "/path/to/test.py"
    mock_rep.longrepr.reprcrash.lineno = 42
    mock_rep.longreprtext = "Full traceback text"

    mock_call = Mock()
    mock_item = Mock()
    mock_item.location = ("test.py", 10, "test_function")

    result = extract_failure_info(mock_rep, mock_call, mock_item)

    assert result["error_message"] == "AssertionError: test failed"
    assert result["error_file"] == "/path/to/test.py"
    assert result["error_line"] == 42
    assert result["longrepr_text"] == "Full traceback text"


def test_extract_failure_info_fallback_excinfo():
    mock_rep = Mock()
    mock_rep.longrepr = None

    mock_call = Mock()
    mock_call.excinfo.exconly.return_value = "ValueError: something went wrong"

    mock_item = Mock()
    mock_item.location = ("test.py", 10, "test_function")

    result = extract_failure_info(mock_rep, mock_call, mock_item)

    assert result["error_message"] == "ValueError: something went wrong"
    assert result["error_file"] == "test.py"
    assert result["error_line"] == 10


def test_extract_failure_info_fallback_item_location():
    mock_rep = Mock()
    mock_rep.longrepr.reprcrash = None
    mock_rep.longreprtext = "Some error text"

    mock_call = Mock()
    mock_call.excinfo = None

    mock_item = Mock()
    mock_item.location = ("test_module.py", 25, "test_func")

    result = extract_failure_info(mock_rep, mock_call, mock_item)

    assert result["error_file"] == "test_module.py"
    assert result["error_line"] == 25


def test_extract_failure_info_strips_ansi():
    mock_rep = Mock()
    mock_rep.longrepr.reprcrash.message = "\x1b[31mRed Error\x1b[0m"
    mock_rep.longrepr.reprcrash.path = "/path/to/test.py"
    mock_rep.longrepr.reprcrash.lineno = 42
    mock_rep.longreprtext = "\x1b[31mFull traceback\x1b[0m"

    mock_call = Mock()
    mock_item = Mock()
    mock_item.location = ("test.py", 10, "test_function")

    result = extract_failure_info(mock_rep, mock_call, mock_item)

    assert result["error_message"] == "Red Error"
    assert result["longrepr_text"] == "Full traceback"


def test_write_failure_summary(tmp_path):
    mock_item = Mock()
    mock_item.nodeid = "test_module.py::test_function"

    mock_rep = Mock()
    mock_rep.when = "call"

    failure_info = {
        "error_message": "AssertionError: test failed",
        "error_file": "test_module.py",
        "error_line": 42,
        "longrepr_text": "Full traceback here",
    }

    write_failure_summary(tmp_path, mock_item, mock_rep, failure_info)

    failure_file = tmp_path / "failure.txt"
    assert failure_file.exists()

    content = failure_file.read_text()
    assert "test_module.py::test_function" in content
    assert "call" in content
    assert "AssertionError: test failed" in content
    assert "test_module.py:42" in content
    assert "Full traceback here" in content


def test_write_failure_summary_missing_fields(tmp_path):
    mock_item = Mock()
    mock_item.nodeid = "test_module.py::test_function"

    mock_rep = Mock()
    mock_rep.when = "setup"

    failure_info = {
        "error_message": None,
        "error_file": None,
        "error_line": None,
        "longrepr_text": None,
    }

    write_failure_summary(tmp_path, mock_item, mock_rep, failure_info)

    failure_file = tmp_path / "failure.txt"
    assert failure_file.exists()

    content = failure_file.read_text()
    assert "test_module.py::test_function" in content
    assert "setup" in content


def test_write_console_logs(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {"type": "log", "text": "message 1", "args": [], "location": {}},
            {"type": "error", "text": "message 2", "args": ["arg"], "location": {}},
        ]
    }

    write_console_logs(tmp_path, mock_config, "test_nodeid")

    logs_file = tmp_path / "console_logs.log"
    assert logs_file.exists()

    content = logs_file.read_text()
    assert "message 1" in content
    assert "message 2" in content
    assert "test_nodeid" not in mock_config._playwright_console_logs


def test_write_console_logs_no_logs(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {}

    write_console_logs(tmp_path, mock_config, "test_nodeid")

    logs_file = tmp_path / "console_logs.log"
    assert not logs_file.exists()


def test_pytest_configure():
    from unittest.mock import patch

    from pytest_playwright_artifacts.plugin import pytest_configure

    mock_config = Mock()

    with patch(
        "pytest_playwright_artifacts.plugin._compile_ignore_patterns", return_value=[]
    ):
        pytest_configure(mock_config)

        assert hasattr(mock_config, "_playwright_console_logs")
        assert isinstance(mock_config._playwright_console_logs, dict)
        assert hasattr(mock_config, "_playwright_console_ignore_patterns")
        assert isinstance(mock_config._playwright_console_ignore_patterns, list)


def test_plugin_loads():
    """Verify the plugin loads without errors."""
    from pytest_playwright_artifacts import plugin

    assert hasattr(plugin, "pytest_configure")
    assert hasattr(plugin, "pytest_addoption")
    assert hasattr(plugin, "pytest_runtest_makereport")
    assert hasattr(plugin, "playwright_console_logging")
