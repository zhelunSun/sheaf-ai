"""Minimal terminal styling — ANSI only, zero dependencies.

Keeps the CLI output readable without adding rich/colorama to the wheel.
Respects the environment: disables color when stdout is not a TTY, when
``NO_COLOR`` is set (https://no-color.org), or when ``TERM=dumb``.

Usage:
    from sheaf_ai.term import dim, bold, green, style
    print(f"{bold(title)}  {dim(meta)}")
    style(text, "bold", "cyan")          # combine codes
"""
from __future__ import annotations

import os
import sys

_RESET = "\033[0m"
_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "underline": "\033[4m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}


def supports_color(stream=None) -> bool:
    """True iff we should emit ANSI escapes on ``stream`` (default stdout)."""
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def style(text: str, *codes: str) -> str:
    """Wrap ``text`` in the given ANSI codes; no-op when color is disabled."""
    if not supports_color():
        return text
    prefix = "".join(_CODES[c] for c in codes if c in _CODES)
    if not prefix:
        return text
    return f"{prefix}{text}{_RESET}"


# ── Convenience wrappers ──────────────────────────────────────
def dim(text: str) -> str:
    return style(text, "dim")


def bold(text: str) -> str:
    return style(text, "bold")


def green(text: str) -> str:
    return style(text, "green")


def yellow(text: str) -> str:
    return style(text, "yellow")


def red(text: str) -> str:
    return style(text, "red")


def cyan(text: str) -> str:
    return style(text, "cyan")


def gray(text: str) -> str:
    return style(text, "gray")
