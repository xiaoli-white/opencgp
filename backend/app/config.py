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
LLM_BACKENDS = ("openai_compat",)
VECTORSTORE_BACKENDS = ("simple", "pgvector")
EXPORTER_BACKENDS = ("builtin",)


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
class Settings:
    """应用总配置。"""

    app_name: str = "AI 课程工作室"
    env: str = "development"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    vectorstore: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    exporter: ExporterConfig = field(default_factory=ExporterConfig)

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
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局唯一配置单例（首次调用时加载 ``.env``）。"""
    _load_dotenv()
    return Settings.load()
