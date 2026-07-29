# Capture debugging artifacts on Playwright test failures

[![Release Notes](https://img.shields.io/github/release/iloveitaly/pytest-playwright-artifacts)](https://github.com/iloveitaly/pytest-playwright-artifacts/releases)
[![Downloads](https://static.pepy.tech/badge/pytest-playwright-artifacts/month)](https://pepy.tech/project/pytest-playwright-artifacts)
![GitHub CI Status](https://github.com/iloveitaly/pytest-playwright-artifacts/actions/workflows/build_and_publish.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

When your Playwright tests fail, you need to see what went wrong. This pytest plugin does a couple things to make it easier for you (and LLMs!) to debug and build Playwright tests:

1. Automatically captures HTML, screenshots, console logs, and failure summaries the moment a test fails and dumps them into a per-test folder for easy debugging.
2. Allows you to assert that no console errors were logged during a test.
3. Automatically retry tests that fail due to Playwright flakiness

No more guessing what the page looked like, what JavaScript errors occurred, or what the actual DOM content was.

## Installation

```bash
uv add --dev pytest-playwright-artifacts
```

The plugin activates automatically once installed. No configuration needed.

## Usage

### Artifacts on failure

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

Console messages are captured for every test but are only written to `console_logs.log` on failure. During a passing test they are emitted at `DEBUG` log level via structlog and are not visible in normal pytest output.

### Fail tests on console errors

```python
from pytest_playwright_artifacts import assert_no_console_errors


def test_no_console_errors(page, request):
    page.goto("https://example.com")
    assert_no_console_errors(request)
```

This fails the test if any `console.error()` messages were logged during the test.
Use `clear_console_errors()` to exclude messages captured before a specific point
from subsequent assertions without removing them from console log output:

```python
from pytest_playwright_artifacts import (
    assert_no_console_errors,
    clear_console_errors,
)


def test_no_console_errors_after_login(page, request):
    page.goto("https://example.com/login")
    clear_console_errors(request)

    page.get_by_role("button", name="Log in").click()
    assert_no_console_errors(request)
```

### Retry on Playwright timeouts

Playwright tests can flake due to network latency or slow animations. The plugin can retry a test automatically when it fails with a `TimeoutError`. Only `playwright._impl._errors.TimeoutError` triggers a retry — assertion failures and other errors fail immediately. Retried attempts show as `R` / `RERUN` in pytest output.

#### Per-test

```python
@pytest.mark.playwright_timeout_retries(2)
def test_checkout(page):
    page.goto("https://example.com/checkout")
    page.click("#pay-button")
    expect(page.locator(".success")).to_be_visible()
```

#### Per-folder

Add a `pytestmark` to `conftest.py` in the folder you want to cover:

```python
# tests/e2e/conftest.py
import pytest

pytestmark = [pytest.mark.playwright_timeout_retries(2)]
```

#### Global default

Set a default for the entire suite in `pyproject.toml`. A marker on an individual test or folder always takes precedence.

```toml
[tool.pytest.ini_options]
playwright_timeout_retries = 2
```

## Configuration

### Filter noisy console messages

Use regex patterns to ignore known noisy messages:

**pyproject.toml:**

```toml
[tool.pytest.ini_options]
playwright_console_ignore = [
  "Invalid Sentry Dsn:.*",
  "Radar SDK: initialized.*",
  # Ignore all messages from a specific file/URL
  { file = "third-party-tracker\\.js" },
  # Ignore all messages from a specific domain (and subdomains)
  { domain = "example.com" },
  # Ignore only specific messages from a file
  { file = "analytics\\.js", message = "deprecated.*" },
]
```

**pytest.ini** (plain strings only — TOML inline tables are not supported):

```ini
[pytest]
playwright_console_ignore =
  Invalid Sentry Dsn:.*
  Radar SDK: initialized.*
  # Plain strings match against the full JSON log, allowing simple domain filtering
  example.com
```

#### Plain string patterns

Plain string entries match against both the raw console text and the fully formatted log entry (which includes the type, text, arguments, and source location/URL). This allows you to filter by content OR origin.

For example, a console log like `console.log("User:", {id: 1, name: "Alice"})` will be formatted as a JSON string:

```json
{"type": "log", "text": "User: JSHandle@object", "args": ["User:", {"id": 1, "name": "Alice"}], "location": {"url": "...", "lineNumber": 1, "columnNumber": 0}}
```

You can match against any part of this JSON string, including expanded object arguments.

#### Structured dict patterns (pyproject.toml only)

Dict entries let you scope ignore rules precisely by URL and/or message.

**Finding the source URL:** the easiest way is to look at `console_logs.log` in a failed test's artifact directory. Each line includes the full location, e.g.:

```json
{"type": "error", "text": "deprecated API", "args": [], "location": {"url": "https://cdn.example.com/analytics.js?v=2", "lineNumber": 1, "columnNumber": 0}}
```

Copy the relevant part of the URL and use it as the `file` regex (remember to escape `.` as `\\.`).

- `domain` — regex-free way to ignore a hostname and its subdomains (e.g., `example.com` matches `http://example.com`, `https://api.example.com`, etc.). Must be a valid domain name.
- `file` — regex matched against the console message's source URL
- `message` — optional; regex matched against the raw console text

If only `domain` or `file` is given, **all** messages from matching URLs are ignored. If both are given with `message`, **both** must match (AND logic).

```toml
playwright_console_ignore = [
  # Ignore everything from a third-party bundle
  { file = "vendor/sentry\\.js" },
  # Ignore all errors from a specific domain
  { domain = "google-analytics.com" },
  # Ignore only deprecation warnings from analytics
  { file = "analytics\\.js", message = "deprecated.*" },
]
```

You can also pass dict patterns directly to `assert_no_console_errors`:

```python
assert_no_console_errors(
    request,
    ignore=[
        {"domain": "example.com"},
        {"file": r"analytics\.js", "message": r"deprecated.*"},
    ],
)
```

### Change artifact output directory

By default, artifacts are saved to `test-results/`. You can customize this:

**Command line:**
```bash
pytest --playwright-artifacts-output=my-artifacts
```

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
playwright_artifacts_output = "my-artifacts"
```

## Related Projects

- [pytest-playwright-visual-snapshot](https://github.com/iloveitaly/pytest-playwright-visual-snapshot): Adds visual regression testing capabilities to your Playwright and pytest suite.
- [playwright-trace-analyzer](https://github.com/iloveitaly/playwright-trace-analyzer): Provides a CLI for inspecting Playwright trace files without needing the full browser viewer.
- [pytest-plugin-utils](https://github.com/iloveitaly/pytest-plugin-utils): Offers reusable logic for managing artifacts and configurations when building other pytest plugins.
- [gh-clean-artifacts](https://github.com/iloveitaly/gh-clean-artifacts): Helps manage storage costs by pruning old or large GitHub Actions artifacts.
- [pytest-line-runner](https://github.com/iloveitaly/pytest-line-runner): Simplifies test execution by allowing you to run pytest tests using file line numbers.
- [pytest-celery-utils](https://github.com/iloveitaly/pytest-celery-utils): Enables inspection of Celery task queues in Redis directly from your pytest environment.
- [python-package-prompts](https://github.com/iloveitaly/python-package-prompts): Contains LLM instructions for maintaining Python standards across projects using pytest and other libraries.

## [MIT License](LICENSE.md)

---

*This project was created from [iloveitaly/python-package-template](https://github.com/iloveitaly/python-package-template)*
