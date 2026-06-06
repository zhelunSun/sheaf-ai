"""
Sheaf User Settings — local secure storage for API keys and provider config.

Storage:
    macOS/Linux: ~/.sheaf/config.json  (permissions 0600)
    Windows:     %USERPROFILE%/.sheaf/config.json

Priority (highest first):
    1. CLI arguments (--api-key, --provider)
    2. Environment variables (OPENAI_API_KEY, etc.) + .env file
    3. User config file (~/.sheaf/config.json)
    4. Interactive prompt (fallback, only in TTY)

Usage:
    from sheaf_ai.settings import get_api_key, get_provider_config, list_providers
"""
from __future__ import annotations
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from sheaf_ai.providers import PROVIDERS as _PROVIDER_REGISTRY

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".sheaf"
CONFIG_FILE = CONFIG_DIR / "config.json"

def _ensure_config_dir() -> None:
    """Create config directory with restrictive permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        # Unix: 0700 (owner read/write/execute only)
        os.chmod(CONFIG_DIR, stat.S_IRWXU)


def _load_config() -> dict[str, Any]:
    """Load user config from ~/.sheaf/config.json."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_config(cfg: dict[str, Any]) -> None:
    """Save user config to ~/.sheaf/config.json with secure permissions."""
    _ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    if sys.platform != "win32":
        # Unix: 0600 (owner read/write only)
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_providers() -> list[dict[str, Any]]:
    """Return list of registered providers for UI display."""
    return [
        {"id": k, **v} for k, v in _PROVIDER_REGISTRY.items()
    ]


def get_provider_config(provider: str | None = None) -> dict[str, Any] | None:
    """Get config for a provider from user config file.

    Returns None if not configured.
    """
    cfg = _load_config()
    providers = cfg.get("providers", {})
    if provider is None:
        provider = cfg.get("default_provider", "openai")
    return providers.get(provider)


def get_api_key(
    provider: str | None = None,
    env_var: str | None = None,
) -> str | None:
    """Resolve API key with priority: env > config file > interactive.

    Args:
        provider: Provider ID (openai, deepseek, etc.)
        env_var:  Explicit env var name (overrides provider default)

    Returns:
        API key string, or None if not found (and not interactive).
    """
    # 1. Environment variable
    if env_var:
        key = os.environ.get(env_var, "").strip()
        if key:
            return key

    # Resolve provider default env var
    provider = provider or os.environ.get("DEFAULT_PROVIDER", "openai")
    reg = _PROVIDER_REGISTRY.get(provider, {})
    default_env = reg.get("api_key_env", f"{provider.upper()}_API_KEY")

    key = os.environ.get(default_env, "").strip()
    if key:
        return key

    # 2. User config file
    cfg = _load_config()
    pc = cfg.get("providers", {}).get(provider)
    if pc:
        key = (pc.get("api_key") or "").strip()
        if key:
            return key

    return None


def resolve_provider(
    provider: str | None = None,
) -> tuple[str, str, str]:
    """Resolve provider, returning (provider_id, api_key, base_url).

    Raises ValueError if API key cannot be resolved.
    """
    provider = provider or os.environ.get("DEFAULT_PROVIDER", "")
    cfg = _load_config()

    # If no provider specified, use default from config or fallback to openai
    if not provider:
        provider = cfg.get("default_provider", "openai")

    if provider not in _PROVIDER_REGISTRY:
        # Allow custom provider IDs from config
        if provider in cfg.get("providers", {}):
            pc = cfg["providers"][provider]
            key = get_api_key(provider)
            if not key:
                raise ValueError(
                    f"API Key not found for provider '{provider}'. "
                    f"Run: sheaf config set-key --provider {provider}"
                )
            return provider, key, pc.get("base_url", "")
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Available: {', '.join(_PROVIDER_REGISTRY.keys())}"
        )

    key = get_api_key(provider)
    if not key:
        # Build helpful guidance
        reg = _PROVIDER_REGISTRY[provider]
        env_name = reg["api_key_env"]
        lines = [
            f"⚠ 未检测到 API 密钥 ({env_name})",
            "",
            "快速配置（推荐交互式向导）：",
            "    sheaf config setup",
            "",
            "或手动设置环境变量：",
            f"    # macOS/Linux:  export {env_name}=你的密钥",
            f"    # Windows PS:   $env:{env_name}='你的密钥'",
            f"    # Windows CMD:  set {env_name}=你的密钥",
            "",
            "或创建 .env 文件：",
            f"    {env_name}=你的密钥",
        ]
        raise ValueError("\n".join(lines))

    reg = _PROVIDER_REGISTRY[provider]
    # Config file can override base_url
    pc = cfg.get("providers", {}).get(provider, {})
    base_url = pc.get("base_url") or reg.get("base_url", "")
    return provider, key, base_url


# ---------------------------------------------------------------------------
# Config commands (used by CLI)
# ---------------------------------------------------------------------------

