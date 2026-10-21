import json
import unittest
from datetime import datetime, timezone

from app.routers.chat import stream_validated_response
from app.schemas.chat import (
    ChatMessageResponse, ChatQueryResponse, ChatSessionResponse, ChatSourceResponse,
)


class StreamingTests(unittest.TestCase):
    def test_stream_contains_only_validated_answer_and_complete_payload(self):
        now = datetime.now(timezone.utc)
        source = ChatSourceResponse(document_id=1, filename="manual.pdf", page_number=2, chunk_index=1, similarity_score=.8)
        user = ChatMessageResponse(id=1, role="USER", content="Question", sources=[], created_at=now)
        assistant = ChatMessageResponse(id=2, role="ASSISTANT", content="Validated answer", sources=[source], created_at=now)
        session = ChatSessionResponse(id=1, title="Question", created_at=now, updated_at=now)
        response = ChatQueryResponse(session_id=1, session=session, user_message=user, assistant_message=assistant, answer="Validated answer", sources=[source])

        output = "".join(stream_validated_response(response))
        self.assertIn("event: metadata", output)
        self.assertIn("event: delta", output)
        self.assertIn("event: complete", output)
        complete = output.split("event: complete\ndata: ", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(json.loads(complete)["sources"][0]["filename"], "manual.pdf")


if __name__ == "__main__":
    unittest.main()
