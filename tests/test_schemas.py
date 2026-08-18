import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.models.schemas import GeneratedAnswer, QueryRequest


def test_query_rejects_blank_and_oversized():
    with pytest.raises(ValidationError):
        QueryRequest(query="   ")
    with pytest.raises(ValidationError):
        QueryRequest(query="x" * 1001)


def test_malformed_model_output_is_rejected():
    with pytest.raises(ValidationError):
        GeneratedAnswer.model_validate({"answer": "x", "confidence": 2, "grounded": True, "citations": [], "refusal": False, "unexpected": "blocked"})


def test_invalid_retrieval_and_chunk_configuration_fails_startup():
    with pytest.raises(ValidationError, match="weights must sum to 1"):
        Settings(semantic_weight=.9, lexical_weight=.9, metadata_weight=.1)
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        Settings(chunk_size=10, chunk_overlap=10, min_chunk_size=1, max_chunk_size=20)


def test_structured_output_contract():
    value = GeneratedAnswer.model_validate({"answer": "No signal", "confidence": 0, "grounded": False, "citations": [], "warnings": [], "refusal": True, "refusal_reason": "LOW_EVIDENCE"})
    assert value.refusal_reason == "LOW_EVIDENCE"
