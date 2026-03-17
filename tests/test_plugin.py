"""Tests for the pytest-playwright-artifacts plugin."""

from unittest.mock import Mock, patch, MagicMock

import pytest

from pytest_playwright_artifacts.assertions import assert_no_console_errors
from pytest_playwright_artifacts.plugin import (
    StructuredConsoleLog,
    _compile_entry,
    _compile_ignore_patterns,
    _is_playwright_timeout,
    _resolve_timeout_retries,
    _should_ignore_console_log,
    extract_failure_info,
    extract_structured_log,
    format_console_msg,
    pytest_report_teststatus,
    pytest_runtest_protocol,
    pytest_terminal_summary,
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
    import json

    msg = {
        "type": "log",
        "text": "test message",
        "args": ["arg1", "arg2"],
        "location": {"url": "http://example.com", "lineNumber": 10},
        "ignored": False,
    }

    formatted = format_console_msg(msg)
    parsed = json.loads(formatted)

    assert parsed["type"] == "log"
    assert parsed["text"] == "test message"
    assert parsed["args"] == ["arg1", "arg2"]
    assert parsed["location"] == {"url": "http://example.com", "lineNumber": 10}


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
    assert result["ignored"] is False


def test_compile_ignore_patterns():
    """Verify ignore patterns are compiled from config into callable predicates."""
    mock_config = Mock()
    # Explicitly set CLI option to None so it falls back to INI
    mock_config.option.playwright_console_ignore = None
    mock_config.getini.return_value = ["pattern1.*", "pattern2.*", "pattern1.*"]

    predicates = _compile_ignore_patterns(mock_config)

    assert len(predicates) == 2
    assert all(callable(p) for p in predicates)


def test_should_ignore_console_log_with_patterns():
    """Verify console logs are filtered based on patterns."""
    log = {
        "type": "log",
        "text": "ignored pattern message",
        "args": [],
        "location": {},
        "ignored": False,
    }

    predicates = [_compile_entry("ignored.*pattern")]
    assert _should_ignore_console_log(log, predicates) is True


def test_should_ignore_console_log_without_match():
    """Verify console logs are not filtered when no patterns match."""
    log = {
        "type": "log",
        "text": "visible message",
        "args": [],
        "location": {},
        "ignored": False,
    }

    predicates = [_compile_entry("ignored.*pattern")]
    assert _should_ignore_console_log(log, predicates) is False


def test_should_ignore_console_log_no_patterns():
    """Verify console logs are not filtered when no patterns configured."""
    log = {
        "type": "log",
        "text": "any message",
        "args": [],
        "location": {},
        "ignored": False,
    }

    assert _should_ignore_console_log(log, []) is False


def test_assert_no_console_errors_raises():
    """Verify assert_no_console_errors raises when errors present."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "error message",
                "args": [],
                "location": {},
                "ignored": False,
            },
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
            {
                "type": "log",
                "text": "info message",
                "args": [],
                "location": {},
                "ignored": False,
            },
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

    path = write_failure_summary(tmp_path, mock_item, mock_rep, failure_info)

    failure_file = tmp_path / "failure.txt"
    assert path == failure_file
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

    path = write_failure_summary(tmp_path, mock_item, mock_rep, failure_info)

    failure_file = tmp_path / "failure.txt"
    assert path == failure_file
    assert failure_file.exists()

    content = failure_file.read_text()
    assert "test_module.py::test_function" in content
    assert "setup" in content


def test_write_console_logs(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "log",
                "text": "message 1",
                "args": [],
                "location": {},
                "ignored": False,
            },
            {
                "type": "error",
                "text": "message 2",
                "args": ["arg"],
                "location": {},
                "ignored": False,
            },
        ]
    }

    path = write_console_logs(tmp_path, mock_config, "test_nodeid")

    logs_file = tmp_path / "console_logs.log"
    assert path == logs_file
    assert logs_file.exists()

    content = logs_file.read_text()
    assert "message 1" in content
    assert "message 2" in content
    assert "test_nodeid" not in mock_config._playwright_console_logs


def test_write_console_logs_no_logs(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {}

    path = write_console_logs(tmp_path, mock_config, "test_nodeid")

    logs_file = tmp_path / "console_logs.log"
    assert path is None
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
    assert hasattr(plugin, "pytest_runtest_protocol")
    assert hasattr(plugin, "pytest_report_teststatus")


def test_is_playwright_timeout_with_timeout_error():
    mock_report = Mock()
    mock_report.passed = False
    mock_report.skipped = False
    mock_report.longrepr = (
        "playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded."
    )

    assert _is_playwright_timeout(mock_report) is True


def test_is_playwright_timeout_with_other_error():
    mock_report = Mock()
    mock_report.passed = False
    mock_report.skipped = False
    mock_report.longrepr = "AssertionError: assert 1 == 2"

    assert _is_playwright_timeout(mock_report) is False


def test_is_playwright_timeout_when_passed():
    mock_report = Mock()
    mock_report.passed = True
    mock_report.skipped = False

    assert _is_playwright_timeout(mock_report) is False


def test_is_playwright_timeout_when_skipped():
    mock_report = Mock()
    mock_report.passed = False
    mock_report.skipped = True

    assert _is_playwright_timeout(mock_report) is False


def test_is_playwright_timeout_no_longrepr():
    mock_report = Mock()
    mock_report.passed = False
    mock_report.skipped = False
    mock_report.longrepr = None

    assert _is_playwright_timeout(mock_report) is False


def test_resolve_timeout_retries_from_marker():
    mock_item = Mock()
    mock_marker = Mock()
    mock_marker.args = [3]
    mock_item.get_closest_marker.return_value = mock_marker

    result = _resolve_timeout_retries(mock_item)

    assert result == 3
    mock_item.get_closest_marker.assert_called_once_with("playwright_timeout_retries")


def test_resolve_timeout_retries_from_ini():
    mock_item = Mock()
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 2

    result = _resolve_timeout_retries(mock_item)

    assert result == 2


def test_resolve_timeout_retries_defaults_to_zero():
    mock_item = Mock()
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 0

    result = _resolve_timeout_retries(mock_item)

    assert result == 0


def test_resolve_timeout_retries_marker_takes_precedence():
    mock_item = Mock()
    mock_marker = Mock()
    mock_marker.args = [5]
    mock_item.get_closest_marker.return_value = mock_marker
    mock_item.config.getini.return_value = 1

    result = _resolve_timeout_retries(mock_item)

    assert result == 5
    mock_item.config.getini.assert_not_called()


def _make_test_report(when="call", passed=True, failed=False, longrepr=None):
    report = Mock(spec=pytest.TestReport)
    report.when = when
    report.passed = passed
    report.failed = failed
    report.skipped = False
    report.longrepr = longrepr
    report.outcome = "passed" if passed else "failed"
    return report


def test_pytest_runtest_protocol_no_page_fixture():
    mock_item = Mock()
    mock_item.fixturenames = ["request", "tmp_path"]

    result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is None


def test_pytest_runtest_protocol_zero_retries():
    mock_item = Mock()
    mock_item.fixturenames = ["page", "request"]
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 0

    result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is None


def test_pytest_runtest_protocol_passes_on_first_attempt():
    mock_item = Mock()
    mock_item.fixturenames = ["page", "request"]
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 2

    passing_report = _make_test_report(when="call", passed=True)

    with patch(
        "pytest_playwright_artifacts.plugin.runtestprotocol",
        return_value=[passing_report],
    ) as mock_protocol:
        result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is True
    assert mock_protocol.call_count == 1


def test_pytest_runtest_protocol_non_timeout_failure_no_retry():
    mock_item = Mock()
    mock_item.fixturenames = ["page", "request"]
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 2

    failing_report = _make_test_report(
        when="call", passed=False, failed=True, longrepr="AssertionError: expected True"
    )

    with patch(
        "pytest_playwright_artifacts.plugin.runtestprotocol",
        return_value=[failing_report],
    ) as mock_protocol:
        result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is True
    assert mock_protocol.call_count == 1


def test_pytest_runtest_protocol_retries_on_timeout():
    mock_item = MagicMock()
    mock_item.fixturenames = ["page", "request"]
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 2

    timeout_longrepr = "playwright._impl._errors.TimeoutError: Timeout exceeded"
    timeout_report = _make_test_report(
        when="call", passed=False, failed=True, longrepr=timeout_longrepr
    )
    passing_report = _make_test_report(when="call", passed=True)

    call_count = 0

    def side_effect(item, nextitem, log):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [timeout_report]
        return [passing_report]

    with patch(
        "pytest_playwright_artifacts.plugin.runtestprotocol", side_effect=side_effect
    ):
        result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is True
    assert call_count == 2


def test_pytest_runtest_protocol_exhausts_retries_on_repeated_timeout():
    mock_item = MagicMock()
    mock_item.fixturenames = ["page", "request"]
    mock_item.get_closest_marker.return_value = None
    mock_item.config.option.playwright_timeout_retries = None
    mock_item.config.getini.return_value = 2

    timeout_longrepr = "playwright._impl._errors.TimeoutError: Timeout exceeded"
    timeout_report = _make_test_report(
        when="call", passed=False, failed=True, longrepr=timeout_longrepr
    )

    with patch(
        "pytest_playwright_artifacts.plugin.runtestprotocol",
        return_value=[timeout_report],
    ) as mock_protocol:
        result = pytest_runtest_protocol(mock_item, nextitem=None)

    assert result is True
    # 1 initial attempt + 2 retries = 3 total
    assert mock_protocol.call_count == 3


def test_pytest_report_teststatus_rerun():
    mock_report = Mock()
    mock_report.outcome = "rerun"
    mock_config = Mock()

    result = pytest_report_teststatus(mock_report, mock_config)

    assert result == ("rerun", "R", "RERUN")


def test_pytest_report_teststatus_other_outcome():
    mock_report = Mock()
    mock_report.outcome = "passed"
    mock_config = Mock()

    result = pytest_report_teststatus(mock_report, mock_config)

    assert result is None


def test_assertion_ignore_errors_extend():
    """Verify ignore extends default list (which is implicitly empty for this test)."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    # Simulate captured logs where some are NOT ignored globally (so they appear here)
    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "Regular Error",
                "args": [],
                "location": {},
                "ignored": False,
            },
            {
                "type": "error",
                "text": "Ignored Error",
                "args": [],
                "location": {},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    # Default: Fails on both
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request)
    assert "Regular Error" in str(excinfo.value)
    assert "Ignored Error" in str(excinfo.value)

    # Ignore one: Fails on other
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request, ignore=["Ignored Error"])
    assert "Regular Error" in str(excinfo.value)
    assert "Ignored Error" not in str(excinfo.value)

    # Ignore both: Passes
    assert_no_console_errors(mock_request, ignore=["Regular Error", "Ignored Error"])


