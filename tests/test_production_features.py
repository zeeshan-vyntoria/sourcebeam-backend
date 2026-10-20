from dataclasses import dataclass

import pytest

from app.services.rag import _keyword_score, _rrf_merge
from app.services.storage import ObjectStorage


@dataclass
class Candidate:
    id: str


def test_keyword_score_rewards_exact_identifiers():
    assert _keyword_score("SEC-104 access", "SEC-104 requires quarterly access reviews") == 1
    assert _keyword_score("SEC-104 access", "General security guidance") == 0


def test_reciprocal_rank_fusion_combines_retrievers():
    alpha = (Candidate("alpha"), "doc.pdf", 0.8)
    beta = (Candidate("beta"), "doc.pdf", 0.7)
    merged = _rrf_merge([[alpha, beta], [beta, alpha]], 2)
    assert {item[0].id for item in merged} == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_local_object_storage_round_trip(tmp_path):
    storage = ObjectStorage()
    storage.backend = "local"
    storage.root = tmp_path.resolve()
    await storage.put("users/1/documents/test.pdf", b"%PDF-test", "application/pdf")
    assert await storage.get("users/1/documents/test.pdf") == b"%PDF-test"
    await storage.delete("users/1/documents/test.pdf")
    with pytest.raises(Exception, match="unavailable"):
        await storage.get("users/1/documents/test.pdf")
