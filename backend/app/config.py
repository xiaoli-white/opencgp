"""配置加载器（单一事实来源）。

所有配置从环境变量读取，并支持 ``.env`` 文件（``.env`` 中的值不会覆盖已存在的
环境变量）。统一前缀 ``COURSE_STUDIO_``，模块用双下划线后缀区分，例如：

    COURSE_STUDIO_DATABASE_BACKEND=sqlite
    COURSE_STUDIO_DATABASE_PATH=data/course_studio.db

原则：代码里不硬编码任何可配置项；切换 adapter 只改配置、不改代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ENV_PREFIX = "COURSE_STUDIO_"

# 各模块允许的 adapter 名称（供文档与校验参考）
DATABASE_BACKENDS = ("sqlite", "postgres")
STORAGE_BACKENDS = ("local", "s3", "rustfs")
LLM_BACKENDS = ("openai_compat", "dummy")
VECTORSTORE_BACKENDS = ("simple", "pgvector")
EXPORTER_BACKENDS = ("builtin",)
PARSER_BACKENDS = ("builtin",)
EMBEDDING_BACKENDS = ("none", "openai_compat")


def _find_dotenv() -> Path | None:
    """向上查找 ``.env``（当前目录 → backend/ → 项目根）。"""
    cwd = Path.cwd()
    for base in (cwd, cwd / "backend", cwd.parent):
        candidate = base / ".env"
        if candidate.is_file():
            return candidate
    return None


def _load_dotenv(path: Path | None = None) -> None:
    """解析 ``.env`` 并注入 ``os.environ``（不覆盖已存在的环境变量）。"""
    path = path or _find_dotenv()
    if path is None or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = os.path.expandvars(value)


def _env(key: str, default: str = "") -> str:
    """读取 ``COURSE_STUDIO_<KEY>`` 环境变量，缺失时返回默认值。"""
    return os.environ.get(ENV_PREFIX + key, default)


@dataclass
class DatabaseConfig:
    backend: str = "sqlite"
    path: str = "data/course_studio.db"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            backend=_env("DATABASE_BACKEND", "sqlite"),
            path=_env("DATABASE_PATH", "data/course_studio.db"),
        )


@dataclass
class StorageConfig:
    backend: str = "local"
    root: str = "data/storage"

    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            backend=_env("STORAGE_BACKEND", "local"),
            root=_env("STORAGE_ROOT", "data/storage"),
        )


@dataclass
class LLMConfig:
    backend: str = "openai_compat"
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            backend=_env("LLM_BACKEND", "openai_compat"),
            base_url=_env("LLM_BASE_URL", ""),
            api_key=_env("LLM_API_KEY", ""),
            model=_env("LLM_MODEL", ""),
        )


@dataclass
class VectorStoreConfig:
    backend: str = "simple"
    path: str = "data/vectorstore"

    @classmethod
    def from_env(cls) -> "VectorStoreConfig":
        return cls(
            backend=_env("VECTORSTORE_BACKEND", "simple"),
            path=_env("VECTORSTORE_PATH", "data/vectorstore"),
        )


@dataclass
class ExporterConfig:
    backend: str = "builtin"

    @classmethod
    def from_env(cls) -> "ExporterConfig":
        return cls(backend=_env("EXPORTER_BACKEND", "builtin"))


@dataclass
class ParserConfig:
    backend: str = "builtin"

    @classmethod
    def from_env(cls) -> "ParserConfig":
        return cls(backend=_env("PARSER_BACKEND", "builtin"))


@dataclass
class EmbeddingConfig:
    backend: str = "none"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    dimension: int = 1024

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            backend=_env("EMBEDDING_BACKEND", "none"),
            base_url=_env("EMBEDDING_BASE_URL", ""),
            api_key=_env("EMBEDDING_API_KEY", ""),
            model=_env("EMBEDDING_MODEL", ""),
            dimension=int(_env("EMBEDDING_DIMENSION", "1024") or 1024),
        )


@dataclass
class IngestConfig:
    chunk_size: int = 800
    chunk_overlap: int = 120
    max_file_mb: int = 20

    @classmethod
    def from_env(cls) -> "IngestConfig":
        return cls(
            chunk_size=int(_env("INGEST_CHUNK_SIZE", "800") or 800),
            chunk_overlap=int(_env("INGEST_CHUNK_OVERLAP", "120") or 120),
            max_file_mb=int(_env("INGEST_MAX_FILE_MB", "20") or 20),
        )


@dataclass
class GenerationConfig:
    top_k: int = 5
    evidence_char_limit: int = 600
    max_evidence: int = 8
    default_mode: str = "strict"

    @classmethod
    def from_env(cls) -> "GenerationConfig":
        return cls(
            top_k=int(_env("GENERATION_TOP_K", "5") or 5),
            evidence_char_limit=int(_env("GENERATION_EVIDENCE_CHAR_LIMIT", "600") or 600),
            max_evidence=int(_env("GENERATION_MAX_EVIDENCE", "8") or 8),
            default_mode=_env("GENERATION_DEFAULT_MODE", "strict"),
        )


@dataclass
class BlueprintConfig:
    top_k: int = 6
    default_mode: str = ""

    @classmethod
    def from_env(cls) -> "BlueprintConfig":
        return cls(
            top_k=int(_env("BLUEPRINT_TOP_K", "6") or 6),
            default_mode=_env("BLUEPRINT_DEFAULT_MODE", ""),
        )


@dataclass
class ConversationConfig:
    history_limit: int = 20
    history_char_limit: int = 400
    content_char_limit: int = 6000
    evidence_char_limit: int = 600

    @classmethod
    def from_env(cls) -> "ConversationConfig":
        return cls(
            history_limit=int(_env("CONVERSATION_HISTORY_LIMIT", "20") or 20),
            history_char_limit=int(_env("CONVERSATION_HISTORY_CHAR_LIMIT", "400") or 400),
            content_char_limit=int(_env("CONVERSATION_CONTENT_CHAR_LIMIT", "6000") or 6000),
            evidence_char_limit=int(
                _env("CONVERSATION_EVIDENCE_CHAR_LIMIT", "600") or 600
            ),
        )


@dataclass
class AuthConfig:
    mode: str = "disabled"
    secret: str = ""
    token_ttl_hours: int = 168

    @classmethod
    def from_env(cls) -> "AuthConfig":
        return cls(
            mode=_env("AUTH_MODE", "disabled"),
            secret=_env("AUTH_SECRET", ""),
            token_ttl_hours=int(_env("AUTH_TOKEN_TTL_HOURS", "168") or 168),
        )


@dataclass
class WebSearchConfig:
    backend: str = "none"
    url: str = ""
    api_key: str = ""
    result_path: str = "results"
    method: str = "POST"
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "WebSearchConfig":
        return cls(
            backend=_env("WEBSEARCH_BACKEND", "none"),
            url=_env("WEBSEARCH_URL", ""),
            api_key=_env("WEBSEARCH_API_KEY", ""),
            result_path=_env("WEBSEARCH_RESULT_PATH", "results") or "results",
            method=_env("WEBSEARCH_METHOD", "POST") or "POST",
            timeout=float(_env("WEBSEARCH_TIMEOUT", "10") or 10),
        )


@dataclass
class LockConfig:
    ttl_seconds: int = 120

    @classmethod
    def from_env(cls) -> "LockConfig":
        return cls(ttl_seconds=int(_env("LOCK_TTL_SECONDS", "120") or 120))


@dataclass
class Settings:
    """应用总配置。"""

    app_name: str = "AI 课程工作室"
    env: str = "development"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    vectorstore: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    exporter: ExporterConfig = field(default_factory=ExporterConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    blueprint: BlueprintConfig = field(default_factory=BlueprintConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    locks: LockConfig = field(default_factory=LockConfig)
    websearch: WebSearchConfig = field(default_factory=WebSearchConfig)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            app_name=_env("APP_NAME", "AI 课程工作室"),
            env=_env("ENV", "development"),
            database=DatabaseConfig.from_env(),
            storage=StorageConfig.from_env(),
            llm=LLMConfig.from_env(),
            vectorstore=VectorStoreConfig.from_env(),
            exporter=ExporterConfig.from_env(),
            parser=ParserConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            ingest=IngestConfig.from_env(),
            generation=GenerationConfig.from_env(),
            blueprint=BlueprintConfig.from_env(),
            conversation=ConversationConfig.from_env(),
            auth=AuthConfig.from_env(),
            locks=LockConfig.from_env(),
            websearch=WebSearchConfig.from_env(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局唯一配置单例（首次调用时加载 ``.env``）。"""
    _load_dotenv()
    return Settings.load()
