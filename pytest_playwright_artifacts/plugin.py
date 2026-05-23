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
  Entries can be plain regex strings OR structured dicts with `file` (required) and `message` (optional).

  Plain string entries are matched against both the raw console text and the fully formatted log
  entry (which includes the type, text, arguments, and source location/URL).

  Structured dict entries match `file` against the source URL and `message` against the raw text.
  If only `file` is given, all messages from matching URLs are ignored. If both are given, both
  must match (AND logic). Dict format requires pyproject.toml (TOML inline tables).

  Example (pyproject.toml):
      [tool.pytest.ini_options]
      playwright_console_ignore = [
        "Invalid Sentry Dsn:.*",
        "Radar SDK: initialized.*",
        { file = "third-party\\.js" },
        { file = "analytics\\.js", message = "deprecated.*" },
      ]

  Example (pytest.ini):
      [pytest]
      playwright_console_ignore =
        Invalid Sentry Dsn:.*
        Radar SDK: initialized.*

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

import json
import re
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast

import pytest
import structlog
from _pytest.runner import runtestprotocol
from _pytest.terminal import TerminalReporter
from playwright.sync_api import ConsoleMessage, Page
from pytest_plugin_utils import (
    get_artifact_dir,
    get_pytest_option,
    register_pytest_options,
    set_pytest_option,
)

log = structlog.get_logger(logger_name=__package__)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PLUGIN_NAMESPACE: str = __package__ or "pytest_playwright_artifacts"


IgnorePredicate = Callable[["StructuredConsoleLog"], bool]


# Define configuration options
set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_artifacts_output",
    default="test-results",
    help="Directory to store artifact files on test failure.",
    available="cli_option",
    type_hint=Path,
)

set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_console_ignore",
    default=[],
    help="List of regex (one per line) to ignore Playwright console messages.",
    available="ini",
    type_hint=list,
)

set_pytest_option(
    PLUGIN_NAMESPACE,
    "playwright_timeout_retries",
    default=0,
    help="Number of times to retry a Playwright test on TimeoutError.",
    available="ini",
    type_hint=int,
)


class StructuredConsoleLog(TypedDict):
    type: str
    text: str
    args: list[object]
    location: object
    # logs matching ignore patterns are flagged rather than dropped, so callers can still inspect them
    ignored: bool


class FailureInfo(TypedDict):
    error_message: str | None
    error_file: str | None
    error_line: int | None
    longrepr_text: str | None


class PlaywrightConfig(Protocol):
    _playwright_console_logs: dict[str, list[StructuredConsoleLog]]
    _playwright_console_ignore_patterns: list[IgnorePredicate]

    def getoption(self, name: str) -> object | None: ...
    def getini(self, name: str) -> object | None: ...


def pytest_addoption(parser: pytest.Parser) -> None:
    register_pytest_options(PLUGIN_NAMESPACE, parser)


def _make_regex_predicate(pattern: re.Pattern[str]) -> IgnorePredicate:
    def predicate(log: StructuredConsoleLog) -> bool:
        formatted = format_console_msg(log)
        return bool(pattern.search(log["text"]) or pattern.search(formatted))

    return predicate


def _make_structured_predicate(
    file_pat: re.Pattern[str], message_pat: re.Pattern[str] | None
) -> IgnorePredicate:
    def predicate(log: StructuredConsoleLog) -> bool:
        location = log["location"]
        url = location.get("url", "") if isinstance(location, dict) else ""
        if not file_pat.search(url):
            return False
        return message_pat is None or bool(message_pat.search(log["text"]))

    return predicate


def _compile_entry(entry: str | re.Pattern[str] | dict[str, str]) -> IgnorePredicate:
    if isinstance(entry, dict):
        message_pat = re.compile(entry["message"]) if entry.get("message") else None

        if "domain" in entry:
            domain = entry["domain"]
            # Validation: no protocol, no path, no wildcards, basic domain structure
            domain_validator = re.compile(
                r"""
                ^                                   # Start of string
                (?:                                 # One or more domain labels followed by a dot
                    [a-z0-9]                        # Label starts with alphanumeric
                    (?:[a-z0-9-]{0,61}[a-z0-9])?    # Optional alphanumeric/hyphen (up to 63 chars total)
                    \.                              # Dot separator
                )+
                [a-z0-9]                            # TLD/Final label starts with alphanumeric
                (?:[a-z0-9-]{0,61}[a-z0-9])?        # Optional alphanumeric/hyphen
                $                                   # End of string
                |                                   # OR
                ^localhost$                         # Exact match for localhost
                """,
                re.VERBOSE | re.IGNORECASE,
            )

            is_valid = not any(c in domain for c in "/:?#*") and bool(
                domain_validator.match(domain)
            )

            if not is_valid:
                raise ValueError(
                    f"Invalid domain name: {domain}. The 'domain' key expects a valid domain name (e.g., 'example.com'), not a URL or regex."
                )

            # Match http(s)://, optional subdomains, the domain itself, and then end of hostname or start of path/query/fragment
            file_pat = re.compile(
                rf"""
                ^https?://                          # Match protocol
                (?:[^/?#]+\.)?                      # Optional subdomains (anything but path/query delimiters)
                {re.escape(domain)}                 # The target domain
                (?:[/?#]|$)                         # End of hostname (start of path/query/fragment or end of string)
                """,
                re.VERBOSE,
            )
        else:
            file_pat = re.compile(entry["file"])

        return _make_structured_predicate(file_pat, message_pat)

    pattern = re.compile(entry) if isinstance(entry, str) else entry
    return _make_regex_predicate(pattern)


