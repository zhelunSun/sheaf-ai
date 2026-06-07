"""Synonym configuration management for Sheaf search.

Loads synonyms from:
  1. User config: DATA_DIR/synonyms.json (highest priority)
  2. Built-in defaults: hard-coded AI/ML/RS synonym groups

This allows users to customize synonym expansion by editing
the synonyms.json file in their data directory.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in default synonym groups — used when no user config exists.
# Each tuple contains equivalent terms for cross-lingual/cross-domain expansion.
_BUILTIN_SYNONYM_GROUPS: list[tuple[str, ...]] = [
    # AI / ML
    ("ai", "artificial intelligence", "人工智能", "AI"),
    ("machine learning", "ml", "机器学习", "ML"),
    ("deep learning", "dl", "深度学习", "DL"),
    ("neural network", "神经网络", "nn"),
    ("llm", "large language model", "大语言模型", "大模型", "LLM"),
    ("nlp", "natural language processing", "自然语言处理", "NLP"),
    ("reinforcement learning", "rl", "强化学习"),
    ("transformer", "注意力机制", "attention"),
    ("gpt", "generative pretrained transformer"),
    ("agent", "智能体", "ai agent", "AI智能体"),
    ("multimodal", "多模态"),
    ("computer vision", "cv", "计算机视觉"),
    ("generative ai", "生成式AI", "genai", "aigc", "生成式人工智能"),
    ("diffusion model", "扩散模型"),
    ("rag", "retrieval augmented generation", "检索增强生成"),
    ("fine-tuning", "微调", "finetune"),
    ("prompt engineering", "提示工程", "prompt"),
    ("embedding", "向量表示", "向量嵌入"),
    ("foundation model", "基础模型", "底座模型"),
    ("knowledge graph", "知识图谱", "kg"),
    ("moe", "mixture of experts", "混合专家"),
    ("cot", "chain of thought", "思维链"),
    ("rlhf", "reinforcement learning from human feedback", "人类反馈强化学习"),
    # General tech
    ("api", "应用程序接口"),
    ("open source", "开源"),
    ("benchmark", "基准测试", "评测"),
    ("dataset", "数据集"),
    ("model", "模型"),
    ("training", "训练"),
    ("inference", "推理", "推断"),
    ("deployment", "部署"),
    ("scaling", "扩展", "缩放"),
    ("optimization", "优化"),
    ("architecture", "架构"),
    ("framework", "框架"),
    ("pipeline", "管道", "流水线"),
    # Remote sensing
    ("remote sensing", "遥感", "卫星遥感"),
    ("earth observation", "地球观测", "eo"),
    ("satellite", "卫星"),
    ("spatial", "空间"),
    ("geospatial", "地理空间"),
    ("gis", "geographic information system", "地理信息系统"),
]


def _load_user_synonyms(path: Path) -> list[list[str]] | None:
    """Load user-defined synonyms from JSON file.

    Expected format: list of string arrays, e.g.:
    [
      ["ai", "人工智能", "artificial intelligence"],
      ["deep learning", "深度学习", "dl"]
    ]
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("synonyms.json: expected list, got %s", type(data).__name__)
            return None
        # Validate each group is a list of strings
        validated: list[list[str]] = []
        for i, group in enumerate(data):
            if isinstance(group, list) and all(isinstance(t, str) for t in group):
                validated.append(group)
            else:
                logger.warning("synonyms.json: group %d invalid, skipping", i)
        return validated if validated else None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("synonyms.json: failed to load: %s", e)
        return None


def load_synonym_groups(data_dir: Path | None = None) -> list[tuple[str, ...]]:
    """Load synonym groups, merging user config with built-in defaults.

    If user config exists, it *replaces* the built-in defaults entirely.
    This gives users full control (they can include the built-in groups
    they want in their config file).

    Args:
        data_dir: Path to data directory. If None, uses config.DATA_DIR.

    Returns:
        List of synonym tuples.
    """
    if data_dir is None:
        from sheaf_ai.config import DATA_DIR
        data_dir = DATA_DIR

    user_file = data_dir / "synonyms.json"
    user_groups = _load_user_synonyms(user_file)

    if user_groups is not None:
        logger.info("Loaded %d synonym groups from %s", len(user_groups), user_file)
        return [tuple(g) for g in user_groups]

    return list(_BUILTIN_SYNONYM_GROUPS)


def get_synonyms_config_path(data_dir: Path | None = None) -> Path:
    """Get the path where user synonyms config should be saved."""
    if data_dir is None:
        from sheaf_ai.config import DATA_DIR
        data_dir = DATA_DIR
    return data_dir / "synonyms.json"


def init_synonyms_config(data_dir: Path | None = None) -> Path:
    """Create a default synonyms.json from built-in groups.

    Returns the path to the created file.
    """
    path = get_synonyms_config_path(data_dir)
    if path.exists():
        return path

    data = [list(g) for g in _BUILTIN_SYNONYM_GROUPS]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Created default synonyms config at %s", path)
    return path


def build_synonym_lookup(
    groups: list[tuple[str, ...]],
) -> dict[str, set[str]]:
    """Build lookup dict from synonym groups.

    Args:
        groups: List of synonym tuples.

    Returns:
        Dict mapping normalized_term -> set of all synonyms (including self).
    """
    lookup: dict[str, set[str]] = {}
    for group in groups:
        normalized = {t.lower().strip() for t in group}
        for term in normalized:
            if term not in lookup:
                lookup[term] = set()
            lookup[term].update(normalized)
    return lookup