def test_assertion_skip_defaults():
    """Verify skip_defaults=True ignores global defaults (includes globally ignored errors)."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    # Simulate captured logs where one WAS globally ignored
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "Globally Ignored Error",
                "args": [],
                "location": {},
                "ignored": True,  # Was ignored by global config
            },
            {
                "type": "error",
                "text": "Regular Error",
                "args": [],
                "location": {},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    # Default (skip_defaults=False): Globally ignored error is filtered out. Fails on Regular Error.
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request)
    assert "Globally Ignored Error" not in str(excinfo.value)
    assert "Regular Error" in str(excinfo.value)

    # skip_defaults=True: Global ignores are ignored (included). Fails on BOTH.
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request, skip_defaults=True)
    assert "Globally Ignored Error" in str(excinfo.value)
    assert "Regular Error" in str(excinfo.value)

    # skip_defaults=True with ignore list: Ignores specific error, includes globally ignored one unless ignored locally
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(
            mock_request, ignore=["Regular Error"], skip_defaults=True
        )
    assert "Globally Ignored Error" in str(excinfo.value)
    assert "Regular Error" not in str(excinfo.value)


def test_assertion_ignore_regex():
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "Error 123",
                "args": [],
                "location": {},
                "ignored": False,
            }
        ]
    }
    mock_request.config = mock_config

    # Fails without regex
    with pytest.raises(AssertionError):
        assert_no_console_errors(mock_request)

    # Passes with regex
    assert_no_console_errors(mock_request, ignore=[r"Error \d+"])


def test_assert_no_console_errors_custom_levels():
    """Verify assert_no_console_errors respects custom error_levels."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "warning",
                "text": "warning message",
                "args": [],
                "location": {},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    # Passes by default (only looks for 'error')
    assert_no_console_errors(mock_request)

    # Fails when 'warning' is added to error_levels
    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(mock_request, error_levels=["warning"])


