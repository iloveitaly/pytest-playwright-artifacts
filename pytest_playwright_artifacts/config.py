import typing as t
from dataclasses import dataclass

from _pytest.config import Config
from _pytest.config.argparsing import Parser

# --- Internal Registry ---


@dataclass
class _OptionDef:
    name: str
    default: t.Any
    help_text: str
    available: t.Literal["all", "ini", "cli_option", None]
    cast: t.Callable[[t.Any], t.Any] | None


_REGISTRY: list[_OptionDef] = []

# --- Public Interface ---


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


def write_pytest_options(config: Config) -> None:
    """
    Resolves and writes final values to `config.option`.
    Must be called within `pytest_configure`.

    This enforces the priority: CLI > INI > Default (Runtime).
    """
    for opt in _REGISTRY:
        # 1. Check if CLI set it (Priority #1)
        # getattr is safe because we might have unregistered options (available=None)
        val = getattr(config.option, opt.name, None)

        # 2. Check if INI set it (Priority #2)
        if val in (None, ""):
            try:
                # Only check INI if we actually registered it or if it's a standard key
                val = config.getini(opt.name)
            except (ValueError, KeyError):
                val = None

        # 3. Use the Default provided in set_pytest_option (Priority #3)
        if val in (None, ""):
            val = opt.default

        # 4. Apply Casting
        if val is not None and opt.cast:
            try:
                val = opt.cast(val)
            except (ValueError, TypeError):
                # If cast fails, keep raw value (or log warning)
                pass

        # 5. WRITE BACK: Force the resolved value into config.option
        # This makes config.option the Single Source of Truth for the session.
        setattr(config.option, opt.name, val)


def get_pytest_option[T](
    config: Config, key: str, *, cast: t.Callable[[t.Any], T] | None = None
) -> T | t.Any | None:
    """
    Retrieve an option.

    Since `write_pytest_options` normalizes everything into `config.option`,
    this is now a simple lookup.
    """
    val = getattr(config.option, key, None)

    if val is not None and cast:
        return cast(val)
    return val
