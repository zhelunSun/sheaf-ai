"""
Sheaf Provider Registry — single source of truth for all LLM provider definitions.

This module is the canonical registry. Both llm_client.py and settings.py
import from here instead of maintaining duplicate provider dicts.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _load_env_file() -> None:
    """Load cwd/.env or repo .env without overriding real environment variables."""
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in env_paths:
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

# Normalized keys: api_key_env, base_url, default_model, models, name
PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "api_key_env": "SILICONFLOW_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3.2",
        "models": [
            "deepseek-ai/DeepSeek-V3.2",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen3.5-397B-A17B",
        ],
    },
    "together": {
        "name": "Together AI",
        "api_key_env": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    },
    "groq": {
        "name": "Groq",
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "custom": {
        "name": "Custom (OpenAI-compatible)",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "",
        "default_model": "",
        "models": [],
    },
}
