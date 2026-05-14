"""
LLM 客户端封装 — 双 Provider 支持
  SiliconFlow（国产：DeepSeek / KIMI 等）
  XTY         （海外：GPT / Claude / Gemini 等）

用法：
  from llm_client import get_client, get_model, chat

  # 国产模型
  client = get_client("siliconflow")
  result = chat("你好", provider="siliconflow", model="deepseek-ai/DeepSeek-V3-0324")

  # 海外模型
  result = chat("Hello", provider="xty", model="openai/gpt-4o")
"""
import os
from pathlib import Path
from openai import OpenAI

# ============================================================
# 0. 加载 .env 文件（plug and play，无需手动 export）
# ============================================================
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ============================================================
# 1. Provider 配置
# ============================================================
PROVIDERS = {
    "siliconflow": {
        "api_key_env": "SILICONFLOW_API_KEY",
        "base_url":    "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3.2",
        "available_models": [
            # --- 国产主力（科研对比常用）---
            "deepseek-ai/DeepSeek-V3.2",      # DeepSeek V3.2，国产性价比之王
            "deepseek-ai/DeepSeek-R1",         # DeepSeek R1，推理能力强
            "Pro/moonshotai/Kimi-K2.5",        # Kimi K2.5，国产旗舰
            "MiniMaxAI/MiniMax-M2.5",           # MiniMax M2.5
            "stepfun-ai/Step-3.5-Flash",       # Step 3.5 Flash
            "zai-org/GLM-5.1",                  # 智谱 GLM 5.1
            "Qwen/Qwen3.5-397B-A17B",          # 通义千问 3.5，397B 大模型
        ],
    },
    "xty": {
        "api_key_env": "XTY_API_KEY",
        "base_url":    "https://api.xty.app/v1",
        "default_model": "gpt-4o",
        "available_models": [
            # --- 海外 SOTA（科研 benchmark 常用，裸名无前缀）---
            "gpt-4o",                          # GPT-4o（主力，验证可用 ✅）
            "gpt-4o-mini",                     # GPT-4o mini（便宜快速，验证可用 ✅）
            "gpt-5",                           # GPT-5（验证可用 ✅）
            "claude-sonnet-4-6",               # Claude Sonnet 4（验证可用 ✅）
            "claude-opus-4-6",                # Claude Opus 4（验证可用 ✅）
            "gemini-2.5-pro",                  # Gemini 2.5 Pro（验证可用 ✅）
        ],
    },
}

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "siliconflow")

# ============================================================
# 2. 客户端工厂（单例）
# ============================================================
_clients = {}

def get_client(provider: str = None) -> OpenAI:
    """获取 API 客户端（自动从 .env 读取 key）"""
    provider = provider or DEFAULT_PROVIDER
    if provider in _clients:
        return _clients[provider]

    if provider not in PROVIDERS:
        raise ValueError(f"未知 provider: {provider}，可用: {list(PROVIDERS.keys())}")

    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "")
    if not api_key:
        raise ValueError(
            f"未找到 API Key：请在 ai-native-research/.env 中设置 {cfg['api_key_env']}，"
            "或 export 该环境变量后重启。"
        )

    _clients[provider] = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    return _clients[provider]

def get_model(provider: str = None) -> str:
    """获取默认模型名称"""
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    model_env_key = f"{provider.upper()}_MODEL"
    return os.environ.get(model_env_key, PROVIDERS[provider]["default_model"])

def list_models(provider: str = None):
    """列出某 provider 支持的所有模型"""
    provider = provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        return []
    return PROVIDERS[provider]["available_models"]

# ============================================================
# 3. 快捷对话函数
# ============================================================
def chat(
    prompt: str,
    system: str = "你是一个有用的AI助手。",
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    provider: str = None,
) -> str:
    """简单对话调用（自动路由到对应 provider）"""
    provider = provider or DEFAULT_PROVIDER
    client = get_client(provider)
    model = model or get_model(provider)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

# ============================================================
# 4. 测试入口
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("LLM Client 配置检测")
    print("=" * 50)

    for p in PROVIDERS:
        cfg = PROVIDERS[p]
        key_set = bool(os.environ.get(cfg["api_key_env"], ""))
        status = "✅" if key_set else "❌ 未配置"
        print(f"\n[{p}] {status}")
        if key_set:
            print(f"  模型列表：")
            for m in cfg["available_models"]:
                print(f"    - {m}")

    print("\n" + "=" * 50)
    print("尝试调用 SiliconFlow（DeepSeek V3）...")
    try:
        result = chat(
            prompt="请用一句话介绍叶面积指数(LAI)在中国城市森林遥感中的研究意义。",
            system="你是一位遥感科学专家，请简洁回答。",
            provider="siliconflow",
            model="deepseek-ai/DeepSeek-V3.2",
            max_tokens=200,
            temperature=0.7,
        )
        print(f"✅ SiliconFlow 连通成功！\n回复：{result}")
    except Exception as e:
        print(f"❌ SiliconFlow 连通失败：{e}")
        print("请确认 .env 中 SILICONFLOW_API_KEY 已正确填写。")

    print("\n尝试调用 XTY（GPT-4o）...")
    try:
        result = chat(
            prompt="Explain the significance of Leaf Area Index (LAI) in urban forest remote sensing.",
            system="You are a remote sensing expert. Keep your answer concise.",
            provider="xty",
            model="gpt-4o",
            max_tokens=200,
            temperature=0.7,
        )
        print(f"✅ XTY 连通成功！\n回复：{result}")
    except Exception as e:
        print(f"❌ XTY 连通失败：{e}")
        print("已确认可用模型：gpt-4o / gpt-5 / claude-sonnet-4-6 / claude-opus-4-6 / gemini-2.5-pro")

