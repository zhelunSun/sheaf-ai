"""
Sheaf — Your personal knowledge layer.

Paste a link, AI does the rest.
"""

from importlib.metadata import version as _version

try:
    __version__ = _version("sheaf-ai")
except Exception:
    __version__ = "0.0.0-dev"
