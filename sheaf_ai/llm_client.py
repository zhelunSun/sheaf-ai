"""
Sheaf LLM Client — works with any OpenAI-compatible API endpoint.

Supports OpenAI, Together, Groq, DeepSeek, SiliconFlow, and any
provider that follows the OpenAI chat completions API format.

Key resolution priority (SHEAF_API_KEY shortcut):
    1. SHEAF_API_KEY (unified env var) — auto-detects provider from key format
    2. Provider-specific env var: SILICONFLOW_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY, etc.
    3. User config file (~/.sheaf/config.json)
    4. Interactive prompt (fallback, TTY only)

Usage:
    from sheaf_ai.llm_client import get_client, get_model, chat, list_models
"""
from __future__ import annotations
import os
import time
from openai import OpenAI

from sheaf_ai.providers import PROVIDERS

# ============================================================
# Provider config (canonical source: sheaf_ai.providers)
# ============================================================

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "openai")

# ============================================================
# SHEAF_API_KEY — unified entry point
# ============================================================

# Key prefix → provider mapping for auto-detection
_KEY_PREFIX_PROVIDERS = {
    "gsk_": "groq",                 # Groq
    "sk-proj-": "openai",           # OpenAI project key
    "sk-or-": "openai",             # OpenRouter (treated as OpenAI-compatible)
    "f_": "together",               # Together AI (legacy)
    "tgp_": "together",             # Together AI
    "ds-": "deepseek",              # DeepSeek
}


def detect_provider_from_key(api_key: str) -> str | None:
    """Try to infer the provider ID from the API key prefix.

    Returns provider ID string or None if unknown.
    """
    for prefix, provider in _KEY_PREFIX_PROVIDERS.items():
        if api_key.startswith(prefix):
            return provider
    # Ambiguous: sk- prefix could be openai, deepseek, or siliconflow
    # Default to the current DEFAULT_PROVIDER
    return None


# Auto-detect default provider from SHEAF_API_KEY format if DEFAULT_PROVIDER not set
_SHEAF_API_KEY = os.environ.get("SHEAF_API_KEY", "").strip()
if _SHEAF_API_KEY and not os.environ.get("DEFAULT_PROVIDER"):
    _detected = detect_provider_from_key(_SHEAF_API_KEY)
    if _detected:
        DEFAULT_PROVIDER = _detected


# ============================================================
# API key resolution (env first, then config file)
# ============================================================

def _resolve_key_and_url(provider: str) -> tuple[str, str]:
    """Resolve API key and base URL with layered priority.

    Priority:
        1. SHEAF_API_KEY (unified env var) — universal fallback for any provider
        2. Provider-specific environment variable (e.g. SILICONFLOW_API_KEY) + .env file
        3. User config file ~/.sheaf/config.json
        4. Raise ValueError with guidance

    SHEAF_API_KEY acts as a universal API key that works with the
    current provider when no provider-specific key is set.
    """
    # 1. Provider-specific environment variable (highest)
    if provider in PROVIDERS:
        cfg = PROVIDERS[provider]
        env_key = os.environ.get(cfg["api_key_env"], "").strip()
        env_url = os.environ.get("OPENAI_BASE_URL", cfg["base_url"])
        if env_key:
            return env_key, env_url

    # 2. SHEAF_API_KEY universal entry point (fallback for any provider)
    unified_key = os.environ.get("SHEAF_API_KEY", "").strip()
    if unified_key:
        # Build base URL for the target provider
        if provider in PROVIDERS:
            url = os.environ.get("OPENAI_BASE_URL", PROVIDERS[provider]["base_url"])
        else:
            url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return unified_key, url

    # 2. User config file
    try:
        from sheaf_ai.settings import get_api_key as _cfg_get_key
        from sheaf_ai.settings import get_provider_config as _cfg_get_pc

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

    # 3. Not found — raise with guidance mentioning SHEAF_API_KEY first
    env_name = PROVIDERS.get(provider, {}).get("api_key_env", f"{provider.upper()}_API_KEY")
    lines = [
        f"⚠ 未检测到 API 密钥 ({env_name})",
        "",
        "推荐方式 — 统一环境变量（适用于所有 Provider）：",
        "    export SHEAF_API_KEY=你的密钥",
        "",
        "或快速配置（推荐交互式向导）：",
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

    Checks:
        1. SHEAF_API_KEY (unified env var)
        2. Provider-specific env var
        3. User config file

    Returns:
        (is_ok, guidance_message)
    """
    provider = provider or DEFAULT_PROVIDER

    # 1. SHEAF_API_KEY unified check
    sheaf_key = os.environ.get("SHEAF_API_KEY", "").strip()
    if sheaf_key:
        return True, ""

    # 2. Provider-specific env var
    if provider not in PROVIDERS:
        provider = "openai"  # fallback to openai as default guidance

    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "")

    # 3. Config file
    if not api_key:
        try:
            from sheaf_ai.settings import get_api_key as _cfg_get_key
            api_key = _cfg_get_key(provider) or ""
        except ImportError:
            pass

    if api_key:
        return True, ""

    # Build guidance with SHEAF_API_KEY as the preferred option
    lines = [
        f"⚠ 未检测到 API 密钥 ({cfg['api_key_env']})",
        "",
        "推荐方式 — 统一环境变量（适用于所有 Provider）：",
        "    export SHEAF_API_KEY=你的密钥",
        "",
        "快速配置（交互式向导）：",
        "    sheaf config setup",
        "",
        "或手动设置 Provider 专属环境变量：",
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


def get_client(provider: str = None, timeout: float = 30) -> OpenAI:
    """Get API client (auto-reads key from .env or user config).

    Uses httpx.Timeout (connect=5s / read=30s) to prevent indefinite hangs
    on slow or unreachable API endpoints (e.g. invalid key, network issues).
    """
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
                _clients[provider] = _build_openai_client(api_key, base_url, timeout)
                return _clients[provider]
        except ImportError:
            pass
        raise ValueError(
            f"Unknown provider: {provider}, available: {list(PROVIDERS.keys())}"
        )

    api_key, base_url = _resolve_key_and_url(provider)
    _clients[provider] = _build_openai_client(api_key, base_url, timeout)
    return _clients[provider]


def _build_openai_client(api_key: str, base_url: str, timeout: float = 30) -> OpenAI:
    """Build an OpenAI client with granular httpx timeouts.

    A bare float timeout does not reliably bound connect / SSL-read phases in
    httpx, which can cause indefinite hangs.  Explicit per-phase timeouts fix
    this (Bug #1: collect hangs with no valid API key).
    """
    import httpx
    http_timeout = httpx.Timeout(
        connect=5.0,   # fail fast on TCP/TLS connect
        read=timeout,  # bounded API response wait
        write=10.0,
        pool=5.0,
    )
    return OpenAI(
        api_key=api_key, base_url=base_url,
        timeout=http_timeout, max_retries=0,
    )


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
    return PROVIDERS[provider]["models"]


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
    max_retries: int = 3,
) -> str:
    """Simple chat call with retry on transient errors.

    Retries on rate limits (429), timeouts, and connection errors
    with exponential backoff (1s, 2s, 4s).
    """
    import openai as _openai

    provider = provider or DEFAULT_PROVIDER
    client = get_client(provider)
    model = model or get_model(provider)

    backoff = 1.0
    for attempt in range(max_retries):
        try:
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
        except (
            _openai.RateLimitError,
            _openai.APITimeoutError,
            _openai.APIConnectionError,
        ):
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff)
            backoff *= 2
