"""
Sheaf LLM Client — works with any OpenAI-compatible API endpoint.

Supports OpenAI, Together, Groq, DeepSeek, SiliconFlow, and any
provider that follows the OpenAI chat completions API format.

Key resolution priority:
    1. Environment variables + .env file (existing behavior)
    2. User config file (~/.sheaf/config.json)
    3. Interactive prompt (fallback, TTY only)

Usage:
    from sheaf_ai.llm_client import get_client, get_model, chat, list_models
"""
from __future__ import annotations
import os
from pathlib import Path
from openai import OpenAI

# Load .env (plug and play)
# Search: cwd/.env first, then package parent/.env (dev mode)
_env_paths = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
for _env_path in _env_paths:
    if _env_path.exists():
        with open(_env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        break

# ============================================================
# Provider config
# ============================================================

PROVIDERS = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url":    os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "default_model": "gpt-4o",
        "available_models": [
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url":    "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "available_models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "siliconflow": {
        "api_key_env": "SILICONFLOW_API_KEY",
        "base_url":    "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3.2",
        "available_models": [
            "deepseek-ai/DeepSeek-V3.2",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen3.5-397B-A17B",
        ],
    },
    "together": {
        "api_key_env": "TOGETHER_API_KEY",
        "base_url":    "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "available_models": [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ],
    },
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "base_url":    "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "available_models": [
            "llama-3.3-70b-versatile",
            "mixtral-8x7b-32768",
        ],
    },
}

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "openai")


# ============================================================
# API key resolution (env first, then config file)
# ============================================================

def _resolve_key_and_url(provider: str) -> tuple[str, str]:
    """Resolve API key and base URL with layered priority.

    Priority:
        1. Environment variable (incl .env)
        2. User config file ~/.sheaf/config.json
        3. Raise ValueError with guidance
    """
    # 1. Environment variable (existing behavior)
    if provider in PROVIDERS:
        cfg = PROVIDERS[provider]
        env_key = os.environ.get(cfg["api_key_env"], "").strip()
        env_url = os.environ.get("OPENAI_BASE_URL", cfg["base_url"])
        if env_key:
            return env_key, env_url

    # 2. User config file
    try:
        from sheaf_ai.settings import get_api_key as _cfg_get_key
        from sheaf_ai.settings import get_provider_config as _cfg_get_pc
        from sheaf_ai.settings import CONFIG_FILE

        cfg_key = _cfg_get_key(provider)
        pc = _cfg_get_pc(provider)
        if cfg_key:
            # Base URL: env > config file > provider default
            if provider in PROVIDERS:
                default_url = PROVIDERS[provider]["base_url"]
            else:
                default_url = pc.get("base_url", "") if pc else ""
            url = os.environ.get("OPENAI_BASE_URL", "")
            if not url and pc:
                url = pc.get("base_url", "")
            if not url:
                url = default_url
            return cfg_key, url
    except ImportError:
        pass

    # 3. Not found — raise with guidance
    env_name = PROVIDERS.get(provider, {}).get("api_key_env", f"{provider.upper()}_API_KEY")
    lines = [
        f"⚠ 未检测到 API 密钥 ({env_name})",
        "",
        "快速配置（推荐）：",
        "    sheaf config setup",
        "",
        "或手动设置环境变量：",
        f"    # macOS/Linux:  export {env_name}=你的密钥",
        f"    # Windows PS:   $env:{env_name}='你的密钥'",
        f"    # Windows CMD:  set {env_name}=你的密钥",
        "",
        "或创建 .env 文件：",
        f"    {env_name}=你的密钥",
        "",
        f"支持的 provider: {', '.join(PROVIDERS.keys())}",
        f"当前默认: {DEFAULT_PROVIDER} (可通过 DEFAULT_PROVIDER 环境变量切换)",
    ]
    raise ValueError("\n".join(lines))


def check_api_key(provider: str = None) -> tuple[bool, str]:
    """Check if API key is configured for a provider.

    Returns:
        (is_ok, guidance_message)
    """
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        provider = "openai"  # fallback to openai as default guidance

    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "")

    # Also check config file
    if not api_key:
        try:
            from sheaf_ai.settings import get_api_key as _cfg_get_key
            api_key = _cfg_get_key(provider) or ""
        except ImportError:
            pass

    if api_key:
        return True, ""

    # Build guidance
    lines = [
        f"⚠ 未检测到 API 密钥 ({cfg['api_key_env']})",
        "",
        "快速配置（推荐交互式向导）：",
        "    sheaf config setup",
        "",
        "或手动设置环境变量：",
        f"    # macOS/Linux:  export {cfg['api_key_env']}=你的密钥",
        f"    # Windows PS:   $env:{cfg['api_key_env']}='你的密钥'",
        f"    # Windows CMD:  set {cfg['api_key_env']}=你的密钥",
        "",
        "或创建 .env 文件：",
        f"    {cfg['api_key_env']}=你的密钥",
        "",
        f"支持的 provider: {', '.join(PROVIDERS.keys())}",
        f"当前默认: {DEFAULT_PROVIDER} (可通过 DEFAULT_PROVIDER 环境变量切换)",
    ]
    return False, "\n".join(lines)


# ============================================================
# Client factory (singleton)
# ============================================================

_clients = {}


def get_client(provider: str = None) -> OpenAI:
    """Get API client (auto-reads key from .env or user config)."""
    provider = provider or DEFAULT_PROVIDER
    if provider in _clients:
        return _clients[provider]

    if provider not in PROVIDERS:
        # Allow custom providers from config file
        try:
            from sheaf_ai.settings import get_provider_config as _cfg_get_pc
            pc = _cfg_get_pc(provider)
            if pc and pc.get("api_key"):
                api_key = pc["api_key"]
                base_url = pc.get("base_url", "")
                _clients[provider] = OpenAI(api_key=api_key, base_url=base_url)
                return _clients[provider]
        except ImportError:
            pass
        raise ValueError(
            f"Unknown provider: {provider}, available: {list(PROVIDERS.keys())}"
        )

    api_key, base_url = _resolve_key_and_url(provider)
    _clients[provider] = OpenAI(api_key=api_key, base_url=base_url)
    return _clients[provider]


def get_model(provider: str = None) -> str:
    """Get default model name for a provider."""
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model_env_key = f"{provider.upper()}_MODEL"

    # Priority: env > config file > provider default
    model = os.environ.get(model_env_key) or os.environ.get("DEFAULT_MODEL")
    if model:
        return model

    try:
        from sheaf_ai.settings import get_provider_config as _cfg_get_pc
        pc = _cfg_get_pc(provider)
        if pc and pc.get("default_model"):
            return pc["default_model"]
    except ImportError:
        pass

    return PROVIDERS[provider]["default_model"]


def list_models(provider: str = None):
    """List available models for a provider."""
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        return []
    return PROVIDERS[provider]["available_models"]


# ============================================================
# Quick chat function
# ============================================================

def chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    provider: str = None,
) -> str:
    """Simple chat call (auto-routes to the correct provider)."""
    provider = provider or DEFAULT_PROVIDER
    client = get_client(provider)
    model = model or get_model(provider)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
