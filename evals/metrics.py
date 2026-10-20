import re


def recall_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 1.0
    return len(expected & set(retrieved[:k])) / len(expected)


def reciprocal_rank(expected: set[str], retrieved: list[str]) -> float:
    for rank, source_id in enumerate(retrieved, start=1):
        if source_id in expected:
            return 1 / rank
    return 0.0


def citation_validity(answer: str, source_count: int) -> float:
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    if not citations:
        return 0.0
    return sum(1 <= value <= source_count for value in citations) / len(citations)


def expected_term_coverage(answer: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    lowered = answer.lower()
    return sum(term.lower() in lowered for term in expected_terms) / len(expected_terms)


def evidence_token_groundedness(answer: str, evidence: str) -> float:
    """Conservative lexical groundedness signal; higher means claims reuse evidence terms."""
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "was", "were", "for", "on"}
    answer_terms = {
        term for term in re.findall(r"[\w$.-]+", answer.lower()) if len(term) > 2 and term not in stop
    }
    if not answer_terms:
        return 1.0
    evidence_terms = set(re.findall(r"[\w$.-]+", evidence.lower()))
    return len(answer_terms & evidence_terms) / len(answer_terms)