def test_assert_no_console_errors_multiple_levels():
    """Verify assert_no_console_errors handles multiple error_levels."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "error msg",
                "args": [],
                "location": {},
                "ignored": False,
            },
            {
                "type": "warning",
                "text": "warning msg",
                "args": [],
                "location": {},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request, error_levels=["error", "warning"])

    assert "error msg" in str(excinfo.value)
    assert "warning msg" in str(excinfo.value)


def test_compile_ignore_patterns_with_dict_entries():
    """Verify dict entries compile into callable predicates with correct behavior."""
    mock_config = Mock()
    mock_config.option.playwright_console_ignore = None
    mock_config.getini.return_value = [
        "plain.*regex",
        {"file": "analytics\\.js"},
        {"file": "tracking\\.js", "message": "deprecated.*"},
        {"file": "analytics\\.js"},  # duplicate — should be deduplicated
    ]

    predicates = _compile_ignore_patterns(mock_config)

    assert len(predicates) == 3
    assert all(callable(p) for p in predicates)

    analytics_log = {
        "type": "log",
        "text": "any message",
        "args": [],
        "location": {"url": "https://cdn.example.com/analytics.js"},
        "ignored": False,
    }
    tracking_deprecated_log = {
        "type": "log",
        "text": "deprecated API",
        "args": [],
        "location": {"url": "https://cdn.example.com/tracking.js"},
        "ignored": False,
    }
    tracking_other_log = {
        "type": "log",
        "text": "some other message",
        "args": [],
        "location": {"url": "https://cdn.example.com/tracking.js"},
        "ignored": False,
    }

    # plain regex predicate matches text
    assert predicates[0](
        {
            "type": "log",
            "text": "plain text regex match",
            "args": [],
            "location": {},
            "ignored": False,
        }
    )
    # file-only predicate ignores all messages from analytics.js
    assert predicates[1](analytics_log)
    # file+message predicate ignores only matching messages from tracking.js
    assert predicates[2](tracking_deprecated_log)
    assert not predicates[2](tracking_other_log)


def test_should_ignore_console_log_structured_file_only():
    """Verify file-only dict entry ignores all messages from matching URL."""
    log_entry = {
        "type": "log",
        "text": "any message",
        "args": [],
        "location": {"url": "https://example.com/analytics.js", "lineNumber": 1},
        "ignored": False,
    }

    predicate = _compile_entry({"file": r"analytics\.js"})
    assert _should_ignore_console_log(log_entry, [predicate]) is True


def test_should_ignore_console_log_structured_file_and_message_match():
    """Verify file+message dict entry ignores when both match."""
    log_entry = {
        "type": "log",
        "text": "deprecated API called",
        "args": [],
        "location": {"url": "https://example.com/tracking.js", "lineNumber": 5},
        "ignored": False,
    }

    predicate = _compile_entry({"file": r"tracking\.js", "message": r"deprecated.*"})
    assert _should_ignore_console_log(log_entry, [predicate]) is True


def test_should_ignore_console_log_structured_file_and_message_no_match():
    """Verify file+message dict entry does not ignore when message doesn't match."""
    log_entry = {
        "type": "log",
        "text": "some other message",
        "args": [],
        "location": {"url": "https://example.com/tracking.js", "lineNumber": 5},
        "ignored": False,
    }

    predicate = _compile_entry({"file": r"tracking\.js", "message": r"deprecated.*"})
    assert _should_ignore_console_log(log_entry, [predicate]) is False


