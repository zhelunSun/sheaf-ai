"""
Sheaf Exceptions — structured error hierarchy for the Sheaf CLI and library.

Usage in CLI:
    from sheaf_ai.exceptions import SheafError, NetworkError
    try:
        ...
    except NetworkError as e:
        print(f"Network error: {e}")

Usage in library code:
    raise ConfigError("Missing API key", key="SHEAF_API_KEY")
"""


class SheafError(Exception):
    """Base exception for all Sheaf errors."""
    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context


class NetworkError(SheafError):
    """Network connectivity or API call failure."""
    pass


class ConfigError(SheafError):
    """Missing or invalid configuration (API keys, paths, etc.)."""
    pass


class StorageError(SheafError):
    """File I/O or data storage failure."""
    pass


class ParseError(SheafError):
    """Content parsing or extraction failure."""
    pass


class LLMError(SheafError):
    """LLM API call failure (rate limit, bad response, etc.)."""
    pass
