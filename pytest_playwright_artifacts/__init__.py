import logging

from pytest_playwright_artifacts.assertions import assert_no_console_errors

from .version import __version__

log = logging.getLogger(__name__)

__all__ = ["assert_no_console_errors", "__version__"]
