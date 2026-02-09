import typing as t
from dataclasses import dataclass

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
    cast: t.Callable[[t.Any], t.Any] | None


_REGISTRY: list[_OptionDef] = []
"configuration options this plugin wants to expose to pytest"


def set_pytest_option(
    name: str,
    default: t.Any = None,
    *,
    help: str = "",
    available: t.Literal["all", "ini", "cli_option", None] = None,
    cast: t.Callable[[t.Any], t.Any] | None = None,
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
        cast: Optional type caster (e.g. int, bool).
    """
    _REGISTRY.append(
        _OptionDef(
            name=name, default=default, help_text=help, available=available, cast=cast
        )
    )


def register_pytest_options(parser: Parser) -> None:
    """
    Must be called within `pytest_addoption` to register CLI/INI flags.
    """
    for opt in _REGISTRY:
        # CLI Registration
        if opt.available in ("all", "cli_option"):
            cli_name = f"--{opt.name.replace('_', '-')}"
            # CRITICAL: We set default=None here so CLI allows fallback to INI/Runtime
            parser.addoption(cli_name, action="store", default=None, help=opt.help_text)

        # INI Registration
        if opt.available in ("all", "ini"):
            # We set default=None here so INI allows fallback to Runtime default
            parser.addini(opt.name, help=opt.help_text, default=None)


def get_pytest_option[T](
    config: Config, key: str, *, cast: t.Callable[[t.Any], T] | None = None
) -> T | t.Any | None:
    """
    Retrieve an option.

    Priority: runtime overrides (config.option) > INI > default (set_pytest_option).
    """
    normalized_key = key.replace("-", "_")

    val = getattr(config.option, normalized_key, None)

    if val in (None, ""):
        try:
            val = config.getini(normalized_key)
        except (ValueError, KeyError):
            val = None

    if val in (None, ""):
        opt = next((entry for entry in _REGISTRY if entry.name == normalized_key), None)
        if opt is not None:
            val = opt.default

    if val is not None and cast:
        try:
            return cast(val)
        except (ValueError, TypeError):
            return val

    if val is not None:
        opt = next((entry for entry in _REGISTRY if entry.name == normalized_key), None)
        if opt is not None and opt.cast:
            try:
                return opt.cast(val)
            except (ValueError, TypeError):
                return val

    return val
