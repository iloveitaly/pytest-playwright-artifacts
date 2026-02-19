"""
Pytest plugin for enhanced Playwright testing.

Features:
- Automatically captures and logs console messages from Playwright pages during tests.
- On test failure, persists the rendered page HTML, a PNG screenshot, a concise text summary
  of the failure, and console logs in a per-test artifact directory (mirroring
  pytest-playwright's structure for screenshots/traces).
- Provides `assert_no_console_errors` helper to fail tests if any 'error' type console logs are detected.

The captured console logs are stored in `request.config._playwright_console_logs[nodeid]` as a list of dicts
for access in custom hooks/reporters if needed.

To disable:
- Change the `autouse=True` to `False` in the `playwright_console_logging` fixture.
- For failure artifacts, remove/comment out the `pytest_runtest_makereport` hook.
- The assertion is manual, so only impacts tests where it's called.

Configuration:
- Use the pytest ini option `playwright_console_ignore` to filter out console messages.
  These values are regular expressions and are matched against both the raw console text and the
  fully formatted log entry (which includes the type, text, arguments, and source location/URL).

  This means you can filter logs based on their content OR their origin (e.g., ignoring all logs
  from a specific third-party script).

  Example (pyproject.toml):
      [tool.pytest.ini_options]
      playwright_console_ignore = [
        "Invalid Sentry Dsn:.*",
        "Radar SDK: initialized.*",
        ".*third-party-tracker\\.js.*",  # Ignore by filename/URL
      ]

  Example (pytest.ini):
      [pytest]
      playwright_console_ignore =
        Invalid Sentry Dsn:.*
        Radar SDK: initialized.*
        .*third-party-tracker\\.js.*

Artifacts:
  On test failure, the following files are written to `<output-dir>/<sanitized-nodeid>/`:

  - `failure.html`: The rendered DOM content of the page at the moment of failure.
  - `screenshot.png`: A full-page PNG screenshot of the browser viewport.
  - `failure.txt`: A concise text summary containing test nodeid, phase, error message,
    location, and full failure traceback.
  - `console_logs.log`: All captured browser console messages (only written on failure).

  The output directory defaults to `test-results` and can be changed via pytest-playwright's
  `--output` option.
"""

import re
from pathlib import Path
from typing import Generator, Protocol, TypedDict, cast

import pytest
import structlog
from _pytest.runner import runtestprotocol
from playwright.sync_api import ConsoleMessage, Page

from pytest_plugin_utils import (
    get_pytest_option,
    register_pytest_options,
    set_pytest_option,
)
from pytest_plugin_utils import get_artifact_dir, set_artifact_dir_option

log = structlog.get_logger(logger_name=__package__)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PLUGIN_NAMESPACE: str = __package__ or "pytest_playwright_artifacts"


# Define configuration options
set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_artifacts_output",
    default="test-results",
    help="Directory to store artifact files on test failure.",
    available="cli_option",
    type_hint=str,
)

set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_console_ignore",
    default=[],
    help="List of regex (one per line) to ignore Playwright console messages.",
    available="ini",
    type_hint=list[str],
)

set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_timeout_retries",
    default=0,
    help="Number of times to retry a Playwright test on TimeoutError.",
    available="ini",
    type_hint=int,
)

set_artifact_dir_option(PLUGIN_NAMESPACE, "playwright_artifacts_output")


class StructuredConsoleLog(TypedDict):
    type: str
    text: str
    args: list[object]
    location: object
    ignored: bool


class FailureInfo(TypedDict):
    error_message: str | None
    error_file: str | None
    error_line: int | None
    longrepr_text: str | None


class PlaywrightConfig(Protocol):
    _playwright_console_logs: dict[str, list[StructuredConsoleLog]]
    _playwright_console_ignore_patterns: list[re.Pattern[str]]

    def getoption(self, name: str) -> object | None: ...
    def getini(self, name: str) -> object | None: ...


def pytest_addoption(parser: pytest.Parser) -> None:
    register_pytest_options(PLUGIN_NAMESPACE, parser)


def _compile_ignore_patterns(config: PlaywrightConfig) -> list[re.Pattern[str]]:
    # collect and compile unique ignore regex from ini configuration
    ini_patterns = (
        get_pytest_option(
            PLUGIN_NAMESPACE, cast(pytest.Config, config), "playwright_console_ignore"
        )
        or []
    )
    unique_patterns = list(dict.fromkeys(ini_patterns))
    return [re.compile(p) for p in unique_patterns]


