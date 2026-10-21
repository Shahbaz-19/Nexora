import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.rag.conversation import ConversationRoute, generate_conversation_answer
from app.rag.generation import (
    NO_RELEVANT_INFORMATION_MESSAGE,
    SUPPLEMENTAL_DISCLAIMER,
    generate_rag_answer,
    parse_structured_rag_response,
    remove_inline_source_markers,
    render_structured_answer,
    sources_from_numbers,
)
from app.rag.retrieval import RetrievalResult


def source(number: int) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=number,
        document_id=number * 10,
        filename=f"source-{number}.pdf",
        chunk_index=number - 1,
        content=f"Document evidence {number}",
        token_count=10,
        page_number=number,
        section_title=None,
        similarity_score=0.9,
    )


class StructuredProvenanceTests(unittest.TestCase):
    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_valid_structured_response_returns_trusted_source_without_supplement(self, retrieve, llm):
        retrieve.return_value = [source(1)]
        llm.return_value = (
            '{"grounded_answer":"Pressure is 2.2-2.8 bar. [Source 1]",'
            '"cited_source_numbers":[1],"additional_guidance":null}'
        )

        result = generate_rag_answer(Mock(), 7, "What is the normal pressure?")

        self.assertEqual(result.answer, "Pressure is 2.2-2.8 bar.")
        self.assertEqual(result.sources, [retrieve.return_value[0]])
        self.assertNotIn("Additional guidance", result.answer)
        self.assertEqual(llm.call_args.kwargs["response_format"], {"type": "json_object"})

    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_supplemental_guidance_is_rendered_separately(self, retrieve, llm):
        retrieve.return_value = [source(1)]
        llm.return_value = (
            '{"grounded_answer":"Inspect the reservoir and hoses. [Source 1]",'
            '"cited_source_numbers":[1],'
            '"additional_guidance":"Another diagnostic avenue is checking whether air is trapped in the loop."}'
        )

        result = generate_rag_answer(Mock(), 7, "What else should I inspect?")

        self.assertIn("Inspect the reservoir and hoses.", result.answer)
        self.assertNotIn("[Source 1]", result.answer)
        self.assertIn("### Additional guidance", result.answer)
        self.assertIn("air is trapped", result.answer)
        self.assertIn(SUPPLEMENTAL_DISCLAIMER, result.answer)
        self.assertEqual(result.sources, [retrieve.return_value[0]])

    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_invalid_source_number_does_not_reach_trusted_sources(self, retrieve, llm):
        retrieve.return_value = [source(1)]
        llm.return_value = (
            '{"grounded_answer":"The document mentions pressure. [Source 999]",'
            '"cited_source_numbers":[999],"additional_guidance":null}'
        )

        result = generate_rag_answer(Mock(), 7, "What pressure?")

        self.assertEqual(result.answer, NO_RELEVANT_INFORMATION_MESSAGE)
        self.assertNotIn("The document mentions pressure", result.answer)
        self.assertEqual(result.sources, [])

    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_empty_source_list_does_not_allow_substantive_grounded_answer(self, retrieve, llm):
        retrieve.return_value = [source(1)]
        llm.return_value = (
            '{"grounded_answer":"Inspect the radiator cap and thermostat.",'
            '"cited_source_numbers":[],"additional_guidance":null}'
        )

        result = generate_rag_answer(Mock(), 7, "What should I inspect?")

        self.assertEqual(result.answer, NO_RELEVANT_INFORMATION_MESSAGE)
        self.assertNotIn("radiator cap", result.answer)
        self.assertEqual(result.sources, [])

    def test_duplicate_source_numbers_are_deduplicated(self):
        results = [source(1), source(2)]
        self.assertEqual(sources_from_numbers([1, 1, 2], results), results)

    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_supplemental_guidance_cannot_create_citations(self, retrieve, llm):
        retrieve.return_value = [source(1)]
        llm.return_value = (
            '{"grounded_answer":"Inspect the reservoir. [Source 1]",'
            '"cited_source_numbers":[1],'
            '"additional_guidance":"Check vibration [Source 1]. Source 2 also suggests replacing parts."}'
        )

        result = generate_rag_answer(Mock(), 7, "What else?")

        supplemental = result.answer.split("### Additional guidance", 1)[1]
        self.assertNotIn("[Source 1]", supplemental)
        self.assertNotIn("Source 2", supplemental)
        self.assertEqual(result.sources, [retrieve.return_value[0]])

    def test_inline_source_marker_sanitizer_removes_single_marker(self):
        self.assertEqual(
            remove_inline_source_markers("Inspect the reservoir. [Source 1]"),
            "Inspect the reservoir.",
        )

    def test_inline_source_marker_sanitizer_removes_multiple_markers(self):
        self.assertEqual(
            remove_inline_source_markers(
                "Inspect the reservoir [Source 1] and hoses [Source 2]."
            ),
            "Inspect the reservoir and hoses.",
        )

    def test_inline_source_marker_sanitizer_removes_adjacent_markers(self):
        self.assertEqual(
            remove_inline_source_markers(
                "Inspect every 1,000 operating hours. [Source 1][Source 2][Source 3]"
            ),
            "Inspect every 1,000 operating hours.",
        )

    def test_inline_source_marker_sanitizer_removes_repeated_markers(self):
        self.assertEqual(
            remove_inline_source_markers(
                "Check clamps [Source 1]. Check fittings [Source 1]."
            ),
            "Check clamps. Check fittings.",
        )

    def test_inline_source_marker_sanitizer_preserves_normal_bracket_text(self):
        self.assertEqual(
            remove_inline_source_markers(
                "Use the [RESET] button and record values in [bar]."
            ),
            "Use the [RESET] button and record values in [bar].",
        )

    def test_blank_supplemental_guidance_is_treated_as_null(self):
        structured = parse_structured_rag_response(
            '{"grounded_answer":"Grounded. [Source 1]",'
            '"cited_source_numbers":[1],"additional_guidance":"   "}'
        )

        self.assertIsNone(structured.additional_guidance)
        self.assertNotIn("Additional guidance", render_structured_answer(structured))

    @patch("app.rag.generation.generate_llm_response")
    @patch("app.rag.generation.retrieve_chunks")
    def test_no_retrieval_results_keeps_existing_message(self, retrieve, llm):
        retrieve.return_value = []

        result = generate_rag_answer(Mock(), 7, "What is unavailable?")

        self.assertEqual(result.answer, NO_RELEVANT_INFORMATION_MESSAGE)
        self.assertEqual(result.sources, [])
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_chat_response", return_value="Hi! Ready when you are.")
    @patch("app.rag.conversation.generate_rag_answer")
    def test_casual_route_does_not_use_structured_rag(self, rag, chat):
        result = generate_conversation_answer(Mock(), 1, "hi", [], 5)

        self.assertEqual(result.route, ConversationRoute.CASUAL)
        self.assertEqual(result.sources, [])
        rag.assert_not_called()
        chat.assert_called_once()

    @patch("app.rag.conversation.generate_rag_answer")
    @patch("app.rag.conversation.generate_llm_response")
    def test_contextual_followup_still_rewrites_and_uses_rag(self, llm, rag):
        history = [
            SimpleNamespace(role="USER", content="Why is NPV better?", sources=[]),
            SimpleNamespace(
                role="ASSISTANT",
                content="The third reason is mutually exclusive project ranking. [Source 1]",
                sources=[{"filename": "investment.pdf"}],
            ),
        ]
        llm.return_value = "NPV mutually exclusive project ranking"
        trusted_source = source(1)
        rag.return_value = SimpleNamespace(
            answer="It matters because only one alternative can be selected. [Source 1]",
            sources=[trusted_source],
        )

        result = generate_conversation_answer(Mock(), 7, "Why does that matter?", history, 5)

        self.assertEqual(result.route, ConversationRoute.CONTEXTUAL_FOLLOWUP)
        self.assertEqual(result.sources, [trusted_source])
        self.assertEqual(rag.call_args.kwargs["query"], "Why does that matter?")
        self.assertEqual(
            rag.call_args.kwargs["retrieval_query"],
            "NPV mutually exclusive project ranking",
        )


if __name__ == "__main__":
    unittest.main()
