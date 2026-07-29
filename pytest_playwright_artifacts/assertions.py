import re
from typing import cast

import pytest

from pytest_playwright_artifacts.plugin import (
    PlaywrightConfig,
    _compile_entry,
    _should_ignore_console_log,
    format_console_msg,
)


def clear_console_errors(request: pytest.FixtureRequest) -> None:
    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])

    for log in logs:
        log["assertion_cleared"] = True


def assert_no_console_errors(
    request: pytest.FixtureRequest,
    ignore: list[str | re.Pattern[str] | dict[str, str]] | None = None,
    skip_defaults: bool = False,
    error_levels: list[str] | None = None,
) -> None:
    # assertion helper to ensure no specified console log types occurred
    error_levels = [level.lower() for level in (error_levels or ["error"])]
    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])
    logs = [log for log in logs if not log.get("assertion_cleared", False)]

    if skip_defaults:
        candidate_logs = logs
    else:
        candidate_logs = [log for log in logs if not log["ignored"]]

    errors = [log for log in candidate_logs if log["type"].lower() in error_levels]

    if ignore and errors:
        predicates = [_compile_entry(p) for p in ignore]
        errors = [e for e in errors if not _should_ignore_console_log(e, predicates)]

    if not errors:
        return

    error_msgs = "\n".join(format_console_msg(log) for log in errors)
    assert not errors, f"Console errors found:\n{error_msgs}"
