"""
Path handling utilities for pytest artifact management.

This module contains logic for determining where artifacts should be stored
for individual tests, including sanitization of test names and resolution
of output directories. The artifact directory option name can be customized
via set_artifact_dir_option().
"""

import re
from pathlib import Path

import pytest

from .config import get_pytest_option

_artifact_dir_option: str = f"{__package__}_output"


def set_artifact_dir_option(option_name: str) -> None:
    """
    Set the pytest option name used for the artifact output directory.

    This function should typically be called in pytest_configure() to customize
    the option name before any tests run. It allows this module to be reused
    by other pytest plugins that need different option names.

    Example:
        # In your conftest.py or plugin module:
        from pytest_playwright_artifacts.paths import set_artifact_dir_option
        from pytest_playwright_artifacts.config import set_pytest_option

        def pytest_configure(config):
            # Register your custom option
            set_pytest_option(
                "my_artifacts_output",
                default="my-test-results",
                help="Directory for test artifacts",
                available="cli_option",
                type_hint=str,
            )
            # Configure paths module to use it
            set_artifact_dir_option("my_artifacts_output")

    Args:
        option_name: The pytest option name (without '--' prefix, with underscores).
    """
    global _artifact_dir_option
    _artifact_dir_option = option_name


def get_artifact_dir_option() -> str:
    """
    Get the currently configured artifact directory option name.

    Returns:
        The pytest option name used for the artifact output directory.
    """
    return _artifact_dir_option


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

    This function determines the root output directory based on the configured
    artifact directory option (see set_artifact_dir_option). It then creates
    a subdirectory for the specific test item using its sanitized nodeid.

    Args:
        item: The pytest.Item (test case) for which to get the directory.

    Returns:
        A pathlib.Path object pointing to the specific test's artifact directory.
        The directory and its parents are created if they do not exist.
    """
    output_path = get_pytest_option(item.config, _artifact_dir_option, type_hint=Path)
    assert output_path
    output_path.mkdir(exist_ok=True)

    per_test_dir = output_path / sanitize_for_artifacts(item.nodeid)
    per_test_dir.mkdir(parents=True, exist_ok=True)
    return per_test_dir
