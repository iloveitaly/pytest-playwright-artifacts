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
  fully formatted line. Messages that match are not emitted to stdout and are not stored in the
  in-memory buffer used for artifacts.

  Example (pyproject.toml):
      [tool.pytest.ini_options]
      playwright_console_ignore = [
        "Invalid Sentry Dsn:.*",
        "Radar SDK: initialized.*",
        "\\[Meta Pixel\\].*",
      ]

  Example (pytest.ini):
      [pytest]
      playwright_console_ignore =
        Invalid Sentry Dsn:.*
        Radar SDK: initialized.*
        \\[Meta Pixel\\].*

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
from playwright.sync_api import ConsoleMessage, Page
import structlog
from structlog_config import configure_logger

configure_logger()
log = structlog.get_logger(logger_name="pytest_playwright_artifacts")

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class StructuredConsoleLog(TypedDict):
    type: str
    text: str
    args: list[object]
    location: object


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
    # register ini option for filtering playwright console logs (no cli flag)
    parser.addini(
        "playwright_console_ignore",
        "List of regex (one per line) to ignore Playwright console messages.",
        type="linelist",
        default=[],
    )


def _compile_ignore_patterns(config: PlaywrightConfig) -> list[re.Pattern[str]]:
    # collect and compile unique ignore regex from ini configuration
    ini_patterns = cast(list[str], config.getini("playwright_console_ignore") or [])
    unique_patterns = list(dict.fromkeys(ini_patterns))
    return [re.compile(p) for p in unique_patterns]


def pytest_configure(config: PlaywrightConfig) -> None:
    config._playwright_console_logs = {}
    config._playwright_console_ignore_patterns = _compile_ignore_patterns(config)


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
        if _should_ignore_console_log(
            structured_log, pytestconfig._playwright_console_ignore_patterns
        ):
            return

        logs.append(structured_log)
        log_msg = format_console_msg(structured_log)
        log.debug("captured browser console message", message=log_msg)

    page.on("console", log_console)
    yield

    if request.node.nodeid in pytestconfig._playwright_console_logs:
        del pytestconfig._playwright_console_logs[request.node.nodeid]


def assert_no_console_errors(request: pytest.FixtureRequest) -> None:
    # assertion helper to ensure no 'error' type console logs occurred
    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])
    errors = [log for log in logs if log["type"].lower() == "error"]

    if not errors:
        return

    error_msgs = "\n".join(format_console_msg(log) for log in errors)
    assert not errors, f"Console errors found:\n{error_msgs}"


def strip_ansi(text: str) -> str:
    # helper to remove ansi escape sequences from text
    return ANSI_ESCAPE_RE.sub("", text)


def sanitize_for_artifacts(text: str) -> str:
    # helper to sanitize test nodeid for artifact directory naming
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", text)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "unknown-test"


def get_artifact_dir(item: pytest.Item) -> Path:
    # helper to get or create the per-test artifact directory
    output_dir = item.config.getoption("output") or "test-results"
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    per_test_dir = output_path / sanitize_for_artifacts(item.nodeid)
    per_test_dir.mkdir(parents=True, exist_ok=True)
    return per_test_dir


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
) -> None:
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
    log.info("wrote test failure summary", file_path=failure_text_file)


def write_console_logs(
    per_test_dir: Path, config: PlaywrightConfig, nodeid: str
) -> None:
    # helper to write captured console logs to a file
    if nodeid not in config._playwright_console_logs:
        return

    logs = config._playwright_console_logs[nodeid]
    logs_content = "\n".join(format_console_msg(log) for log in logs)
    logs_file = per_test_dir / "console_logs.log"
    logs_file.write_text(logs_content)
    log.info("wrote console logs", file_path=logs_file)
    del config._playwright_console_logs[nodeid]


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
    per_test_dir = get_artifact_dir(item)

    failure_file = per_test_dir / "failure.html"
    failure_file.write_text(page.content())
    log.info("wrote rendered playwright page html", file_path=failure_file)

    screenshot_file = per_test_dir / "screenshot.png"
    page.screenshot(path=screenshot_file, full_page=True)
    log.info("wrote playwright screenshot", file_path=screenshot_file)

    failure_info = extract_failure_info(rep, call, item)
    write_failure_summary(per_test_dir, item, rep, failure_info)

    write_console_logs(per_test_dir, cast(PlaywrightConfig, item.config), item.nodeid)
