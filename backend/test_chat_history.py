"""Integration checks against the migrated PostgreSQL DB; all test data is rolled back.
Run: python -m unittest test_chat_history -v
Set RUN_LIVE_RAG=1 to also exercise real Nomic ingestion, pgvector, and Groq.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.rag.generation import extract_cited_sources
from app.routers.chat import conversation_title


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.credentials = {"email": f"chat-{uuid4().hex}@example.com", "password": "HistoryTest-123!"}
        result = self.client.post('/auth/register', json={**self.credentials, "full_name": "History Test"})
        self.assertEqual(result.status_code, 201, result.text)
        self.user_id = result.json()['id']
        login = self.client.post('/auth/login', json=self.credentials)
        self.assertEqual(login.status_code, 200)
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def create(self):
        response = self.client.post('/chat/sessions', headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def query(self, session_id, query='Why is NPV useful?'):
        return self.client.post('/chat/query', headers=self.headers, json={"session_id": session_id, "query": query, "top_k": 5})

    @patch('app.routers.chat.generate_conversation_answer')
    def test_history_citations_order_and_delete(self, generate):
        source = SimpleNamespace(document_id=123, filename='engineering.pdf', page_number=2, chunk_index=1, similarity_score=.76)
        generate.return_value = SimpleNamespace(answer='**Evidence** [Source 1]', sources=[source])
        first, second = self.create(), self.create()
        for _ in range(2):
            result = self.query(first)
            self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(generate.call_args.kwargs['user_id'], self.user_id)
        self.assertEqual(generate.call_args.kwargs['query'], 'Why is NPV useful?')
        self.assertEqual(generate.call_args.kwargs['top_k'], 5)
        self.assertEqual(len(generate.call_args.kwargs['history']), 2)
        sessions = self.client.get('/chat/sessions', headers=self.headers).json()
        self.assertEqual([s['id'] for s in sessions], [first, second])
        self.assertEqual(sessions[0]['title'], 'Why is NPV useful?')
        detail = self.client.get(f'/chat/sessions/{first}', headers=self.headers).json()
        self.assertEqual([m['role'] for m in detail['messages']], ['USER', 'ASSISTANT'] * 2)
        self.assertEqual(detail['messages'][1]['sources'][0]['filename'], 'engineering.pdf')
        self.assertEqual(detail['messages'][1]['sources'][0]['page_number'], 2)
        self.assertEqual(detail['messages'][1]['content'], '**Evidence** [Source 1]')
        self.assertEqual(self.client.delete(f'/chat/sessions/{first}', headers=self.headers).status_code, 204)
        self.assertIsNone(self.db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == first)))
        self.assertEqual(self.client.get(f'/chat/sessions/{first}', headers=self.headers).status_code, 404)

    @patch('app.routers.chat.generate_conversation_answer')
    def test_ownership(self, generate):
        other = User(email=f'other-{uuid4().hex}@example.com', full_name='Other', hashed_password='unused')
        self.db.add(other); self.db.flush()
        session = ChatSession(user_id=other.id); self.db.add(session); self.db.commit()
        session_id = session.id
        self.assertEqual(self.client.get('/chat/sessions', headers=self.headers).json(), [])
        self.assertEqual(self.client.get(f'/chat/sessions/{session_id}', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.delete(f'/chat/sessions/{session_id}', headers=self.headers).status_code, 404)
        self.assertEqual(self.query(session_id).status_code, 404)
        generate.assert_not_called()
        self.assertIsNotNone(self.db.get(ChatSession, session_id))

    @patch('app.routers.chat.generate_conversation_answer', side_effect=RuntimeError('private provider details'))
    def test_failed_generation_rolls_back(self, generate):
        session_id = self.create()
        result = self.query(session_id)
        self.assertEqual(result.status_code, 500)
        self.assertNotIn('private', result.text)
        self.assertEqual(self.client.get(f'/chat/sessions/{session_id}', headers=self.headers).json()['messages'], [])
        self.assertEqual(self.query(None).status_code, 500)
        self.assertEqual(len(self.client.get('/chat/sessions', headers=self.headers).json()), 1)

    @patch('app.routers.chat.generate_conversation_answer')
    def test_implicit_session_and_user_cascade(self, generate):
        generate.return_value = SimpleNamespace(answer='No relevant documents.', sources=[])
        result = self.query(None)
        self.assertEqual(result.status_code, 200, result.text)
        session_id = result.json()['session_id']
        self.db.execute(text('DELETE FROM users WHERE id=:id'), {'id': self.user_id})
        self.db.commit()
        self.assertIsNone(self.db.scalar(select(ChatSession.id).where(ChatSession.id == session_id)))
        self.assertIsNone(self.db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == session_id)))

    def test_auth_refresh_and_validation(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=self.headers).status_code, 200)
        refreshed = self.client.post('/auth/refresh')
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn('httponly', refreshed.headers['set-cookie'].lower())
        self.assertIn(self.client.get('/chat/sessions').status_code, [401, 403])
        self.assertEqual(self.query(None, '   ').status_code, 422)
        self.assertEqual(self.client.post('/documents/upload', headers=self.headers, files={'file': ('bad.exe', b'bad')}).status_code, 415)
        self.assertEqual(self.client.post('/auth/logout').status_code, 200)
        self.assertEqual(self.client.post('/auth/refresh').status_code, 401)

    def test_title_and_citation_validation(self):
        self.assertEqual(conversation_title('  Why is NPV\nuseful?  '), 'Why is NPV useful?')
        self.assertLessEqual(len(conversation_title('engineering ' * 30)), 80)
        source = SimpleNamespace(filename='trusted.pdf')
        self.assertEqual(extract_cited_sources('[Source 1] [Source 99] [Source 1]', [source]), [source])

    @unittest.skipUnless(os.getenv('RUN_LIVE_RAG') == '1', 'Set RUN_LIVE_RAG=1 for real Nomic/Groq integration')
    def test_live_upload_retrieval_and_generation(self):
        result = self.client.post('/documents/upload', headers=self.headers, files={'file': ('history-validation.txt', b'The HX-42 engineering pump requires a discharge pressure of 18 bar. Its scheduled inspection interval is 120 operating hours.', 'text/plain')})
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()['status'], 'READY')
        session_id = self.create()
        answer = self.query(session_id, 'What discharge pressure does the HX-42 pump require? Cite the source.')
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertIn('18', answer.json()['answer'])
        self.assertTrue(answer.json()['sources'])
        detail = self.client.get(f'/chat/sessions/{session_id}', headers=self.headers).json()
        self.assertEqual(detail['messages'][1]['sources'], answer.json()['sources'])
        self.assertEqual(detail['messages'][1]['sources'][0]['filename'], 'history-validation.txt')

    @unittest.skipUnless(os.getenv('RUN_LIVE_CONVERSATION') == '1', 'Set RUN_LIVE_CONVERSATION=1 for live conversational RAG')
    def test_live_conversation_routing_and_followups(self):
        content = (
            b'NPV is preferred to IRR for four reasons. 1. NPV directly measures added shareholder wealth. '
            b'2. NPV is an absolute monetary measure. 3. For mutually exclusive projects, NPV ranks alternatives '
            b'by the shareholder wealth each one adds, avoiding misleading percentage rankings from IRR. '
            b'4. NPV can use changing discount rates when the cost of capital varies.'
        )
        upload = self.client.post('/documents/upload', headers=self.headers, files={
            'file': ('investment-appraisal.txt', content, 'text/plain')
        })
        self.assertEqual(upload.status_code, 201, upload.text)
        session_id = self.create()

        for casual_query in ('hi', 'whats up', 'how are you?', 'thanks', 'what can you do?'):
            casual = self.query(session_id, casual_query)
            self.assertEqual(casual.status_code, 200, casual.text)
            self.assertEqual(casual.json()['sources'], [])
            self.assertNotIn("couldn't find relevant information", casual.json()['answer'].lower())

        initial = self.query(session_id, 'Why is NPV considered better than IRR?')
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertTrue(initial.json()['sources'])
        self.assertEqual(initial.json()['sources'][0]['filename'], 'investment-appraisal.txt')

        followup = self.query(session_id, 'Explain the third one again in simple words.')
        self.assertEqual(followup.status_code, 200, followup.text)
        self.assertTrue(followup.json()['sources'])
        self.assertIn('exclusive', followup.json()['answer'].lower())

        second_followup = self.query(session_id, 'Why does that matter?')
        self.assertEqual(second_followup.status_code, 200, second_followup.text)
        self.assertTrue(second_followup.json()['sources'])

        thanks = self.query(session_id, 'thanks')
        self.assertEqual(thanks.status_code, 200, thanks.text)
        self.assertEqual(thanks.json()['sources'], [])

        new_session = self.create()
        isolated = self.query(new_session, 'What did we just discuss?')
        self.assertEqual(isolated.status_code, 200, isolated.text)
        self.assertEqual(isolated.json()['sources'], [])
        self.assertNotIn('npv', isolated.json()['answer'].lower())


if __name__ == '__main__':
    unittest.main()
