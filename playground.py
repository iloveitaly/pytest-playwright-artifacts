"""
Playground for experimental approaches to console logging that didn't work.

This file contains the autouse fixture approach that was attempted but disabled
because it doesn't work reliably with pytest-playwright's page fixture.

## Why the autouse fixture doesn't work:

The core issue is timing and fixture dependency resolution. When using:
```python
@pytest.fixture(autouse=True)
def _playwright_console_logging_fixture(request):
    page: Page = request.getfixturevalue("page")
    # attach console listener
```

The problem is that:
1. `request.getfixturevalue("page")` creates a page instance
2. We attach a console listener to that page
3. BUT pytest-playwright may create ANOTHER page instance for the actual test
4. OR the timing of when listeners are attached vs when the test runs causes issues
5. Result: Only some console messages are captured, or none at all

The tests show that only 1 of 2 console messages gets captured with this approach,
suggesting the listener stops working or is attached to a different page object.

## What actually works:

The working approach is in `conftest.py` at the project root, which explicitly
wraps the `page` fixture:

```python
@pytest.fixture(scope="function")
def page(page: Page, request: pytest.FixtureRequest) -> Generator[Page, None, None]:
    # attach console listener
    page.on("console", log_console)
    yield page
```

This works because:
1. It receives the actual page fixture that pytest-playwright creates
2. It attaches the listener BEFORE yielding to the test
3. The same page instance is used throughout the test
4. All console messages are captured reliably

## For end users:

End users need to add a similar page fixture wrapper in their own `conftest.py`.
The plugin doesn't work automatically - it requires explicit setup.
See the `conftest.py` in this repo for an example implementation.
"""

# Disabled autouse fixture - kept here for reference
#
# @pytest.fixture(autouse=True)
# def _playwright_console_logging_fixture(
#     request: pytest.FixtureRequest,
# ) -> Generator[None, None, None]:
#     """Autouse fixture to capture and log Playwright console messages."""
#     from pytest_playwright_artifacts.plugin import (
#         PlaywrightConfig,
#         StructuredConsoleLog,
#         extract_structured_log,
#         format_console_msg,
#         _should_ignore_console_log,
#     )
#     import logging
#
#     logger = logging.getLogger("playwright_javascript")
#
#     # Check if this test uses the page fixture
#     fixturenames = cast(list[str], getattr(request, "fixturenames", []))
#     if "page" not in fixturenames:
#         yield
#         return
#
#     # Get the page fixture - this will trigger its creation
#     try:
#         page: Page = request.getfixturevalue("page")
#     except (pytest.FixtureLookupError, AttributeError):
#         yield
#         return
#
#     config = cast(PlaywrightConfig, request.config)
#
#     # Initialize logs list for this test
#     logs: list[StructuredConsoleLog] = []
#     config._playwright_console_logs[request.node.nodeid] = logs
#
#     def log_console(msg: ConsoleMessage) -> None:
#         structured_log = extract_structured_log(msg)
#         if _should_ignore_console_log(
#             structured_log, config._playwright_console_ignore_patterns
#         ):
#             return
#         logs.append(structured_log)
#         log_msg = format_console_msg(structured_log)
#         logger.debug(log_msg)
#
#     # Attach console listener
#     page.on("console", log_console)
#
#     # Yield to let test run
#     yield
