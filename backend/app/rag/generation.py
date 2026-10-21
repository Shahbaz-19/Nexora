import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.rag.llm import generate_llm_response
from app.rag.prompts import (
    SYSTEM_PROMPT,
    build_rag_prompt,
)
from app.rag.retrieval import (
    RetrievalResult,
    retrieve_chunks,
)
from app.rag.timing import RAGTimings


DEFAULT_GENERATION_TOP_K = 5
NO_RELEVANT_INFORMATION_MESSAGE = (
    "I couldn't find relevant information in your uploaded documents."
)
SUPPLEMENTAL_DISCLAIMER = (
    "*AI-generated supplemental guidance — not sourced from your uploaded documents.*"
)
SOURCE_REFERENCE_PATTERN = re.compile(
    r"\s*(?:\[\s*)?Source\s+\d+(?:\s*\])?\s*",
    flags=re.IGNORECASE,
)
INLINE_SOURCE_MARKER_PATTERN = re.compile(
    r"[ \t]*(?:\[\s*Source\s+\d+\s*\])+",
    flags=re.IGNORECASE,
)


@dataclass
class GeneratedAnswer:
    answer: str
    sources: list[RetrievalResult]


@dataclass
class StructuredRAGResponse:
    grounded_answer: str
    cited_source_numbers: list[int]
    additional_guidance: str | None = None


def source_numbers_from_text(text: str) -> list[int]:
    matches = re.findall(
        r"(?:\[)?Source\s+(\d+)(?:\])?",
        text,
        flags=re.IGNORECASE,
    )
    return [int(match) for match in matches]


def validated_source_numbers(
    source_numbers: list[int],
    retrieval_results: list[RetrievalResult],
) -> list[int]:
    valid_numbers: list[int] = []
    for source_number in source_numbers:
        if (
            isinstance(source_number, int)
            and 1 <= source_number <= len(retrieval_results)
            and source_number not in valid_numbers
        ):
            valid_numbers.append(source_number)
    return valid_numbers


def sources_from_numbers(
    source_numbers: list[int],
    retrieval_results: list[RetrievalResult],
) -> list[RetrievalResult]:
    return [
        retrieval_results[source_number - 1]
        for source_number in validated_source_numbers(source_numbers, retrieval_results)
    ]


def extract_cited_sources(
    answer: str,
    retrieval_results: list[RetrievalResult],
) -> list[RetrievalResult]:
    """
    Preserve the old text-citation helper for callers and tests that validate
    trusted source mapping. Structured RAG uses the same validation rules.
    """

    return sources_from_numbers(
        source_numbers_from_text(answer),
        retrieval_results,
    )


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        fenced = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if fenced:
            value = json.loads(fenced.group(1))
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("The model did not return a JSON object.") from None
            value = json.loads(text[start:end + 1])

    if not isinstance(value, dict):
        raise ValueError("The model returned JSON, but not an object.")
    return value


def _normalize_source_numbers(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []

    numbers: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            numbers.append(item)
            continue
        if isinstance(item, str) and item.strip().isdigit():
            numbers.append(int(item.strip()))
    return numbers


def sanitize_supplemental_guidance(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    guidance = SOURCE_REFERENCE_PATTERN.sub(" ", value)
    guidance = re.sub(r"[ \t]+", " ", guidance)
    guidance = re.sub(r"\n{3,}", "\n\n", guidance)
    guidance = guidance.strip()
    return guidance or None


def remove_inline_source_markers(text: str) -> str:
    text = INLINE_SOURCE_MARKER_PATTERN.sub("", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_structured_rag_response(raw_response: str) -> StructuredRAGResponse:
    payload = _extract_json_object(raw_response)

    grounded_answer = payload.get("grounded_answer")
    if not isinstance(grounded_answer, str) or not grounded_answer.strip():
        raise ValueError("Structured RAG response must include grounded_answer.")

    return StructuredRAGResponse(
        grounded_answer=grounded_answer.strip(),
        cited_source_numbers=_normalize_source_numbers(
            payload.get("cited_source_numbers")
        ),
        additional_guidance=sanitize_supplemental_guidance(
            payload.get("additional_guidance")
        ),
    )


def render_structured_answer(response: StructuredRAGResponse) -> str:
    grounded_answer = remove_inline_source_markers(response.grounded_answer)

    if not response.additional_guidance:
        return grounded_answer

    return (
        f"{grounded_answer}\n\n"
        f"### Additional guidance\n\n"
        f"{response.additional_guidance}\n\n"
        f"{SUPPLEMENTAL_DISCLAIMER}"
    )


def _is_no_information_answer(answer: str) -> bool:
    normalized = re.sub(r"\s+", " ", answer.strip().lower())
    return (
        "available documents do not contain enough information" in normalized
        or "couldn't find relevant information" in normalized
        or "could not find relevant information" in normalized
    )


def generate_rag_answer(
    db: Session,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_GENERATION_TOP_K,
    retrieval_query: str | None = None,
    conversation_history: str | None = None,
    timings: RAGTimings | None = None,
) -> GeneratedAnswer:

    query = query.strip()

    if not query:
        raise ValueError(
            "Query cannot be empty."
        )

    results = retrieve_chunks(
        db=db,
        user_id=user_id,
        query=(retrieval_query or query),
        top_k=top_k,
        timings=timings,
    )

    if not results:
        return GeneratedAnswer(
            answer=NO_RELEVANT_INFORMATION_MESSAGE,
            sources=[],
        )

    user_prompt = build_rag_prompt(
        query=query,
        results=results,
        conversation_history=conversation_history,
    )

    if timings:
        with timings.measure("generation"):
            raw_answer = generate_llm_response(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0,
                response_format={"type": "json_object"},
            )
        with timings.measure("parsing"):
            structured = parse_structured_rag_response(raw_answer)
            answer = render_structured_answer(structured)
            cited_source_numbers = validated_source_numbers(
                [
                    *structured.cited_source_numbers,
                    *source_numbers_from_text(structured.grounded_answer),
                ],
                retrieval_results=results,
            )
    else:
        raw_answer = generate_llm_response(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0,
            response_format={"type": "json_object"},
        )
        structured = parse_structured_rag_response(raw_answer)
        answer = render_structured_answer(structured)
        cited_source_numbers = validated_source_numbers(
            [
                *structured.cited_source_numbers,
                *source_numbers_from_text(structured.grounded_answer),
            ],
            retrieval_results=results,
        )

    if not cited_source_numbers and not _is_no_information_answer(structured.grounded_answer):
        return GeneratedAnswer(
            answer=NO_RELEVANT_INFORMATION_MESSAGE,
            sources=[],
        )

    return GeneratedAnswer(
        answer=answer,
        sources=sources_from_numbers(
            cited_source_numbers,
            retrieval_results=results,
        ),
    )