def _compile_ignore_patterns(config: PlaywrightConfig) -> list[IgnorePredicate]:
    # collect and compile unique ignore patterns (strings or structured dicts) from ini configuration
    ini_patterns = (
        get_pytest_option(
            PLUGIN_NAMESPACE, cast(pytest.Config, config), "playwright_console_ignore"
        )
        or []
    )

    seen: set[str | tuple[str, str | None]] = set()
    result: list[IgnorePredicate] = []

    for entry in ini_patterns:
        key: str | tuple[str, str | None] = (
            entry
            if isinstance(entry, str)
            else (entry.get("file") or entry.get("domain", ""), entry.get("message"))
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(_compile_entry(entry))

    return result


def pytest_configure(config: PlaywrightConfig) -> None:
    config._playwright_console_logs = {}
    config._playwright_console_ignore_patterns = _compile_ignore_patterns(config)
    cast(pytest.Config, config).addinivalue_line(
        "markers",
        "playwright_timeout_retries(count): retry Playwright tests on TimeoutError",
    )


def format_console_msg(msg: StructuredConsoleLog) -> str:
    # helper to format a console message dict into a JSON string
    log_dict = {
        "type": msg["type"],
        "text": msg["text"],
        "args": msg["args"],
        "location": msg["location"],
    }
    return json.dumps(log_dict, default=str)


def _safe_json_value(arg):
    try:
        return arg.json_value()
    except Exception:
        return str(arg)


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
    structured_log: StructuredConsoleLog, predicates: list[IgnorePredicate]
) -> bool:
    return any(pred(structured_log) for pred in predicates)


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

    # listener survives page navigations since it's bound to the Page object, not the document
    page.on("console", log_console)
    yield

    nodeid = request.node.nodeid
    if nodeid in pytestconfig._playwright_console_logs:
        # for single-test runs, keep logs in the dict so pytest_terminal_summary can print them
        if len(request.session.items) != 1:
            del pytestconfig._playwright_console_logs[nodeid]


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
    per_test_dir: Path, config: PlaywrightConfig, nodeid: str, single_test: bool = False
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

    # same single-test preservation as the fixture teardown
    if not single_test:
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
        # log=False suppresses automatic pytest_runtest_logreport calls so we can emit "rerun" instead
        reports = runtestprotocol(item, nextitem=nextitem, log=is_last_attempt)

        failed_call = next((r for r in reports if r.when == "call" and r.failed), None)

        if failed_call is None or not _is_playwright_timeout(failed_call):
            # runtestprotocol was called with log=False on non-final attempts, so report manually
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
            # "rerun" is a runtime-only outcome from pytest-rerunfailures; pytest's Literal type has no entry for it
            cast(Any, report).outcome = "rerun"
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
    base_dir = get_pytest_option(
        PLUGIN_NAMESPACE, item.config, "playwright_artifacts_output", type_hint=Path
    )
    assert base_dir
    per_test_dir = get_artifact_dir(item, base_dir, create=True)

    failure_file = per_test_dir / "failure.html"
    failure_file.write_text(page.content())

    screenshot_file = per_test_dir / "screenshot.png"
    page.screenshot(path=screenshot_file, full_page=True)

    failure_info = extract_failure_info(rep, call, item)
    summary_file = write_failure_summary(per_test_dir, item, rep, failure_info)

    logs_file = write_console_logs(
        per_test_dir,
        cast(PlaywrightConfig, item.config),
        item.nodeid,
        single_test=len(item.session.items) == 1,
    )

    log.info(
        "wrote playwright artifacts",
        html=failure_file,
        screenshot=screenshot_file,
        summary=summary_file,
        logs=logs_file,
    )


def pytest_terminal_summary(
    terminalreporter: TerminalReporter, exitstatus: object, config: PlaywrightConfig
) -> None:
    del exitstatus  # required by pytest hook signature but unused
    # only populated for single-test runs; entries are cleaned up per-test otherwise
    if not config._playwright_console_logs:
        return

    for nodeid, logs in config._playwright_console_logs.items():
        terminalreporter.section(f"Playwright console logs: {nodeid}")
        for entry in logs:
            prefix = "[ignored] " if entry["ignored"] else ""
            terminalreporter.write_line(f"{prefix}{format_console_msg(entry)}")
