from __future__ import annotations

DEFAULT_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "lean": ("lean", "lean4", "lean 4", "leanprover", "精益"),
    "定理证明": (
        "定理证明",
        "形式化证明",
        "形式化验证",
        "自动定理证明",
        "theorem proving",
        "formal proof",
        "formal verification",
    ),
    "形式化证明": (
        "形式化证明",
        "定理证明",
        "形式化验证",
        "formal proof",
        "theorem proving",
        "formal verification",
    ),
    "依赖类型": ("依赖类型", "依值类型", "dependent type", "dependent types"),
    "tactic": ("tactic", "tactics", "策略", "战术"),
    "向量数据库": (
        "向量数据库",
        "向量检索",
        "vector database",
        "vector search",
        "vector store",
    ),
    "索引调优": (
        "索引调优",
        "索引优化",
        "index tuning",
        "index optimization",
        "hnsw",
        "ivf",
    ),
    "量化压缩": ("量化压缩", "量化", "quantization", "product quantization", "pq"),
}
