"""Conftest for pytest-playwright-artifacts development - wraps page fixture for testing."""

import pytest
from playwright.sync_api import Page
from typing import Generator, cast
import logging

# This conftest is ONLY for testing the plugin itself
# End users don't need this - the plugin handles everything automatically


@pytest.fixture(scope="function")
def page(page: Page, request: pytest.FixtureRequest) -> Generator[Page, None, None]:
    """Wrap pytest-playwright's page fixture to add console logging for our tests."""
    from pytest_playwright_artifacts.plugin import (
        PlaywrightConfig,
        StructuredConsoleLog,
        extract_structured_log,
        format_console_msg,
        _should_ignore_console_log,
    )

    logger = logging.getLogger("playwright_javascript")
    config = cast(PlaywrightConfig, request.config)

    # Initialize logs list for this test
    logs: list[StructuredConsoleLog] = []
    config._playwright_console_logs[request.node.nodeid] = logs

    def log_console(msg) -> None:
        try:
            structured_log = extract_structured_log(msg)
            if _should_ignore_console_log(
                structured_log, config._playwright_console_ignore_patterns
            ):
                return
            logs.append(structured_log)
            log_msg = format_console_msg(structured_log)
            logger.debug(log_msg)
        except Exception as e:
            # Log any errors to avoid silently breaking the listener
            logger.error(f"Error in console listener: {e}", exc_info=True)

    # Attach console listener
    page.on("console", log_console)

    yield page
