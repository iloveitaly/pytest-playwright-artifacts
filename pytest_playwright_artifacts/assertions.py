import re
from typing import cast

import pytest

from pytest_playwright_artifacts.plugin import (
    PlaywrightConfig,
    _should_ignore_console_log,
    format_console_msg,
)


def assert_no_console_errors(
    request: pytest.FixtureRequest,
    ignore: list[str | re.Pattern[str]] | None = None,
    skip_defaults: bool = False,
    error_levels: list[str] | None = None,
) -> None:
    # assertion helper to ensure no specified console log types occurred
    error_levels = [level.lower() for level in (error_levels or ["error"])]
    config = cast(PlaywrightConfig, request.config)
    logs = config._playwright_console_logs.get(request.node.nodeid, [])

    if skip_defaults:
        candidate_logs = logs
    else:
        candidate_logs = [log for log in logs if not log["ignored"]]

    errors = [log for log in candidate_logs if log["type"].lower() in error_levels]

    if ignore and errors:
        # Filter out errors that match the provided ignore patterns
        ignore_patterns = [
            re.compile(p) if isinstance(p, str) else p for p in ignore
        ]
        
        filtered_errors = []
        for error in errors:
            should_ignore = _should_ignore_console_log(error, ignore_patterns)
            if not should_ignore:
                filtered_errors.append(error)
        errors = filtered_errors

    if not errors:
        return

    error_msgs = "\n".join(format_console_msg(log) for log in errors)
    assert not errors, f"Console errors found:\n{error_msgs}"
