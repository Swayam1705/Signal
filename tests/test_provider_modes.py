import json
from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.core.container import Container
from backend.rag.embeddings.providers import HashingEmbeddingProvider
from backend.rag.vector.qdrant_store import QdrantVectorStore


def test_hashing_provider_is_explicit_development_fallback():
    provider = HashingEmbeddingProvider(96)
    assert provider.mode == "development_fallback"
    assert provider.provider_name == "feature-hashing"
    assert provider.model_name == "signal-hashing-v1"


def test_text_and_voice_production_readiness_are_separate():
    settings = Settings(
        embedding_provider="openai", embedding_api_key="test-embedding-key",
        llm_provider="openai", llm_api_key="test-llm-key", elevenlabs_api_key=None,
    )
    assert settings.production_ready is True
    assert settings.voice_ready is False


def test_runtime_rejects_index_created_by_different_embedding_model(tmp_path: Path):
    data = tmp_path / "data"
    (data / "index").mkdir(parents=True)
    settings = Settings(data_dir=data, qdrant_path=data / "index" / "qdrant", embedding_dimension=96)
    store = QdrantVectorStore(settings.qdrant_path, settings.qdrant_collection, 96)
    store.ensure_collection()
    store.close()
    manifest = {
        "embedding_provider": "hashing", "embedding_model": "different-model",
        "embedding_dimension": 96, "dataset_source": "test", "chunk_strategy": "sentence",
    }
    settings.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="INDEX_EMBEDDING_MISMATCH"):
        Container(settings)
