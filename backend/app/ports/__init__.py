"""Port layer: defines all abstract interfaces.

Each port corresponds to one pluggable capability. Business code depends only on
these Protocols and never imports a concrete adapter implementation.
"""

from app.ports.conversation_repository import ConversationRepository
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.series_repository import SeriesRepository
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
    "SeriesRepository",
    "Database",
    "StorageBackend",
    "LLMProvider",
    "VectorStore",
    "Exporter",
    "DocumentParser",
    "ParsedDocument",
    "EmbeddingProvider",
]