def config_setup_interactive() -> dict[str, Any]:
    """Interactive wizard to set up provider credentials.

    Returns the updated config dict.
    """
    print("=" * 50)
    print("  Sheaf API Key 配置向导")
    print("=" * 50)
    print()
    print("支持的 Provider：")
    for i, p in enumerate(list_providers(), 1):
        print(f"  {i}. {p['name']} ({p['id']})")
    print()

    # Choose provider
    choices = [p["id"] for p in list_providers()]
    while True:
        choice = input("选择 Provider [1-6, 默认 1-OpenAI]: ").strip()
        if not choice:
            choice = "1"
        if choice.isdigit() and 1 <= int(choice) <= len(choices):
            provider = choices[int(choice) - 1]
            break
        if choice in choices:
            provider = choice
            break
        print(f"无效选择，请输 1-{len(choices)} 或 provider ID")

    reg = _PROVIDER_REGISTRY[provider]
    print(f"\n→ 配置 {reg['name']}")

    # API key (hidden input)
    env_hint = reg["api_key_env"]
    key = getpass.getpass(
        f"请输入 API Key [{env_hint}] (输入不会显示): "
    ).strip()
    if not key:
        print("⚠ 未输入 API Key，跳过配置")
        return _load_config()

    # Base URL (optional override)
    default_url = reg.get("base_url", "")
    url_input = input(
        f"Base URL [默认: {default_url or '留空'}]: "
    ).strip()
    base_url = url_input or default_url

    # Model (optional override)
    default_model = reg.get("default_model", "")
    model_input = input(
        f"默认 Model [默认: {default_model or '留空'}]: "
    ).strip()
    model = model_input or default_model

    # Save
    cfg = _load_config()
    if "providers" not in cfg:
        cfg["providers"] = {}
    cfg["providers"][provider] = {
        "api_key": key,
        "base_url": base_url,
        "default_model": model,
    }

    # Set as default if this is the first provider or user confirms
    if cfg.get("default_provider") is None:
        cfg["default_provider"] = provider
        print(f"✅ 已设置 {reg['name']} 为默认 provider")
    else:
        set_default = input(
            f"\n是否将 {reg['name']} 设为默认 provider? [y/N]: "
        ).strip().lower()
        if set_default in ("y", "yes"):
            cfg["default_provider"] = provider
            print(f"✅ 已切换默认 provider 为 {reg['name']}")

    _save_config(cfg)
    print(f"\n✅ 配置已保存到 {CONFIG_FILE}")
    if sys.platform != "win32":
        print("   文件权限已设置为仅当前用户可读")
    print()
    print("使用方式：")
    print("    sheaf collect <url>        # 使用默认 provider")
    print(f"    sheaf collect <url> --provider {provider}  # 指定 provider")
    return cfg


def config_set_key(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Set/update a provider's API key programmatically.

    If api_key is None, prompts interactively (secure, no echo).
    """
    if provider not in _PROVIDER_REGISTRY:
        # Allow arbitrary provider IDs
        pass

    if api_key is None:
        reg = _PROVIDER_REGISTRY.get(provider, {})
        env_hint = reg.get("api_key_env", f"{provider.upper()}_API_KEY")
        api_key = getpass.getpass(
            f"API Key for {provider} [{env_hint}]: "
        ).strip()

    if not api_key:
        raise ValueError("API Key cannot be empty")

    cfg = _load_config()
    if "providers" not in cfg:
        cfg["providers"] = {}
    if provider not in cfg["providers"]:
        cfg["providers"][provider] = {}

    cfg["providers"][provider]["api_key"] = api_key
    if base_url:
        cfg["providers"][provider]["base_url"] = base_url
    if model:
        cfg["providers"][provider]["default_model"] = model

    _save_config(cfg)
    return cfg


def config_list() -> list[dict[str, Any]]:
    """Return list of configured providers (keys masked)."""
    cfg = _load_config()
    providers = cfg.get("providers", {})
    default_provider = cfg.get("default_provider", "")
    result = []
    for pid, pc in providers.items():
        key = pc.get("api_key", "")
        masked = _mask_key(key)
        reg = _PROVIDER_REGISTRY.get(pid, {})
        result.append({
            "id": pid,
            "name": reg.get("name", pid),
            "api_key": masked,
            "base_url": pc.get("base_url", reg.get("base_url", "")),
            "default_model": pc.get("default_model", reg.get("default_model", "")),
            "is_default": pid == default_provider,
        })
    return result


def config_use(provider: str) -> dict[str, Any]:
    """Set the default provider."""
    cfg = _load_config()
    providers = cfg.get("providers", {})
    if provider not in providers and provider not in _PROVIDER_REGISTRY:
        raise ValueError(
            f"Provider '{provider}' not configured. "
            f"Run: sheaf config set-key --provider {provider}"
        )
    cfg["default_provider"] = provider
    _save_config(cfg)
    return cfg


def config_remove(provider: str) -> dict[str, Any]:
    """Remove a provider from config."""
    cfg = _load_config()
    if "providers" in cfg and provider in cfg["providers"]:
        del cfg["providers"][provider]
    if cfg.get("default_provider") == provider:
        # Pick another default if available
        remaining = list(cfg.get("providers", {}).keys())
        cfg["default_provider"] = remaining[0] if remaining else None
    _save_config(cfg)
    return cfg


def _mask_key(key: str) -> str:
    """Mask API key for display: sk-abc...xyz → sk-ab****xyz."""
    if len(key) <= 12:
        return "****" if key else "(not set)"
    return key[:6] + "****" + key[-4:]
