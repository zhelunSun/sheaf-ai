"""
Sheaf LLM Client — works with any OpenAI-compatible API endpoint.

Supports OpenAI, Together, Groq, DeepSeek, SiliconFlow, and any
provider that follows the OpenAI chat completions API format.

Usage:
    from sheaf_ai.llm_client import get_client, get_model, chat
"""
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
}

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "openai")


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

    if api_key:
        return True, ""

    # Build guidance
    lines = [
        f"⚠ 未检测到 API 密钥 ({cfg['api_key_env']})",
        "",
        "快速配置（二选一）：",
        "",
        "  方法 1: 创建 .env 文件",
        f"    echo '{cfg['api_key_env']}=你的密钥' > .env",
        "",
        "  方法 2: 设置环境变量",
        f"    export {cfg['api_key_env']}=你的密钥",
        "",
        "  方法 3: 运行初始化向导",
        "    sheaf init",
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
    """Get API client (auto-reads key from .env)."""
    provider = provider or DEFAULT_PROVIDER
    if provider in _clients:
        return _clients[provider]

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}, available: {list(PROVIDERS.keys())}")

    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "")
    if not api_key:
        raise ValueError(
            f"API Key not found: set {cfg['api_key_env']} in .env "
            "or export it as environment variable."
        )

    _clients[provider] = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    return _clients[provider]


def get_model(provider: str = None) -> str:
    """Get default model name for a provider."""
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model_env_key = f"{provider.upper()}_MODEL"
    return os.environ.get(model_env_key, PROVIDERS[provider]["default_model"])


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
