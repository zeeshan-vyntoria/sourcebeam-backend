"""Run a repeatable live Gemini retrieval and grounded-answer evaluation."""

import asyncio
import json
from pathlib import Path
import statistics

from app.services.ai import generate_chat_response
from app.services.rag import _cosine_similarity, embed_texts, grounded_system_instruction
from evals.metrics import (
    citation_validity,
    evidence_token_groundedness,
    expected_term_coverage,
    recall_at_k,
    reciprocal_rank,
)


async def evaluate() -> dict:
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        sources = case["sources"]
        vectors = await embed_texts([source["text"] for source in sources], "RETRIEVAL_DOCUMENT")
        query_vector = (await embed_texts([case["question"]], "RETRIEVAL_QUERY"))[0]
        ranked = sorted(
            zip(sources, vectors, strict=True),
            key=lambda item: _cosine_similarity(item[1], query_vector),
            reverse=True,
        )
        retrieved = [item[0] for item in ranked[:3]]
        context = "\n\n".join(
            f"[Source {index}: evaluation.pdf, page {source['page']}]\n{source['text']}"
            for index, source in enumerate(retrieved, start=1)
        )
        answer, model = await generate_chat_response(
            [{"role": "user", "content": case["question"]}],
            grounded_system_instruction(context),
        )
        expected = set(case["expected_sources"])
        retrieved_ids = [source["id"] for source in retrieved]
        results.append(
            {
                "id": case["id"],
                "model": model,
                "retrieved": retrieved_ids,
                "recall_at_3": recall_at_k(expected, retrieved_ids, 3),
                "reciprocal_rank": reciprocal_rank(expected, retrieved_ids),
                "citation_validity": citation_validity(answer, len(retrieved)),
                "groundedness": evidence_token_groundedness(answer, context),
                "answer_term_coverage": expected_term_coverage(
                    answer, case["expected_answer_terms"]
                ),
                "answer": answer,
            }
        )
    metric_names = [
        "recall_at_3", "reciprocal_rank", "citation_validity", "groundedness",
        "answer_term_coverage"
    ]
    return {
        "summary": {
            name: round(statistics.mean(result[name] for result in results), 4)
            for name in metric_names
        },
        "cases": results,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(evaluate()), indent=2))