def test_should_ignore_console_log_structured_file_no_match():
    """Verify dict entry does not ignore when URL doesn't match."""
    log_entry = {
        "type": "log",
        "text": "deprecated API called",
        "args": [],
        "location": {"url": "https://example.com/app.js", "lineNumber": 5},
        "ignored": False,
    }

    predicate = _compile_entry({"file": r"tracking\.js", "message": r"deprecated.*"})
    assert _should_ignore_console_log(log_entry, [predicate]) is False


def test_assert_no_console_errors_with_dict_ignore_file_only():
    """Verify assert_no_console_errors accepts dict ignore with file pattern."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "some error",
                "args": [],
                "location": {"url": "https://cdn.example.com/third-party.js"},
                "ignored": False,
            },
            {
                "type": "error",
                "text": "real error",
                "args": [],
                "location": {"url": "https://myapp.com/app.js"},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    # Ignoring third-party.js errors by file: only real error remains
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(mock_request, ignore=[{"file": r"third-party\.js"}])

    assert "real error" in str(excinfo.value)
    assert "some error" not in str(excinfo.value)


def test_assert_no_console_errors_with_dict_ignore_file_and_message():
    """Verify assert_no_console_errors with file+message dict ignore."""
    mock_request = Mock()
    mock_request.node.nodeid = "test_nodeid"

    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [
            {
                "type": "error",
                "text": "deprecated feature used",
                "args": [],
                "location": {"url": "https://cdn.example.com/analytics.js"},
                "ignored": False,
            },
            {
                "type": "error",
                "text": "network failure",
                "args": [],
                "location": {"url": "https://cdn.example.com/analytics.js"},
                "ignored": False,
            },
        ]
    }
    mock_request.config = mock_config

    # Only ignore "deprecated" messages from analytics.js; network failure should remain
    with pytest.raises(AssertionError) as excinfo:
        assert_no_console_errors(
            mock_request,
            ignore=[{"file": r"analytics\.js", "message": r"deprecated.*"}],
        )

    assert "network failure" in str(excinfo.value)
    assert "deprecated feature used" not in str(excinfo.value)


def _make_log(text: str, ignored: bool = False) -> StructuredConsoleLog:
    return {
        "type": "log",
        "text": text,
        "args": [],
        "location": {},
        "ignored": ignored,
    }


def test_write_console_logs_keeps_for_single_test(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_nodeid": [_make_log("msg1"), _make_log("ignored", ignored=True)]
    }

    write_console_logs(tmp_path, mock_config, "test_nodeid", single_test=True)

    assert "test_nodeid" in mock_config._playwright_console_logs


def test_write_console_logs_deletes_for_multi_test(tmp_path):
    mock_config = Mock()
    mock_config._playwright_console_logs = {"test_nodeid": [_make_log("msg1")]}

    write_console_logs(tmp_path, mock_config, "test_nodeid", single_test=False)

    assert "test_nodeid" not in mock_config._playwright_console_logs


def test_pytest_terminal_summary_outputs_all_logs():
    mock_tr = Mock()
    mock_config = Mock()
    mock_config._playwright_console_logs = {
        "test_foo.py::test_bar": [
            _make_log("hello"),
            _make_log("filtered", ignored=True),
        ]
    }

    pytest_terminal_summary(mock_tr, exitstatus=0, config=mock_config)

    mock_tr.section.assert_called_once_with(
        "Playwright console logs: test_foo.py::test_bar"
    )
    calls = [call.args[0] for call in mock_tr.write_line.call_args_list]
    assert any("hello" in c for c in calls)
    assert any("[ignored]" in c and "filtered" in c for c in calls)


def test_pytest_terminal_summary_no_logs():
    mock_tr = Mock()
    mock_config = Mock()
    mock_config._playwright_console_logs = {}

    pytest_terminal_summary(mock_tr, exitstatus=0, config=mock_config)

    mock_tr.section.assert_not_called()
    mock_tr.write_line.assert_not_called()
