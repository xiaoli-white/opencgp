"""配置加载器（单一事实来源）。

所有配置从环境变量读取，并支持 ``.env`` 文件（``.env`` 中的值不会覆盖已存在的
环境变量）。统一前缀 ``OPENCGP_``，模块用双下划线后缀区分，例如：

    OPENCGP_DATABASE_BACKEND=sqlite
    OPENCGP_DATABASE_PATH=data/opencgp.db

兼容旧前缀 ``COURSE_STUDIO_``（仅作回退，新部署请统一用 ``OPENCGP_``）。

原则：代码里不硬编码任何可配置项；切换 adapter 只改配置、不改代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ENV_PREFIX = "OPENCGP_"
LEGACY_ENV_PREFIXES = ("COURSE_STUDIO_",)

# 各模块允许的 adapter 名称（供文档与校验参考）
DATABASE_BACKENDS = ("sqlite", "postgres")
STORAGE_BACKENDS = ("local", "s3", "rustfs")
LLM_BACKENDS = ("openai_compat", "dummy")
VECTORSTORE_BACKENDS = ("simple", "postgres", "pgvector")
EXPORTER_BACKENDS = ("builtin",)
PARSER_BACKENDS = ("builtin",)
EMBEDDING_BACKENDS = ("none", "openai", "openai_compat", "hash")
RERANK_BACKENDS = (
    "none",
    "dashscope",
    "qwen",
    "llm",
    "http",
    "cohere",
    "jina",
    "siliconflow",
    "zhipu",
    "tei",
    "generic",
)
IMAGE_BACKENDS = ("none", "openai_images")
EXECUTOR_BACKENDS = ("docker", "local", "none")


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
    """读取 ``OPENCGP_<KEY>`` 环境变量，回退旧前缀，再回退默认值。"""
    value = os.environ.get(ENV_PREFIX + key)
    if value is not None:
        return value
    for prefix in LEGACY_ENV_PREFIXES:
        legacy = os.environ.get(prefix + key)
        if legacy is not None:
            return legacy
    return default


@dataclass
class DatabaseConfig:
    backend: str = "sqlite"
    path: str = "data/opencgp.db"
    dsn: str = ""
    pool_size: int = 8

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            backend=_env("DATABASE_BACKEND", "sqlite"),
            path=_env("DATABASE_PATH", "data/opencgp.db"),
            dsn=_env("DATABASE_DSN", ""),
            pool_size=int(_env("DATABASE_POOL_SIZE", "8") or 8),
        )


@dataclass
class StorageConfig:
    backend: str = "local"
    root: str = "data/storage"
    endpoint: str = ""
    region: str = "us-east-1"
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    prefix: str = ""
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            backend=_env("STORAGE_BACKEND", "local"),
            root=_env("STORAGE_ROOT", "data/storage"),
            endpoint=_env("S3_ENDPOINT", ""),
            region=_env("S3_REGION", "us-east-1") or "us-east-1",
            bucket=_env("S3_BUCKET", ""),
            access_key=_env("S3_ACCESS_KEY", ""),
            secret_key=_env("S3_SECRET_KEY", ""),
            prefix=_env("S3_PREFIX", ""),
            timeout=float(_env("S3_TIMEOUT", "10") or 10),
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
    min_score: float = 0.15
    dsn: str = ""
    pool_size: int = 8
    vector_weight: float = 0.55
    fusion: str = "rrf"
    rrf_k: int = 60
    max_per_source: int = 3
    max_vector_rows: int = 200000
    lsh_bits: int = 12

    @classmethod
    def from_env(cls) -> "VectorStoreConfig":
        return cls(
            backend=_env("VECTORSTORE_BACKEND", "simple"),
            path=_env("VECTORSTORE_PATH", "data/vectorstore"),
            min_score=float(_env("SEARCH_MIN_SCORE", "0.15") or 0.15),
            dsn=_env("VECTORSTORE_DSN", "") or _env("DATABASE_DSN", ""),
            pool_size=int(_env("VECTORSTORE_POOL_SIZE", "8") or 8),
            vector_weight=float(_env("HYBRID_VECTOR_WEIGHT", "0.55") or 0.55),
            fusion=_env("HYBRID_FUSION", "rrf"),
            rrf_k=int(_env("HYBRID_RRF_K", "60") or 60),
            max_per_source=int(_env("HYBRID_MAX_PER_SOURCE", "3") or 3),
            max_vector_rows=int(_env("HYBRID_MAX_VECTOR_ROWS", "200000") or 200000),
            lsh_bits=max(1, min(32, int(_env("HYBRID_LSH_BITS", "12") or 12))),
        )


@dataclass
class ExporterConfig:
    backend: str = "builtin"
    font_regular: str = ""
    font_bold: str = ""
    pdf_margin_mm: int = 18

    @classmethod
    def from_env(cls) -> "ExporterConfig":
        return cls(
            backend=_env("EXPORTER_BACKEND", "builtin"),
            font_regular=_env("EXPORTER_FONT_REGULAR", ""),
            font_bold=_env("EXPORTER_FONT_BOLD", ""),
            pdf_margin_mm=int(_env("EXPORTER_PDF_MARGIN_MM", "18")),
        )


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
    model: str = "text-embedding-3-small"
    dim: int = 1024
    batch: int = 32
    timeout: float = 20.0
    query_prefix: str = ""

    @property
    def dimension(self) -> int:
        return self.dim

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            backend=(_env("EMBEDDING_BACKEND", "none") or "none").strip().lower(),
            base_url=_env("EMBEDDING_BASE_URL", ""),
            api_key=_env("EMBEDDING_API_KEY", ""),
            model=_env("EMBEDDING_MODEL", "text-embedding-3-small")
            or "text-embedding-3-small",
            dim=int(
                _env("EMBEDDING_DIM", "")
                or _env("EMBEDDING_DIMENSION", "1024")
                or 1024
            ),
            batch=max(1, int(_env("EMBEDDING_BATCH", "32") or 32)),
            timeout=float(_env("EMBEDDING_TIMEOUT", "20") or 20),
            query_prefix=_env("EMBEDDING_QUERY_PREFIX", ""),
        )


@dataclass
class RerankConfig:
    backend: str = "none"
    top_n: int = 12
    weight: float = 0.5
    timeout: float = 20.0
    retries: int = 2
    batch: int = 100
    chars: int = 2000
    normalize: str = "auto"
    raw_scores: bool = False
    base_url: str = ""
    model: str = ""
    api_key: str = ""

    @classmethod
    def from_env(cls) -> "RerankConfig":
        return cls(
            backend=(_env("RERANK_BACKEND", "none") or "none").strip().lower(),
            top_n=max(1, int(_env("RERANK_TOP_N", "12") or 12)),
            weight=float(_env("RERANK_WEIGHT", "0.5") or 0.5),
            timeout=float(_env("RERANK_TIMEOUT", "20") or 20),
            retries=max(0, int(_env("RERANK_RETRIES", "2") or 2)),
            batch=max(1, int(_env("RERANK_BATCH", "100") or 100)),
            chars=max(80, int(_env("RERANK_CHARS", "2000") or 2000)),
            normalize=(_env("RERANK_NORMALIZE", "auto") or "auto").strip().lower(),
            raw_scores=(_env("RERANK_RAW_SCORES", "false") or "false").strip().lower()
            in ("1", "true", "yes", "on"),
            base_url=_env("RERANK_BASE_URL", ""),
            model=_env("RERANK_MODEL", ""),
            api_key=_env("RERANK_API_KEY", ""),
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
    top_k: int = 8
    evidence_char_limit: int = 600
    max_evidence: int = 8
    default_mode: str = "strict"

    @classmethod
    def from_env(cls) -> "GenerationConfig":
        return cls(
            top_k=int(_env("GENERATION_TOP_K", "8") or 8),
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
    require_approval: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        return cls(
            mode=_env("AUTH_MODE", "disabled"),
            secret=_env("AUTH_SECRET", ""),
            token_ttl_hours=int(_env("AUTH_TOKEN_TTL_HOURS", "168") or 168),
            require_approval=_env("REQUIRE_APPROVAL", "true").strip().lower()
            not in ("0", "false", "no", "off"),
        )


@dataclass
class WebSearchConfig:
    backend: str = "none"
    url: str = ""
    api_key: str = ""
    result_path: str = "results"
    method: str = "POST"
    timeout: float = 10.0
    fetch_enabled: bool = True
    fetch_top: int = 2
    fetch_chars: int = 4000
    fetch_timeout: float = 8.0

    @classmethod
    def from_env(cls) -> "WebSearchConfig":
        return cls(
            backend=_env("WEBSEARCH_BACKEND", "none"),
            url=_env("WEBSEARCH_URL", ""),
            api_key=_env("WEBSEARCH_API_KEY", ""),
            result_path=_env("WEBSEARCH_RESULT_PATH", "results") or "results",
            method=_env("WEBSEARCH_METHOD", "POST") or "POST",
            timeout=float(_env("WEBSEARCH_TIMEOUT", "10") or 10),
            fetch_enabled=(_env("WEBSEARCH_FETCH_ENABLED", "true") or "true")
            .strip()
            .lower()
            not in ("0", "false", "no", "off"),
            fetch_top=int(_env("WEBSEARCH_FETCH_TOP", "2") or 2),
            fetch_chars=int(_env("WEBSEARCH_FETCH_CHARS", "4000") or 4000),
            fetch_timeout=float(_env("WEBSEARCH_FETCH_TIMEOUT", "8") or 8),
        )


@dataclass
class NotifyConfig:
    backend: str = "none"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    smtp_timeout: float = 10.0
    admin_email: str = ""

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        return cls(
            backend=(_env("NOTIFY_BACKEND", "none") or "none").strip().lower(),
            smtp_host=_env("SMTP_HOST", ""),
            smtp_port=int(_env("SMTP_PORT", "587") or 587),
            smtp_user=_env("SMTP_USER", ""),
            smtp_password=_env("SMTP_PASSWORD", ""),
            smtp_from=_env("SMTP_FROM", ""),
            smtp_tls=(_env("SMTP_TLS", "true") or "true").strip().lower() not in ("0", "false", "no"),
            smtp_timeout=float(_env("SMTP_TIMEOUT", "10") or 10),
            admin_email=_env("NOTIFY_ADMIN_EMAIL", ""),
        )


@dataclass
class ImageConfig:
    backend: str = "none"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-image-1"
    api_key: str = ""
    max_bytes: int = 8388608
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "ImageConfig":
        return cls(
            backend=_env("IMAGE_BACKEND", "none") or "none",
            base_url=_env("IMAGE_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            model=_env("IMAGE_MODEL", "gpt-image-1") or "gpt-image-1",
            api_key=_env("IMAGE_API_KEY", ""),
            max_bytes=int(_env("IMAGE_MAX_BYTES", "8388608") or 8388608),
            timeout=float(_env("IMAGE_TIMEOUT", "60") or 60),
        )


@dataclass
class LockConfig:
    ttl_seconds: int = 120

    @classmethod
    def from_env(cls) -> "LockConfig":
        return cls(ttl_seconds=int(_env("LOCK_TTL_SECONDS", "120") or 120))


@dataclass
class JobsConfig:
    queue_backend: str = "local"
    redis_url: str = ""
    concurrency: int = 2
    sse_interval: float = 0.6
    sse_max_seconds: float = 600.0
    sse_ping_seconds: float = 15.0
    max_attempts: int = 3
    brpop_timeout: int = 2

    @classmethod
    def from_env(cls) -> "JobsConfig":
        return cls(
            queue_backend=_env("QUEUE_BACKEND", "local") or "local",
            redis_url=_env("REDIS_URL", ""),
            concurrency=max(0, int(_env("JOB_CONCURRENCY", "2") or 2)),
            sse_interval=max(0.1, float(_env("JOB_SSE_INTERVAL", "0.6") or 0.6)),
            sse_max_seconds=max(10.0, float(_env("JOB_SSE_MAX_SECONDS", "600") or 600)),
            sse_ping_seconds=max(1.0, float(_env("JOB_SSE_PING_SECONDS", "15") or 15)),
            max_attempts=max(1, int(_env("JOB_MAX_ATTEMPTS", "3") or 3)),
            brpop_timeout=max(1, int(_env("JOB_BRPOP_TIMEOUT", "2") or 2)),
        )


@dataclass
class ExecConfig:
    backend: str = "docker"
    timeout: int = 10
    max_bytes: int = 65536
    images: dict[str, str] = field(
        default_factory=lambda: {
            "python": "python:3.12-slim",
            "node": "node:20-slim",
            "bash": "python:3.12-slim",
        }
    )

    @classmethod
    def from_env(cls) -> "ExecConfig":
        default = cls()
        raw_images = _env("EXEC_IMAGES", "")
        images = dict(default.images)
        for item in raw_images.split(","):
            entry = item.strip()
            if not entry or ":" not in entry:
                continue
            lang, _, image = entry.partition(":")
            if lang.strip() and image.strip():
                images[lang.strip().lower()] = image.strip()
        return cls(
            backend=(_env("EXECUTOR_BACKEND", "docker") or "docker").strip().lower(),
            timeout=max(1, int(_env("EXEC_TIMEOUT", "10") or 10)),
            max_bytes=max(1024, int(_env("EXEC_MAX_BYTES", "65536") or 65536)),
            images=images,
        )


@dataclass
class Settings:
    """应用总配置。"""

    app_name: str = "OpenCGP"
    env: str = "development"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    vectorstore: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    exporter: ExporterConfig = field(default_factory=ExporterConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    blueprint: BlueprintConfig = field(default_factory=BlueprintConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    locks: LockConfig = field(default_factory=LockConfig)
    websearch: WebSearchConfig = field(default_factory=WebSearchConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    jobs: JobsConfig = field(default_factory=JobsConfig)
    exec: ExecConfig = field(default_factory=ExecConfig)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            app_name=_env("APP_NAME", "OpenCGP"),
            env=_env("ENV", "development"),
            database=DatabaseConfig.from_env(),
            storage=StorageConfig.from_env(),
            llm=LLMConfig.from_env(),
            vectorstore=VectorStoreConfig.from_env(),
            exporter=ExporterConfig.from_env(),
            parser=ParserConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            rerank=RerankConfig.from_env(),
            ingest=IngestConfig.from_env(),
            generation=GenerationConfig.from_env(),
            blueprint=BlueprintConfig.from_env(),
            conversation=ConversationConfig.from_env(),
            auth=AuthConfig.from_env(),
            locks=LockConfig.from_env(),
            websearch=WebSearchConfig.from_env(),
            image=ImageConfig.from_env(),
            notify=NotifyConfig.from_env(),
            jobs=JobsConfig.from_env(),
            exec=ExecConfig.from_env(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局唯一配置单例（首次调用时加载 ``.env``）。"""
    _load_dotenv()
    return Settings.load()
