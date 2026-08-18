from backend.rag.chunking.strategies import (
    AdaptiveHybridChunker,
    ChunkConfig,
    FixedSemanticChunker,
    MetadataAwareChunker,
    SentenceChunker,
    SlidingWindowChunker,
)

TEXT = (
    "Photosynthesis converts light energy into chemical energy. Plants use chlorophyll to capture sunlight. "
    "Carbon dioxide and water are converted to glucose and oxygen. This process generally happens in chloroplasts. "
) * 8


def assert_contract(chunker):
    chunks = chunker.chunk(TEXT, document_id="doc_1", record_id="rec_1", source="test", metadata={"language": "en"})
    assert chunks
    assert all(chunk.chunk_id and chunk.embedding_id for chunk in chunks)
    assert all(chunk.character_count == len(chunk.text) for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)
    return chunks


def test_sentence_chunker_respects_sentences():
    chunks = assert_contract(SentenceChunker(ChunkConfig(chunk_size=30)))
    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert all(chunk.strategy == "sentence" for chunk in chunks)


def test_sliding_window_has_real_overlap():
    chunks = assert_contract(SlidingWindowChunker(ChunkConfig(chunk_size=35, overlap=8, minimum_chunk_size=5)))
    assert len(chunks) > 2
    assert chunks[0].overlap == 0
    assert all(chunk.overlap == 8 for chunk in chunks[1:])


def test_semantic_and_metadata_strategies():
    assert all(chunk.strategy == "semantic" for chunk in assert_contract(FixedSemanticChunker(ChunkConfig(chunk_size=40))))
    chunks = MetadataAwareChunker(ChunkConfig(chunk_size=40)).chunk(TEXT, document_id="d", record_id="r", source="s", metadata={"title": "Biology", "language": "en"})
    assert chunks[0].text.startswith("Biology")
    assert chunks[0].strategy == "metadata_aware"


def test_same_document_produces_distinct_real_boundaries():
    config = ChunkConfig(chunk_size=35, overlap=8, minimum_chunk_size=5, maximum_chunk_size=60)
    metadata = {"title": "Biology", "language": "en"}
    strategies = [SentenceChunker(config), SlidingWindowChunker(config), FixedSemanticChunker(config), MetadataAwareChunker(config)]
    signatures = []
    for strategy in strategies:
        chunks = strategy.chunk(TEXT, document_id="same", record_id="same", source="test", metadata=metadata)
        signatures.append(tuple((chunk.text, chunk.overlap) for chunk in chunks))
    assert len(set(signatures)) >= 3
    assert any(overlap > 0 for _, overlap in signatures[1])
    assert signatures[3][0][0].startswith("Biology")


def test_adaptive_records_selection_decision():
    short = AdaptiveHybridChunker(ChunkConfig(chunk_size=100)).chunk("One complete sentence.", document_id="d", record_id="r", source="s")
    assert short[0].strategy == "adaptive_hybrid"
    assert short[0].metadata["adaptive_selected_strategy"] == "sentence"
    structured = AdaptiveHybridChunker().chunk(TEXT, document_id="d2", record_id="r", source="s", metadata={"title": "Structured"})
    assert structured[0].metadata["adaptive_selected_strategy"] == "metadata_aware"
