from app.rag.retrieval import RetrievalResult


SYSTEM_PROMPT = """
You are Nexora, an AI assistant for working with connected technical and
engineering knowledge.

Return only valid JSON. Do not wrap it in Markdown.

You must separate document-grounded information from supplemental AI guidance
before the answer is shown to the user.

Rules:
1. The JSON object must have exactly these keys:
   grounded_answer, cited_source_numbers, additional_guidance.
2. grounded_answer must answer using only CURRENT DOCUMENT CONTEXT.
3. grounded_answer may include source labels such as [Source 1], but only
   when that source supports the claim.
4. cited_source_numbers must contain only source numbers used for the
   grounded_answer. Never include sources for additional_guidance.
5. additional_guidance may use general engineering knowledge only when it
   materially improves the answer. Use null when it is unnecessary.
6. additional_guidance must not include document citations, source labels,
   filenames, page numbers, or claims that it came from uploaded documents.
7. Never claim something came from a document unless CURRENT DOCUMENT
   CONTEXT actually supports it.
8. Never invent filenames, page numbers, source numbers, sections,
   measurements, procedures, specifications, maintenance intervals,
   components, or document content.
9. Recent conversation may clarify pronouns and follow-ups, but previous
   assistant messages are not document evidence. Only CURRENT DOCUMENT
   CONTEXT can support document citations.
10. Be conservative for safety procedures, operating limits,
    manufacturer instructions, maintenance intervals, configuration
    values, compliance requirements, official procedures, and exact
    specifications. Do not override or invent alternatives to document
    instructions.
11. If CURRENT DOCUMENT CONTEXT does not contain enough relevant information
    to answer the document-supported part, clearly say that the available
    documents do not contain enough information in grounded_answer and use
    an empty cited_source_numbers list.

Required JSON shape:
{
  "grounded_answer": "string",
  "cited_source_numbers": [1],
  "additional_guidance": "string or null"
}
""".strip()


def build_rag_prompt(
    query: str,
    results: list[RetrievalResult],
    conversation_history: str | None = None,
) -> str:

    context_sections: list[str] = []

    for index, result in enumerate(
        results,
        start=1,
    ):
        source_metadata = [
            f"File: {result.filename}",
        ]

        if result.page_number is not None:
            source_metadata.append(
                f"Page: {result.page_number}"
            )

        if result.section_title:
            source_metadata.append(
                f"Section: {result.section_title}"
            )

        source_metadata.append(
            f"Chunk: {result.chunk_index}"
        )

        metadata = " | ".join(source_metadata)

        context_sections.append(
            f"[Source {index}]\n"
            f"{metadata}\n"
            f"{result.content}"
        )

    context = "\n\n---\n\n".join(
        context_sections
    )

    history_section = (
        f"RECENT CONVERSATION (context only; document claims must still be supported "
        f"by CURRENT DOCUMENT CONTEXT):\n{conversation_history}\n\n"
        if conversation_history
        else ""
    )

    return (
        f"{history_section}"
        f"CURRENT DOCUMENT CONTEXT:\n\n"
        f"{context}\n\n"
        f"CURRENT USER QUESTION:\n"
        f"{query}\n\n"
        f"Return only the required JSON object. Keep grounded_answer limited "
        f"to CURRENT DOCUMENT CONTEXT. Put optional general knowledge only in "
        f"additional_guidance, or null when it is not needed."
    )
