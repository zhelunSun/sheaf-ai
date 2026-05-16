"""
UC Core — shared constants, paths, and configuration.

All modules import from here for single-source-of-truth paths.
"""
import sys
import os
from pathlib import Path

# Project root (where .env, prompts/, data/ live)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
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
from uc import __version__

VERSION = __version__


def ensure_data_dirs():
    """Create data directories if they don't exist."""
    for d in [DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/"""
    path = PROJECT_ROOT / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def fix_windows_encoding():
    """Fix Windows GBK console encoding for Unicode output."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
