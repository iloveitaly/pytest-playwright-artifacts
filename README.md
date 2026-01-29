# Capture debugging artifacts on Playwright test failures

When your Playwright tests fail, you need to see what went wrong. This pytest plugin automatically captures HTML, screenshots, console logs, and failure summaries the moment a test fails.

I built this because debugging failed tests without artifacts is painful. You're left guessing what the page looked like, what JavaScript errors occurred, or what the actual DOM content was. This plugin captures all of that automatically.

## Installation

```bash
uv add pytest-playwright-artifacts
```

## Usage

The plugin activates automatically once installed. No configuration needed.

### Basic Test

```python
def test_my_page(page):
    page.goto("https://example.com")
    assert page.title() == "Example"
```

When this test fails, you'll find artifacts in `test-results/<test-name>/`:
- `failure.html` - Rendered DOM content at the moment of failure
- `screenshot.png` - Full-page screenshot
- `failure.txt` - Failure summary with traceback
- `console_logs.log` - All captured console messages

### Fail tests on console errors

```python
from pytest_playwright_artifacts import assert_no_console_errors

def test_no_console_errors(page, request):
    page.goto("https://example.com")
    assert_no_console_errors(request)
```

This fails the test if any `console.error()` messages were logged during the test.

## Features

- Automatic artifact capture on test failure: HTML, screenshots, failure summary, and console logs
- Console log monitoring for all browser console messages during tests
- Regex-based filtering to ignore noisy console messages
- Helper assertion `assert_no_console_errors()` to fail tests on console errors
- Per-test artifact directories for clean organization

## Configuration

### Filter noisy console messages

Use regex patterns to ignore known noisy messages:

**pyproject.toml:**

```toml
[tool.pytest.ini_options]
playwright_console_ignore = [
  "Invalid Sentry Dsn:.*",
  "Radar SDK: initialized.*",
  "\\[Meta Pixel\\].*",
]
```

**pytest.ini:**

```ini
[pytest]
playwright_console_ignore =
  Invalid Sentry Dsn:.*
  Radar SDK: initialized.*
  \\[Meta Pixel\\].*
```

Patterns match against both the raw console text and the formatted log line.

### Change artifact output directory

```bash
pytest --output=my-artifacts
```

## How it works

The plugin uses pytest hooks and fixtures to capture artifacts:

1. An autouse fixture attaches a console listener to every Playwright page
2. Console logs are stored in memory at `request.config._playwright_console_logs[nodeid]`
3. The `pytest_runtest_makereport` hook detects test failures
4. On failure, the plugin captures page content, takes a screenshot, and writes all artifacts
5. Console logs are cleaned up from memory after test completion

## Disabling features

**Disable console logging:**
```python
# In pytest_playwright_artifacts/plugin.py, change:
@pytest.fixture(autouse=False)
def playwright_console_logging(...):
```

**Disable failure artifacts:**
Comment out the `pytest_runtest_makereport` hook in `plugin.py`.

# [MIT License](LICENSE.md)
