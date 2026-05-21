"""Integration tests for console message capture and filtering with a real browser."""

import pytest

from pytest_playwright_artifacts import assert_no_console_errors


def _fire_console_error(page, message: str) -> None:
    # page.evaluate() dispatches the CDP console event asynchronously, so wrap in
    # expect_console_message() to block until Playwright has processed the event
    # and our log_console handler has been called before we check the logs.
    with page.expect_console_message():
        page.evaluate(f"console.error({repr(message)})")


def _serve_script(page, url: str, body: str) -> None:
    # route a fake script URL so console messages carry a real location.url
    page.route(
        url, lambda route: route.fulfill(content_type="text/javascript", body=body)
    )
    with page.expect_console_message():
        page.add_script_tag(url=url)


def test_console_error_is_captured(page, request):
    """A real console.error is captured and fails assert_no_console_errors."""
    _fire_console_error(page, "real error")

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(request)


def test_plain_string_ignore_filters_by_message(page, request):
    """Plain regex matching message text suppresses the error."""
    _fire_console_error(page, "Invalid Sentry Dsn: abc123")

    assert_no_console_errors(request, ignore=[r"Invalid Sentry Dsn:.*"])


def test_plain_string_ignore_does_not_over_filter(page, request):
    """Non-matching errors still fail when an unrelated ignore pattern is present."""
    _fire_console_error(page, "real error")
    _fire_console_error(page, "Invalid Sentry Dsn: abc123")

    with pytest.raises(AssertionError) as exc_info:
        assert_no_console_errors(request, ignore=[r"Invalid Sentry Dsn:.*"])

    assert "real error" in str(exc_info.value)
    assert "Sentry" not in str(exc_info.value)


def test_file_only_ignore_suppresses_all_errors_from_url(page, request):
    """Dict pattern with only `file` ignores every error from the matching URL."""
    _serve_script(
        page, "https://cdn.example.com/analytics.js", "console.error('any error');"
    )

    assert_no_console_errors(request, ignore=[{"file": r"analytics\.js"}])


def test_file_only_ignore_does_not_affect_other_urls(page, request):
    """File-only pattern does not suppress errors from non-matching URLs."""
    _fire_console_error(page, "error from app code")

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(request, ignore=[{"file": r"analytics\.js"}])


def test_file_and_message_ignore_suppresses_matching_error(page, request):
    """Dict pattern with `file` + `message` suppresses errors when both match."""
    _serve_script(
        page,
        "https://cdn.example.com/tracking.js",
        "console.error('deprecated API called');",
    )

    assert_no_console_errors(
        request,
        ignore=[{"file": r"tracking\.js", "message": r"deprecated.*"}],
    )


def test_file_and_message_ignore_keeps_non_matching_message(page, request):
    """Dict pattern with `file` + `message` keeps errors whose message doesn't match."""
    _serve_script(
        page,
        "https://cdn.example.com/tracking.js",
        "console.error('network failure');",
    )

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(
            request,
            ignore=[{"file": r"tracking\.js", "message": r"deprecated.*"}],
        )


def test_file_and_message_ignore_keeps_matching_message_from_wrong_file(page, request):
    """Dict pattern with `file` + `message` keeps errors from non-matching URLs."""
    _serve_script(
        page,
        "https://cdn.example.com/app.js",
        "console.error('deprecated API called');",
    )

    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(
            request,
            ignore=[{"file": r"tracking\.js", "message": r"deprecated.*"}],
        )


def test_multiple_ignore_patterns(page, request):
    """Multiple patterns in the ignore list all apply."""
    _serve_script(
        page,
        "https://cdn.example.com/analytics.js",
        "console.error('analytics noise');",
    )
    _fire_console_error(page, "Invalid Sentry Dsn: abc")

    assert_no_console_errors(
        request,
        ignore=[
            r"Invalid Sentry Dsn:.*",
            {"file": r"analytics\.js"},
        ],
    )


def test_domain_ignore_matches_exact_domain(page, request):
    """'domain' key ignores errors from the exact domain (including protocol)."""
    _serve_script(
        page, "https://example.com/app.js", "console.error('exact domain error')"
    )
    assert_no_console_errors(request, ignore=[{"domain": "example.com"}])


def test_domain_ignore_matches_subdomains(page, request):
    """'domain' key ignores errors from subdomains by default."""
    _serve_script(
        page, "https://api.example.com/app.js", "console.error('subdomain error')"
    )
    assert_no_console_errors(request, ignore=[{"domain": "example.com"}])


def test_domain_ignore_does_not_match_similar_domains(page, request):
    """'domain' key is strict about hostname boundaries."""
    # Matches part of the string but not as a domain boundary
    _serve_script(
        page, "https://badexample.com/app.js", "console.error('similar domain error')"
    )
    with pytest.raises(AssertionError, match="Console errors found"):
        assert_no_console_errors(request, ignore=[{"domain": "example.com"}])


def test_console_error_with_js_error_object(page, request):
    """console.error() with a JS Error arg causes INTERNALERROR via non-serializable arg.json_value()."""
    with page.expect_console_message():
        page.evaluate("console.error('failed:', new Error('boom'))")

    with pytest.raises(AssertionError):
        assert_no_console_errors(request)


def test_domain_validation_rejects_invalid_inputs(page, request):
    """'domain' key validation ensures clean domain strings."""
    invalid_inputs = [
        "https://example.com",
        "example.com/path",
        "*.example.com",
        "example.com?",
        "not_a_domain",
    ]
    # Fire an error so that the ignore patterns are actually compiled/validated
    _fire_console_error(page, "trigger error")

    for domain in invalid_inputs:
        with pytest.raises(ValueError, match="Invalid domain name"):
            assert_no_console_errors(request, ignore=[{"domain": domain}])
