# Capture debugging artifacts on Playwright test failures

[![Release Notes](https://img.shields.io/github/release/iloveitaly/pytest-playwright-artifacts)](https://github.com/iloveitaly/pytest-playwright-artifacts/releases)
[![Downloads](https://static.pepy.tech/badge/pytest-playwright-artifacts/month)](https://pepy.tech/project/pytest-playwright-artifacts)
![GitHub CI Status](https://github.com/iloveitaly/pytest-playwright-artifacts/actions/workflows/build_and_publish.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

When your Playwright tests fail, you need to see what went wrong. This pytest plugin does a couple things to make it easier to debug and build playwight tests:

1. Automatically captures HTML, screenshots, console logs, and failure summaries the moment a test fails and dumps them into a per-test folder for easy debugging.
2. Allows you to assert that no console errors were logged during a test.
3. Automatically retry tests that fail due to playwright flakiness

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

### Fail tests on console errors

```python
from pytest_playwright_artifacts import assert_no_console_errors

def test_no_console_errors(page, request):
    page.goto("https://example.com")
    assert_no_console_errors(request)
```

This fails the test if any `console.error()` messages were logged during the test.

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
  "\\[Meta Pixel\\].*",
]
```

Patterns match against both the raw console text and the formatted log line.

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
