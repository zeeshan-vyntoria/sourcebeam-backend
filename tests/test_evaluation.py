from evals.metrics import (
    citation_validity,
    evidence_token_groundedness,
    expected_term_coverage,
    recall_at_k,
    reciprocal_rank,
)


def test_retrieval_metrics():
    expected = {"b", "c"}
    retrieved = ["a", "b", "d", "c"]
    assert recall_at_k(expected, retrieved, 3) == 0.5
    assert reciprocal_rank(expected, retrieved) == 0.5


def test_answer_metrics():
    assert citation_validity("Supported [1], invented [4].", 2) == 0.5
    assert expected_term_coverage("Revenue was $12.4 million.", ["revenue", "$12.4 million"]) == 1
    assert evidence_token_groundedness(
        "Revenue was $12.4 million.", "The report states revenue was $12.4 million."
    ) == 1
