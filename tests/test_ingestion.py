from scripts.ingest import deterministic_records, official_parquet_url


def test_official_subset_url_and_selection_are_reproducible():
    assert official_parquet_url("hi", "validation").endswith("/validation/hinval.parquet")
    records = [{"query_id": index} for index in range(50)]
    first = list(deterministic_records(records, selection="hash", max_records=10, scan_limit=50, seed=2026))
    second = list(deterministic_records(records, selection="hash", max_records=10, scan_limit=50, seed=2026))
    assert [row["query_id"] for row in first] == [row["query_id"] for row in second]
    assert len({row["query_id"] for row in first}) == 10


def test_first_selection_remains_streaming_and_ordered():
    records = ({"query_id": index} for index in range(3))
    selected = deterministic_records(records, selection="first", max_records=2, scan_limit=10, seed=2026)
    assert [row["query_id"] for row in selected] == [0, 1, 2]
