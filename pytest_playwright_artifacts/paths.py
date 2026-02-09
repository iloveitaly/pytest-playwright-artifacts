"""
Path handling utilities for pytest-playwright-artifacts.

This module contains logic for determining where artifacts should be stored
for individual tests, including sanitization of test names and resolution
of output directories.

Constants:
    PLAYWRIGHT_ARTIFACTS_OUTPUT_VAR: The name of the pytest option for the output directory.
"""

import re
from pathlib import Path

import pytest

PLAYWRIGHT_ARTIFACTS_OUTPUT_VAR = "playwright_artifacts_output"


def sanitize_for_artifacts(text: str) -> str:
    """
    Sanitize a test nodeid or name for use as a directory name.

    This function replaces characters that are not alphanumeric or hyphens
    with a single hyphen, and removes leading/trailing hyphens. This ensures
    that the resulting string is safe to use as a directory name on most
    file systems.

    Example:
        >>> sanitize_for_artifacts("test_file.py::test_func[param]")
        'test-file-py-test-func-param'

    Args:
        text: The text to sanitize (e.g., a test nodeid).

    Returns:
        A sanitized string safe for use as a directory name.
    """
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", text)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "unknown-test"


def get_artifact_dir(item: pytest.Item) -> Path:
    """
    Get or create the artifact directory for a specific test item.

    This function determines the root output directory based on the
    `--playwright-artifacts-output` CLI option (defaults to 'test-results').
    It then creates a subdirectory for the specific test item using its
    sanitized nodeid.

    Args:
        item: The pytest.Item (test case) for which to get the directory.

    Returns:
        A pathlib.Path object pointing to the specific test's artifact directory.
        The directory and its parents are created if they do not exist.
    """
    output_dir = (
        item.config.getoption(PLAYWRIGHT_ARTIFACTS_OUTPUT_VAR) or "test-results"
    )
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    per_test_dir = output_path / sanitize_for_artifacts(item.nodeid)
    per_test_dir.mkdir(parents=True, exist_ok=True)
    return per_test_dir
