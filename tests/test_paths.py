"""Tests for paths.py artifact directory handling."""

from unittest.mock import Mock, patch

from pytest_playwright_artifacts.paths import (
    get_artifact_dir,
    get_artifact_dir_option,
    sanitize_for_artifacts,
    set_artifact_dir_option,
)


def test_set_and_get_artifact_dir_option():
    original = get_artifact_dir_option()

    try:
        set_artifact_dir_option("custom_option_name")
        assert get_artifact_dir_option() == "custom_option_name"
    finally:
        set_artifact_dir_option(original)


def test_sanitize_for_artifacts():
    nodeid = "test_file.py::TestClass::test_method[param-value]"
    result = sanitize_for_artifacts(nodeid)

    assert result == "test-file-py-TestClass-test-method-param-value"
    assert "::" not in result
    assert "[" not in result
    assert "]" not in result


def test_sanitize_for_artifacts_empty_string():
    result = sanitize_for_artifacts("")
    assert result == "unknown-test"


def test_sanitize_for_artifacts_only_special_chars():
    result = sanitize_for_artifacts(":::[[[]]]")
    assert result == "unknown-test"


def test_get_artifact_dir(tmp_path):
    mock_item = Mock()
    mock_item.nodeid = "test_module.py::test_function"
    mock_item.config = Mock()

    output_dir = tmp_path / "test-output"

    with patch(
        "pytest_playwright_artifacts.paths.get_pytest_option", return_value=output_dir
    ):
        result = get_artifact_dir(mock_item)

        expected = output_dir / "test-module-py-test-function"
        assert result == expected
        assert result.exists()
        assert output_dir.exists()
