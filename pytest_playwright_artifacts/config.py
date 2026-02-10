"""
Pytest option registry and resolution helpers for this plugin.

Options are registered once, then resolved at read time with a consistent
precedence: runtime overrides > INI > defaults from the registry.
"""

import typing as t
import warnings
from dataclasses import dataclass
from pathlib import Path

from _pytest.config import Config
from _pytest.config.argparsing import Parser


@dataclass
class _OptionDef:
    """
    Internal representation of the options this plugin wants to expose to pytest.
    """

    name: str
    default: t.Any
    help_text: str
    available: t.Literal["all", "ini", "cli_option", None]
    type_hint: t.Any | None
    ini_type: str | None


_REGISTRY: list[_OptionDef] = []
"configuration options this plugin wants to expose to pytest"


def _infer_ini_type(type_hint: t.Any) -> str | None:
    """
    Infer the pytest INI type string from a Python type hint.

    Supported mappings:
    - bool -> "bool"
    - str -> "string"
    - list[str] -> "linelist"
    - list[Path] -> "paths"

    Unsupported/Not inferred:
    - "args" (list of whitespace-separated strings)
    - "pathlist" (legacy alias for "paths")
    """
    if type_hint is bool:
        return "bool"
    if type_hint is str:
        return "string"

    origin = t.get_origin(type_hint)
    args = t.get_args(type_hint)

    if origin is list:
        if args and args[0] is str:
            return "linelist"
        if args and issubclass(args[0], Path):
            return "paths"

    return None


def set_pytest_option(
    name: str,
    default: t.Any = None,
    *,
    help: str = "",
    available: t.Literal["all", "ini", "cli_option", None] = None,
    type_hint: t.Any | None = None,
) -> None:
    """
    Define a pytest option.

    This queues the option for registration (hook_addoption) and
    configuration (hook_configure).

    Args:
        name: The key name (e.g. "api_url"). Use underscores.
        default: The fallback value if not provided via CLI or INI.
        help: Help text for the CLI/INI description.
        available: Where this option should be exposed to the user.
                   - 'cli_option': Adds a --flag.
                   - 'ini': Adds a value to pytest.ini.
                   - 'all': Adds both.
                   - None: Purely internal/runtime (set via code only).
        type_hint: Optional Python type hint (e.g. bool, list[str]) used for
                   validation and INI type inference.
    """
    ini_type = _infer_ini_type(type_hint)
    _REGISTRY.append(
        _OptionDef(
            name=name,
            default=default,
            help_text=help,
            available=available,
            type_hint=type_hint,
            ini_type=ini_type,
        )
    )


def register_pytest_options(parser: Parser) -> None:
    """
    Must be called within `pytest_addoption` to register CLI/INI flags.
    """
    for opt in _REGISTRY:
        help_text = opt.help_text
        if opt.default is not None:
            help_text = f"{opt.help_text} (default: {opt.default})"

        # CLI Registration
        if opt.available in ("all", "cli_option"):
            cli_name = f"--{opt.name.replace('_', '-')}"
            # CRITICAL: We set default=None here so CLI allows fallback to INI/Runtime
            parser.addoption(cli_name, action="store", default=None, help=help_text)

        # INI Registration
        if opt.available in ("all", "ini"):
            # We set default=None here so INI allows fallback to Runtime default
            parser.addini(opt.name, help=help_text, default=None, type=opt.ini_type)


def _smart_cast[T](value: t.Any, type_hint: type[T] | None) -> T | t.Any:
    """
    Cast a value to the expected type if it's not already correct.
    This handles cases where CLI arguments (always strings) need conversion,
    or where default values might not match the strict type.
    """
    if type_hint is None:
        return value

    # Handle GenericAlias types (e.g. list[str]) for isinstance checks
    origin = t.get_origin(type_hint)
    check_type = origin if origin is not None else type_hint

    try:
        if isinstance(value, check_type):
            return value
    except TypeError:
        # Fallback if isinstance fails (e.g. some complex types)
        pass

    if value is None:
        return None

    # Casting logic for strings (from CLI or raw defaults)
    if type_hint is bool and isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")

    if type_hint is int and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass  # Let it fail downstream or raise TypeError below

    if origin is list and isinstance(value, str):
        # Fallback for CLI list parsing (comma or newline separated?)
        # For 'linelist' INI types, pytest handles newlines.
        # For CLI, let's assume we might get a single string that needs splitting?
        # Or maybe we just return it wrapped in a list?
        # The user instructions suggested:
        # "return [v.strip() for v in value.splitlines() if v.strip()]"
        return [v.strip() for v in value.splitlines() if v.strip()]

    # If we can't cast it safely, return as is (or raise if strictness required)
    # The plan said "Raise TypeError if casting fails or type is unhandled"
    # but strictly raising might break existing lenient behaviors.
    # We'll try to follow the plan's strictness for now.
    raise TypeError(f"Cannot cast value of type {type(value)} to {type_hint}")


def get_pytest_option[T](
    config: Config, key: str, *, type_hint: type[T] | None = None
) -> T | t.Any | None:
    """
    Retrieve a configuration value from runtime overrides, CLI, or INI files.

    Priority chain:
    1. Runtime overrides (via config.option in pytest_configure)
    2. CLI arguments (e.g., --my-key)
    3. Configuration files (pytest.ini, pyproject.toml)

    Args:
            config: The pytest Config object.
            key: The option name (use underscores).
            type_hint: Optional expected type for validation and smart casting.

    Returns:
            The resolved value, optionally casted. Returns None if not found.
    """
    normalized_key = key.replace("-", "_")
    opt = next((entry for entry in _REGISTRY if entry.name == normalized_key), None)

    # Validation
    if type_hint is not None and opt is not None and opt.type_hint is not None:
        if type_hint != opt.type_hint:
            warnings.warn(
                f"Type mismatch for option '{key}': requested {type_hint}, configured {opt.type_hint}"
            )

    # CLI/runtime value from config.option (argparse Namespace)
    val = getattr(config.option, normalized_key, None)

    if val in (None, ""):
        # INI value from pytest.ini or pyproject.toml
        try:
            val = config.getini(normalized_key)
        except (ValueError, KeyError):
            val = None

    if val in (None, ""):
        # Default value from the registry
        if opt is not None:
            val = opt.default

    # Determine effective type hint
    effective_type_hint = type_hint
    if effective_type_hint is None and opt is not None:
        effective_type_hint = opt.type_hint

    # Smart cast
    if val is not None and effective_type_hint is not None:
        try:
            return _smart_cast(val, effective_type_hint)
        except TypeError as e:
            # warning? or just return val?
            # Let's log a warning and return val to be safe
            warnings.warn(f"Failed to cast option '{key}': {e}")
            return val

    return val
