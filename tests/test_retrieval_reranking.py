from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.models.schemas import Candidate, Chunk, QueryAnalysis
from backend.rag.embeddings.providers import HashingEmbeddingProvider
from backend.rag.reranking.lightweight import LightweightReranker
from backend.rag.retrieval.hybrid import HybridRetriever
from backend.rag.vector.qdrant_store import QdrantVectorStore


def make_chunk(index: int, text: str, selected: bool = False) -> Chunk:
    return Chunk(chunk_id=f"c{index}", document_id=f"d{index}", record_id=f"r{index}", source="test", strategy="sentence", chunk_index=0, token_count=len(text.split()), character_count=len(text), text=text, embedding_id=f"e{index}", metadata={"language": "en", "is_selected": selected})


@pytest.mark.asyncio
async def test_hybrid_retrieval_and_separate_reranking(tmp_path: Path):
    data = tmp_path / "data"
    (data / "index").mkdir(parents=True)
    chunks = [
        make_chunk(1, "The Moon's gravitational pull is the main cause of ocean tides.", True),
        make_chunk(2, "Photosynthesis converts light into chemical energy."),
        make_chunk(3, "Weather describes short term atmospheric conditions."),
    ]
    with (data / "index" / "chunks.jsonl").open("w") as handle:
        for item in chunks:
            handle.write(item.model_dump_json() + "\n")
    settings = Settings(data_dir=data, qdrant_path=data / "index" / "qdrant", embedding_dimension=96, top_k_candidates=3)
    embedding = HashingEmbeddingProvider(96)
    store = QdrantVectorStore(settings.qdrant_path, settings.qdrant_collection, 96)
    vectors = await embedding.embed_documents([item.text for item in chunks])
    await store.upsert(chunks, vectors)
    retriever = HybridRetriever(settings, embedding, store)
    analysis = QueryAnalysis(normalized_query="What causes ocean tides?", intent="description", language="en", safety_status="safe", retrieval_mode="balanced")
    candidates = await retriever.retrieve(analysis, top_k=3)
    assert candidates[0].chunk.chunk_id == "c1"
    assert candidates[0].semantic_score > 0
    assert candidates[0].lexical_score > 0
    reranked = await LightweightReranker().rerank(analysis.normalized_query, candidates, 2)
    assert reranked[0].chunk.chunk_id == "c1"
    assert reranked[0].rerank_score >= reranked[1].rerank_score
    store.close()


@pytest.mark.asyncio
async def test_ground_truth_selected_label_never_changes_rerank_score():
    chunk_a = make_chunk(1, "Identical evidence about ocean tides.", selected=True)
    chunk_b = make_chunk(2, "Identical evidence about ocean tides.", selected=False)
    candidates = [
        Candidate(chunk=chunk_a, semantic_score=.5, lexical_score=.5, metadata_score=.5, hybrid_score=.5),
        Candidate(chunk=chunk_b, semantic_score=.5, lexical_score=.5, metadata_score=.5, hybrid_score=.5),
    ]
    reranked = await LightweightReranker().rerank("ocean tides", candidates, 2)
    assert reranked[0].rerank_score == reranked[1].rerank_score
