from scripts.benchmark import percentile


def test_percentiles_are_calculated_not_hardcoded():
    values = [10, 20, 30, 40, 50]
    assert percentile(values, 50) == 30
    assert percentile(values, 70) == 38
    assert percentile(values, 100) == 50
    assert percentile([7], 50) == 7
    assert percentile([], 70) == 0