def pytest_configure(config: PlaywrightConfig) -> None:
    config._playwright_console_logs = {}
    config._playwright_console_ignore_patterns = _compile_ignore_patterns(config)
    cast(pytest.Config, config).addinivalue_line(
        "markers",
        "playwright_timeout_retries(count): retry Playwright tests on TimeoutError",
    )


def format_console_msg(msg: StructuredConsoleLog) -> str:
    # helper to format a console message dict into a log string
    args_str = ", ".join(str(arg) for arg in msg["args"]) if msg["args"] else "None"
    return f"Type: {msg['type']}, Text: {msg['text']}, Args: {args_str}, Location: {msg['location']}"


def _safe_json_value(arg):
    return arg.json_value()


def extract_structured_log(msg: ConsoleMessage) -> StructuredConsoleLog:
    # helper to extract console message into a structured dict
    return {
        "type": msg.type,
        "text": msg.text,
        "args": [_safe_json_value(arg) for arg in msg.args],
        "location": msg.location,
        "ignored": False,
    }


def _should_ignore_console_log(
    structured_log: StructuredConsoleLog, patterns: list[re.Pattern[str]]
) -> bool:
    if not patterns:
        return False

    formatted = format_console_msg(structured_log)
    candidates = [structured_log["text"], formatted]

    for candidate in candidates:
        for pattern in patterns:
            if pattern.search(candidate):
                return True

    return False


@pytest.fixture(autouse=True)
def playwright_console_logging(
    request: pytest.FixtureRequest, pytestconfig: PlaywrightConfig
) -> Generator[None, None, None]:
    # fixture to capture and log playwright console messages
    if "page" not in request.fixturenames:
        yield
        return

    page: Page = request.getfixturevalue("page")
    logs: list[StructuredConsoleLog] = []
    pytestconfig._playwright_console_logs[request.node.nodeid] = logs

    def log_console(msg: ConsoleMessage) -> None:
        structured_log = extract_structured_log(msg)
        is_ignored = _should_ignore_console_log(
            structured_log, pytestconfig._playwright_console_ignore_patterns
        )
        structured_log["ignored"] = is_ignored
        logs.append(structured_log)

        if not is_ignored:
            log_msg = format_console_msg(structured_log)
            log.debug("captured browser console message", message=log_msg)

    page.on("console", log_console)
    yield

    if request.node.nodeid in pytestconfig._playwright_console_logs:
        del pytestconfig._playwright_console_logs[request.node.nodeid]


def strip_ansi(text: str) -> str:
    # helper to remove ansi escape sequences from text
    return ANSI_ESCAPE_RE.sub("", text)


def extract_failure_info(
    rep: pytest.TestReport, call: pytest.CallInfo[object], item: pytest.Item
) -> FailureInfo:
    # helper to extract failure details from pytest report
    error_message = None
    error_file = None
    error_line = None
    longrepr_text = None

    if hasattr(rep, "longrepr") and rep.longrepr is not None:
        reprcrash = getattr(rep.longrepr, "reprcrash", None)
        if reprcrash is not None:
            error_message = getattr(reprcrash, "message", None)
            error_file = getattr(reprcrash, "path", None)
            error_line = getattr(reprcrash, "lineno", None)
        longrepr_text = getattr(rep, "longreprtext", None) or str(rep.longrepr)

    if not error_message and hasattr(call, "excinfo") and call.excinfo is not None:
        error_message = call.excinfo.exconly()

    if error_file is None or error_line is None:
        location_filename, location_lineno, _ = item.location
        error_file = error_file or location_filename
        error_line = error_line or location_lineno

    return {
        "error_message": strip_ansi(error_message) if error_message else None,
        "error_file": error_file,
        "error_line": error_line,
        "longrepr_text": strip_ansi(longrepr_text) if longrepr_text else None,
    }


