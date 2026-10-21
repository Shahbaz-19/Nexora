import unittest

from app.rag.prompts import SYSTEM_PROMPT, build_rag_prompt
from app.rag.retrieval import RetrievalResult


def result(content: str = "Reservoir level and visible hoses should be checked.") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=1,
        document_id=10,
        filename="cooling-manual.pdf",
        chunk_index=2,
        content=content,
        token_count=12,
        page_number=4,
        section_title="Cooling checks",
        similarity_score=0.91,
    )


class RagPromptTests(unittest.TestCase):
    def test_system_prompt_requests_structured_provenance(self):
        self.assertIn("Return only valid JSON", SYSTEM_PROMPT)
        self.assertIn("grounded_answer", SYSTEM_PROMPT)
        self.assertIn("cited_source_numbers", SYSTEM_PROMPT)
        self.assertIn("additional_guidance", SYSTEM_PROMPT)
        self.assertIn("Only CURRENT DOCUMENT", SYSTEM_PROMPT)
        self.assertIn("CONTEXT can support document citations", SYSTEM_PROMPT)
        self.assertIn("Never include sources for additional_guidance", SYSTEM_PROMPT)
        self.assertIn("Do not override or invent alternatives", SYSTEM_PROMPT)

    def test_rag_prompt_keeps_history_separate_from_document_evidence(self):
        prompt = build_rag_prompt(
            query="Why does that matter?",
            results=[result()],
            conversation_history=(
                "Assistant: The pump also has a hidden bypass valve. [Source 1]"
            ),
        )

        self.assertIn("RECENT CONVERSATION", prompt)
        self.assertIn("context only; document claims must still be supported", prompt)
        self.assertIn("CURRENT DOCUMENT CONTEXT", prompt)
        self.assertIn("[Source 1]", prompt)
        self.assertIn("File: cooling-manual.pdf", prompt)
        self.assertIn("Return only the required JSON object.", prompt)


if __name__ == "__main__":
    unittest.main()
