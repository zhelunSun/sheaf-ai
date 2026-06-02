"""
Sheaf Exceptions — structured error hierarchy for the Sheaf CLI and library.

Usage in CLI:
    from sheaf_ai.exceptions import SheafError, NetworkError
    try:
        ...
    except NetworkError as e:
        print(f"Network error: {e}")
        sys.exit(EXIT_CODES["NETWORK"])

Usage in library code:
    raise ConfigError("Missing API key", key="SHEAF_API_KEY")

Exits codes:
    SUCCESS=0, PARTIAL=1, DUPLICATE=2, QUALITY=3,
    NETWORK=4, CONFIG=5, LLM=6, STORAGE=7
"""
import sys


# ── Semantic exit codes ──────────────────────────────────────────────
EXIT_CODES = {
    "SUCCESS": 0,
    "PARTIAL": 1,
    "DUPLICATE": 2,
    "QUALITY": 3,
    "NETWORK": 4,
    "CONFIG": 5,
    "LLM": 6,
    "STORAGE": 7,
}

# Reverse mapping: exception class → exit code key
_EXCEPTION_EXIT_MAP: dict[type, str] = {}


def _register_exit(exc_cls: type, code_key: str) -> None:
    _EXCEPTION_EXIT_MAP[exc_cls] = code_key


def get_exit_code(exc: Exception) -> int:
    """Resolve a semantic exit code from an exception instance.

    Walks the MRO of the exception class so a subclass inherits
    its parent's exit code unless explicitly overridden.
    """
    for cls in type(exc).__mro__:
        for exc_cls, code_key in _EXCEPTION_EXIT_MAP.items():
            if cls is exc_cls:
                return EXIT_CODES.get(code_key, 1)
    return 1


def get_exit_code_from_key(key: str) -> int:
    """Resolve an exit code from a string key."""
    return EXIT_CODES.get(key, 1)


# ── Exception hierarchy ──────────────────────────────────────────────

class SheafError(Exception):
    """Base exception for all Sheaf errors."""
    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context


class NetworkError(SheafError):
    """Network connectivity or API call failure."""
    pass


_register_exit(NetworkError, "NETWORK")


class NetworkTimeoutError(NetworkError):
    """Network request timed out."""
    pass


class JSRenderingRequiredError(SheafError):
    """Content requires JS rendering (SPA site, Playwright not available)."""
    pass


_register_exit(JSRenderingRequiredError, "PARTIAL")


class ConfigError(SheafError):
    """Missing or invalid configuration (API keys, paths, etc.)."""
    pass


_register_exit(ConfigError, "CONFIG")


class StorageError(SheafError):
    """File I/O or data storage failure."""
    pass


_register_exit(StorageError, "STORAGE")


class ParseError(SheafError):
    """Content parsing or extraction failure."""
    pass


_register_exit(ParseError, "QUALITY")


class LLMError(SheafError):
    """LLM API call failure (rate limit, bad response, etc.)."""
    pass


_register_exit(LLMError, "LLM")


class DuplicateError(SheafError):
    """Duplicate entry detected."""
    pass


_register_exit(DuplicateError, "DUPLICATE")


class QualityError(SheafError):
    """Content quality check failed."""
    pass


_register_exit(QualityError, "QUALITY")
