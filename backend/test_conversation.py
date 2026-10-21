import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.rag.conversation import (
    MAX_HISTORY_CHARACTERS,
    MAX_HISTORY_MESSAGES,
    ConversationRoute,
    bounded_history,
    classify_message,
    generate_conversation_answer,
)


def message(role, content, sources=None):
    return SimpleNamespace(role=role, content=content, sources=sources or [])


class ConversationRoutingTests(unittest.TestCase):
    @patch("app.rag.conversation.generate_llm_response")
    def test_obvious_casual_messages_do_not_use_router_llm(self, llm):
        for query in ("hi", "Hello!", "thanks", "good morning", "bye"):
            self.assertEqual(classify_message(query, []), ConversationRoute.CASUAL)
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response")
    def test_requested_casual_router_examples_stay_casual(self, llm):
        for query in ("hi", "what's up", "thanks", "how are you?"):
            with self.subTest(query=query):
                self.assertEqual(classify_message(query, []), ConversationRoute.CASUAL)
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response")
    def test_technical_questions_route_to_documents_without_router_llm(self, llm):
        queries = (
            "P-17",
            "What should I inspect first if coolant pressure drops?",
            "Which sensor should I verify if the coolant pressure reading seems inaccurate?",
            "What happens if pump current drops below 3.5 A?",
            "What is the normal coolant pressure range?",
            "How does pump current relate to coolant pressure?",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(classify_message(query, []), ConversationRoute.DOCUMENT_QUERY)
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response")
    def test_manual_question_routes_to_documents(self, llm):
        self.assertEqual(
            classify_message("What does the manual say about restart?", []),
            ConversationRoute.DOCUMENT_QUERY,
        )
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response")
    def test_obvious_followup_uses_history_without_router_llm(self, llm):
        history = [message("USER", "Why is NPV better than IRR?"), message("ASSISTANT", "1. Wealth 2. Scale 3. Ranking")]
        self.assertEqual(
            classify_message("Explain the third one again in simple words.", history),
            ConversationRoute.CONTEXTUAL_FOLLOWUP,
        )
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response", return_value="CASUAL")
    def test_social_messages_are_classified_without_router_llm(self, llm):
        for query in ("whats up", "what's up", "how are you?", "how's it going?"):
            with self.subTest(query=query):
                self.assertEqual(classify_message(query, []), ConversationRoute.CASUAL)
        llm.assert_not_called()

    @patch("app.rag.conversation.generate_llm_response", return_value="CASUAL_CONVERSATION because it is social")
    def test_invalid_classifier_output_is_rejected_then_uses_social_fallback(self, llm):
        self.assertEqual(classify_message("whats up", []), ConversationRoute.CASUAL)

    @patch("app.rag.conversation.generate_llm_response", side_effect=RuntimeError("provider"))
    def test_social_fallback_does_not_retrieve_documents(self, llm):
        for query in ("whats up", "how are you?", "how's it going?"):
            with self.subTest(query=query):
                self.assertEqual(classify_message(query, []), ConversationRoute.CASUAL)

    @patch("app.rag.conversation.generate_llm_response", side_effect=RuntimeError("provider"))
    def test_router_failure_falls_back_to_grounded_path(self, llm):
        self.assertEqual(classify_message("Explain thermodynamic availability", []), ConversationRoute.DOCUMENT_QUERY)
        self.assertEqual(classify_message("Why is NPV considered better than IRR?", []), ConversationRoute.DOCUMENT_QUERY)

    def test_history_window_is_bounded(self):
        history = [message("USER", f"{index}-" + "x" * 900) for index in range(20)]
        selected = bounded_history(history)
        self.assertLessEqual(len(selected), MAX_HISTORY_MESSAGES)
        self.assertLessEqual(sum(len(item.content) for item in selected), MAX_HISTORY_CHARACTERS)
        self.assertTrue(selected[-1].content.startswith("19-"))

    @patch("app.rag.conversation.generate_chat_response", return_value="Hi! How can I help with your engineering knowledge today?")
    @patch("app.rag.conversation.generate_rag_answer")
    def test_greeting_bypasses_retrieval_and_has_no_citations(self, rag, chat):
        result = generate_conversation_answer(Mock(), 1, "hi", [], 5)
        self.assertEqual(result.route, ConversationRoute.CASUAL)
        self.assertEqual(result.sources, [])
        rag.assert_not_called()
        chat.assert_called_once()

    @patch("app.rag.conversation.generate_llm_response", return_value="CASUAL")
    @patch("app.rag.conversation.generate_chat_response", return_value="I'm here and ready to help. What are you working on?")
    @patch("app.rag.conversation.generate_rag_answer")
    def test_requested_casual_messages_all_bypass_rag(self, rag, chat, router):
        queries = ("hi", "whats up", "how are you?", "thanks", "what can you do?")
        for query in queries:
            with self.subTest(query=query):
                result = generate_conversation_answer(Mock(), 1, query, [], 5)
                self.assertEqual(result.route, ConversationRoute.CASUAL)
                self.assertEqual(result.sources, [])
        rag.assert_not_called()
        self.assertEqual(chat.call_count, len(queries))

    @patch("app.rag.conversation.generate_llm_response", return_value="DOCUMENT_QUERY")
    @patch("app.rag.conversation.generate_rag_answer")
    def test_npv_question_uses_rag_and_preserves_trusted_source(self, rag, router):
        source = SimpleNamespace(filename="investment-appraisal.pdf", page_number=2)
        rag.return_value = SimpleNamespace(answer="NPV measures added wealth. [Source 1]", sources=[source])
        result = generate_conversation_answer(
            Mock(), 1, "Why is NPV considered better than IRR?", [], 5
        )
        self.assertEqual(result.route, ConversationRoute.DOCUMENT_QUERY)
        self.assertEqual(result.sources, [source])
        rag.assert_called_once()

    @patch("app.rag.conversation.generate_llm_response")
    @patch("app.rag.conversation.generate_rag_answer")
    def test_technical_queries_use_retrieval_path(self, rag, router):
        source = SimpleNamespace(filename="asterion-gx-400.pdf", page_number=3)
        rag.return_value = SimpleNamespace(
            answer="Inspect reservoir level, visible hoses, clamps, pump housing, radiator connections, and drain fittings. [Source 1]",
            sources=[source],
        )

        queries = (
            "P-17",
            "What should I inspect first if coolant pressure drops?",
            "Which sensor should I verify if the coolant pressure reading seems inaccurate?",
            "What happens if pump current drops below 3.5 A?",
        )

        for query in queries:
            with self.subTest(query=query):
                result = generate_conversation_answer(Mock(), 1, query, [], 5)
                self.assertEqual(result.route, ConversationRoute.DOCUMENT_QUERY)
                self.assertEqual(result.sources, [source])
                self.assertEqual(rag.call_args.kwargs["query"], query)
        router.assert_not_called()

    @patch("app.rag.conversation.generate_rag_answer")
    @patch("app.rag.conversation.generate_llm_response")
    def test_document_followup_rewrites_for_retrieval_and_keeps_original_question(self, llm, rag):
        history = [
            message("USER", "Why is NPV better than IRR?"),
            message("ASSISTANT", "1. Wealth 2. Scale 3. Better ranking for mutually exclusive projects", [{"filename": "investment.pdf"}]),
        ]
        llm.return_value = "Explain why NPV ranks mutually exclusive projects better than IRR."
        trusted_source = SimpleNamespace(filename="investment.pdf")
        rag.return_value = SimpleNamespace(answer="It compares the value each alternative adds. [Source 1]", sources=[trusted_source])

        result = generate_conversation_answer(Mock(), 7, "Explain the third one again.", history, 5)

        self.assertEqual(result.route, ConversationRoute.CONTEXTUAL_FOLLOWUP)
        self.assertEqual(result.sources, [trusted_source])
        self.assertEqual(rag.call_args.kwargs["query"], "Explain the third one again.")
        self.assertEqual(
            rag.call_args.kwargs["retrieval_query"],
            "Explain why NPV ranks mutually exclusive projects better than IRR.",
        )
        self.assertIn("Better ranking", rag.call_args.kwargs["conversation_history"])

    @patch("app.rag.conversation.generate_rag_answer")
    @patch("app.rag.conversation.generate_llm_response")
    def test_short_contextual_variants_remain_grounded(self, llm, rag):
        history = [
            message("USER", "Why is NPV better than IRR?"),
            message("ASSISTANT", "The third reason concerns mutually exclusive projects.", [{"filename": "investment.pdf"}]),
        ]
        llm.return_value = "NPV mutually exclusive project ranking significance"
        rag.return_value = SimpleNamespace(answer="Because only one project can be selected. [Source 1]", sources=[SimpleNamespace(filename="investment.pdf")])
        for query in ("explain the third one simply", "why?", "why does that matter?", "can you give an example?"):
            with self.subTest(query=query):
                result = generate_conversation_answer(Mock(), 1, query, history, 5)
                self.assertEqual(result.route, ConversationRoute.CONTEXTUAL_FOLLOWUP)
                self.assertTrue(result.sources)

    @patch("app.rag.conversation.generate_chat_response", return_value="You're welcome!")
    def test_selected_route_is_logged_without_message_content(self, chat):
        with self.assertLogs("app.rag.conversation", level="INFO") as logs:
            generate_conversation_answer(Mock(), 1, "thanks", [], 5)
        self.assertIn("Conversation route: CASUAL", logs.output[0])
        self.assertNotIn("thanks", logs.output[0])

    @patch("app.rag.conversation.generate_rag_answer")
    def test_rag_timing_log_is_emitted_to_uvicorn_logger(self, rag):
        rag.return_value = SimpleNamespace(
            answer="Inspect the reservoir level. [Source 1]",
            sources=[SimpleNamespace(filename="manual.pdf")],
        )

        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            generate_conversation_answer(
                Mock(),
                1,
                "What should I inspect first if coolant pressure drops?",
                [],
                5,
            )

        timing_lines = [
            output
            for output in logs.output
            if "RAG timing | selected_route=DOCUMENT_QUERY" in output
        ]
        self.assertEqual(len(timing_lines), 1)
        timing_line = timing_lines[0]
        for field in (
            "route=",
            "rewrite=",
            "embedding=",
            "semantic=",
            "lexical=",
            "fusion=",
            "rerank=",
            "generation=",
            "parsing=",
            "total=",
        ):
            self.assertIn(field, timing_line)
        self.assertNotIn("coolant pressure", timing_line)

    @patch("app.rag.conversation.generate_chat_response", return_value="This new chat has no earlier discussion.")
    def test_new_chat_does_not_inherit_history(self, chat):
        result = generate_conversation_answer(Mock(), 1, "What did we just discuss?", [], 5)
        self.assertEqual(result.sources, [])
        sent_messages = chat.call_args.kwargs["messages"]
        self.assertEqual([item["role"] for item in sent_messages], ["system", "user"])


if __name__ == "__main__":
    unittest.main()
