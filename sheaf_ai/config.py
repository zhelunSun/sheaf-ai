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


def _load_env_file():
    """Load a local .env file once, without overriding real environment variables."""
    for env_path in [Path.cwd() / ".env", PROJECT_ROOT / ".env"]:
        if not env_path.exists():
            continue
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        break


_load_env_file()


# Data directories — three-tier resolution:
#   1. SHEAF_DATA_DIR env var (explicit override, highest priority)
#   2. ./data if CWD has project markers (.git, .env, .sheaf) — local-first dev mode
#   3. ~/.sheaf/data — stable fallback for MCP server / agent context
def _resolve_data_root() -> Path:
    explicit = os.environ.get("SHEAF_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit)
    cwd = Path.cwd()
    for marker in (".git", ".env", ".sheaf"):
        if (cwd / marker).exists():
            return cwd / "data"
    return Path.home() / ".sheaf" / "data"


_DATA_ROOT = _resolve_data_root()
DATA_DIR = _DATA_ROOT
ENTRIES_DIR = DATA_DIR / "entries"
SUMMARIES_DIR = DATA_DIR / "summaries"
RAW_DIR = DATA_DIR / "raw"
INDEX_FILE = DATA_DIR / "index.jsonl"
TAGS_REGISTRY_FILE = DATA_DIR / "tags_registry.json"

# Beijing timezone
from datetime import timezone, timedelta
BJT = timezone(timedelta(hours=8))

# Optional model overrides. None lets llm_client choose the provider default.
CLASSIFY_MODEL = os.environ.get("CLASSIFY_MODEL") or os.environ.get("DEFAULT_MODEL") or None
SUMMARIZE_MODEL = os.environ.get("SUMMARIZE_MODEL") or os.environ.get("DEFAULT_MODEL") or None

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