def write_failure_summary(
    per_test_dir: Path,
    item: pytest.Item,
    rep: pytest.TestReport,
    failure_info: FailureInfo,
) -> Path:
    # helper to write concise failure text summary
    from string import Template

    template_str = """test: $test_nodeid
phase: $phase
error: $error_message
location: $location

full failure:
$longrepr_text"""

    location = ""
    if failure_info["error_file"]:
        if failure_info["error_line"] is not None:
            location = f"{failure_info['error_file']}:{failure_info['error_line']}"
        else:
            location = failure_info["error_file"]

    template = Template(template_str)
    content = template.substitute(
        test_nodeid=item.nodeid,
        phase=rep.when,
        error_message=failure_info["error_message"] or "",
        location=location,
        longrepr_text=failure_info["longrepr_text"] or "",
    )

    content = strip_ansi(content)
    failure_text_file = per_test_dir / "failure.txt"
    failure_text_file.write_text(content)

    return failure_text_file


def write_console_logs(
    per_test_dir: Path, config: PlaywrightConfig, nodeid: str
) -> Path | None:
    # helper to write captured console logs to a file
    if nodeid not in config._playwright_console_logs:
        return None

    logs = config._playwright_console_logs[nodeid]
    # Filter out ignored logs before writing to file
    active_logs = [log for log in logs if not log["ignored"]]

    logs_content = "\n".join(format_console_msg(log) for log in active_logs)
    logs_file = per_test_dir / "console_logs.log"
    logs_file.write_text(logs_content)
    del config._playwright_console_logs[nodeid]

    return logs_file


def _is_playwright_timeout(report: pytest.TestReport) -> bool:
    if report.passed or report.skipped:
        return False
    longrepr_str = str(report.longrepr) if report.longrepr else ""
    return "playwright._impl._errors.TimeoutError" in longrepr_str


def _resolve_timeout_retries(item: pytest.Item) -> int:
    marker = item.get_closest_marker("playwright_timeout_retries")
    if marker is not None:
        return int(marker.args[0])
    return int(
        get_pytest_option(PLUGIN_NAMESPACE, item.config, "playwright_timeout_retries")
        or 0
    )


def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> bool | None:
    if "page" not in cast(list[str], getattr(item, "fixturenames", [])):
        return None

    retries = _resolve_timeout_retries(item)
    if retries == 0:
        return None

    for attempt in range(retries + 1):
        is_last_attempt = attempt == retries
        reports = runtestprotocol(item, nextitem=nextitem, log=is_last_attempt)

        failed_call = next((r for r in reports if r.when == "call" and r.failed), None)

        if failed_call is None or not _is_playwright_timeout(failed_call):
            if not is_last_attempt:
                for report in reports:
                    item.ihook.pytest_runtest_logreport(report=report)
            return True

        if is_last_attempt:
            return True

        log.info(
            "playwright timeout, retrying test",
            nodeid=item.nodeid,
            attempt=attempt + 1,
            retries=retries,
        )

        for report in reports:
            # pytest-rerunfailures pattern: "rerun" is not in pyright's Literal type for outcome
            setattr(report, "outcome", "rerun")
            item.ihook.pytest_runtest_logreport(report=report)

    return True


def pytest_report_teststatus(
    report: pytest.TestReport, config: pytest.Config
) -> tuple[str, str, str] | None:
    del config  # required by pytest hook signature but unused
    if report.outcome == "rerun":
        return "rerun", "R", "RERUN"
    return None


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[object]
) -> Generator[None, object, None]:
    # hook to persist page html, screenshot, failure summary, and console logs on test failure
    outcome = yield

    class _HookOutcome(Protocol):
        def get_result(self) -> pytest.TestReport: ...

    rep = cast(_HookOutcome, outcome).get_result()

    if rep.when != "call" or not rep.failed:
        return

    fixturenames = cast(list[str], getattr(item, "fixturenames", []))
    if "page" not in fixturenames:
        return

    funcargs = cast(dict[str, object], getattr(item, "funcargs", {}))
    page = funcargs.get("page")
    if page is None:
        return

    page = cast(Page, page)
    per_test_dir = get_artifact_dir(PLUGIN_NAMESPACE, item)

    failure_file = per_test_dir / "failure.html"
    failure_file.write_text(page.content())

    screenshot_file = per_test_dir / "screenshot.png"
    page.screenshot(path=screenshot_file, full_page=True)

    failure_info = extract_failure_info(rep, call, item)
    summary_file = write_failure_summary(per_test_dir, item, rep, failure_info)

    logs_file = write_console_logs(
        per_test_dir, cast(PlaywrightConfig, item.config), item.nodeid
    )

    log.info(
        "wrote playwright artifacts",
        html=failure_file,
        screenshot=screenshot_file,
        summary=summary_file,
        logs=logs_file,
    )
