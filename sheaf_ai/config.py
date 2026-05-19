"""
Sheaf Config — shared constants, paths, and configuration.

All modules import from here for single-source-of-truth paths.
"""
import sys
import os
from pathlib import Path

# Project root (where .env, prompts/, data/ live)
# Works both in dev (repo root) and pip-installed (package parent)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories — default to ./data relative to cwd, configurable via env
_DATA_ROOT = Path(os.environ.get("SHEAF_DATA_DIR", str(Path.cwd() / "data")))
DATA_DIR = _DATA_ROOT
ENTRIES_DIR = DATA_DIR / "entries"
SUMMARIES_DIR = DATA_DIR / "summaries"
RAW_DIR = DATA_DIR / "raw"
INDEX_FILE = DATA_DIR / "index.jsonl"
TAGS_REGISTRY_FILE = DATA_DIR / "tags_registry.json"

# Beijing timezone
from datetime import timezone, timedelta
BJT = timezone(timedelta(hours=8))

# Default LLM models
CLASSIFY_MODEL = "deepseek-ai/DeepSeek-V3.2"
SUMMARIZE_MODEL = "deepseek-ai/DeepSeek-V3.2"

# Version (single source)
from sheaf_ai import __version__

VERSION = __version__


def ensure_data_dirs():
    """Create data directories if they don't exist."""
    for d in [DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_prompt(name: str) -> str:
    """Load a prompt file. Works both in dev and pip-installed mode.

    Search order:
      1. PROJECT_ROOT/prompts/ (dev mode, repo root)
      2. Package-bundled prompts/ (pip installed via importlib.resources)
    """
    # Dev mode: repo root / prompts / name
    path = PROJECT_ROOT / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")

    # Pip-installed: use importlib.resources to find bundled prompts
    try:
        from importlib.resources import files
        prompts_pkg = files("prompts")
        prompt_file = prompts_pkg.joinpath(name)
        return prompt_file.read_text(encoding="utf-8")
    except Exception:
        pass

    return ""


def fix_windows_encoding():
    """Fix Windows GBK console encoding for Unicode output."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
