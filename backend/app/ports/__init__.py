"""端口（Port）层：定义全部抽象接口。

每个端口对应一类可插拔能力，业务代码只依赖这些 Protocol，
不 import 任何具体 adapter 实现。
"""

from app.ports.conversation_repository import ConversationRepository
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.course_repository import CourseRepository
from app.ports.database import Database
from app.ports.embedding import EmbeddingProvider
from app.ports.exporter import Exporter
from app.ports.llm import LLMProvider
from app.ports.parser import DocumentParser, ParsedDocument
from app.ports.storage import StorageBackend
from app.ports.vectorstore import VectorStore

__all__ = [
    "BlueprintRepository",
    "ConversationRepository",
    "CourseRepository",
    "Database",
    "StorageBackend",
    "LLMProvider",
    "VectorStore",
    "Exporter",
    "DocumentParser",
    "ParsedDocument",
    "EmbeddingProvider",
]
