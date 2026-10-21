from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_k: float
    evaluated: int


def recall_at_k(retrieved: list[list[int]], expected: list[set[int]]) -> RetrievalMetrics:
    if len(retrieved) != len(expected):
        raise ValueError("Retrieved and expected case counts must match.")
    scores = []
    for actual, relevant in zip(retrieved, expected, strict=True):
        if not relevant:
            continue
        scores.append(len(set(actual) & relevant) / len(relevant))
    return RetrievalMetrics(sum(scores) / len(scores) if scores else 0.0, len(scores))


def citations_are_valid(citations: list[int], retrieved_count: int) -> bool:
    return all(isinstance(number, int) and 1 <= number <= retrieved_count for number in citations)


def answer_contains_expected_facts(answer: str, expected_facts: list[str]) -> bool:
    normalized = " ".join(answer.lower().split())
    return all(" ".join(fact.lower().split()) in normalized for fact in expected_facts)
