import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from sqlalchemy.orm import Session

from app.rag.generation import GeneratedAnswer, generate_rag_answer
from app.rag.llm import generate_chat_response, generate_llm_response
from app.rag.timing import RAGTimings


MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARACTERS = 7000
ROUTER_MAX_TOKENS = 12
REWRITE_MAX_TOKENS = 180
CASUAL_MAX_TOKENS = 350
ROUTER_HISTORY_MESSAGES = 4
ROUTER_HISTORY_CHARACTERS = 2000

logger = logging.getLogger(__name__)
timing_logger = logging.getLogger("uvicorn.error")


class HistoryMessage(Protocol):
    role: str
    content: str
    sources: list[dict]


class ConversationRoute(str, Enum):
    CASUAL = "CASUAL"
    DOCUMENT_QUERY = "DOCUMENT_QUERY"
    CONTEXTUAL_FOLLOWUP = "CONTEXTUAL_FOLLOWUP"


@dataclass
class ConversationAnswer:
    answer: str
    sources: list
    route: ConversationRoute


CASUAL_MESSAGES = {
    "hi", "hello", "hey", "hiya", "thanks", "thank you", "good morning",
    "good afternoon", "good evening", "bye", "goodbye", "nice", "cool",
    "okay", "ok", "got it", "who are you", "what can you do",
    "tell me about yourself", "what did we just discuss",
}
FOLLOWUP_PATTERN = re.compile(
    r"(?:^why\??$|\b(that|this|it|those|these|the (first|second|third|fourth|last) "
    r"(one|point|reason)?|explain .*again|simpl(?:e|er|ify)|in simple words|"
    r"elaborate|what about|why does that|why is that|what does that mean|"
    r"give (me )?an example)\b)",
    re.IGNORECASE,
)
SOCIAL_PATTERN = re.compile(
    r"\b(what'?s up|whats up|how are you|how'?s (it|everything) going|"
    r"how is (it|everything) going|how have you been|nice to meet you)\b",
    re.IGNORECASE,
)
DOCUMENT_PATTERN = re.compile(
    r"\b(document|documents|manual|report|pdf|file|uploaded|knowledge base|"
    r"according to|what does .* say|summari[sz]e|page|section)\b",
    re.IGNORECASE,
)
TECHNICAL_REQUEST_PATTERN = re.compile(
    r"^((what|which|why|when|where)\b|how (does|do|is)|"
    r"explain|define|describe|compare|calculate|derive|solve|analy[sz]e|"
    r"summari[sz]e)\b",
    re.IGNORECASE,
)
ACRONYM_PATTERN = re.compile(r"\b[A-Z][A-Z0-9-]{1,}\b")


def bounded_history(messages: Sequence[HistoryMessage]) -> list[HistoryMessage]:
    """Keep the newest complete messages within fixed message and character limits."""
    selected: list[HistoryMessage] = []
    characters = 0
    for message in reversed(messages[-MAX_HISTORY_MESSAGES:]):
        size = len(message.content)
        if selected and characters + size > MAX_HISTORY_CHARACTERS:
            break
        selected.append(message)
        characters += size
    return list(reversed(selected))


def format_history(messages: Sequence[HistoryMessage]) -> str:
    return "\n".join(
        f"{'User' if message.role == 'USER' else 'Assistant'}: {message.content}"
        for message in bounded_history(messages)
    )


def format_router_history(messages: Sequence[HistoryMessage]) -> str:
    """Use a smaller history window for the intent classifier."""
    lines: list[str] = []
    characters = 0
    for message in reversed(bounded_history(messages)[-ROUTER_HISTORY_MESSAGES:]):
        line = f"{'User' if message.role == 'USER' else 'Assistant'}: {message.content}"
        remaining = ROUTER_HISTORY_CHARACTERS - characters
        if remaining <= 0:
            break
        lines.append(line[:remaining])
        characters += min(len(line), remaining)
    return "\n".join(reversed(lines))


def _normalize(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _fallback_route(
    query: str,
    normalized: str,
    history: Sequence[HistoryMessage],
) -> ConversationRoute:
    """Classify safely when the lightweight LLM router is unavailable or invalid."""
    if SOCIAL_PATTERN.search(normalized):
        return ConversationRoute.CASUAL
    if history and FOLLOWUP_PATTERN.search(normalized):
        return ConversationRoute.CONTEXTUAL_FOLLOWUP
    if (
        DOCUMENT_PATTERN.search(normalized)
        or TECHNICAL_REQUEST_PATTERN.search(normalized)
        or ACRONYM_PATTERN.search(query)
    ):
        return ConversationRoute.DOCUMENT_QUERY

    # An unknown social statement is safer on the non-grounded conversational
    # path than inventing a document search. That prompt cannot claim document facts.
    return ConversationRoute.CASUAL


def classify_message(
    query: str,
    history: Sequence[HistoryMessage],
) -> ConversationRoute:
    normalized = _normalize(query)
    casual_key = normalized.rstrip(".!?")
    if normalized in CASUAL_MESSAGES or casual_key in CASUAL_MESSAGES:
        return ConversationRoute.CASUAL
    if SOCIAL_PATTERN.search(normalized):
        return ConversationRoute.CASUAL
    if history and FOLLOWUP_PATTERN.search(normalized):
        return ConversationRoute.CONTEXTUAL_FOLLOWUP
    if DOCUMENT_PATTERN.search(normalized):
        return ConversationRoute.DOCUMENT_QUERY
    if TECHNICAL_REQUEST_PATTERN.search(normalized) or ACRONYM_PATTERN.search(query):
        return ConversationRoute.DOCUMENT_QUERY

    prompt = (
        "Classify the current message for an engineering knowledge assistant. "
        "Return exactly one of these values with no punctuation or explanation: "
        "CASUAL, DOCUMENT_QUERY, CONTEXTUAL_FOLLOWUP. CASUAL includes social chat "
        "such as 'what's up' and 'how are you', acknowledgements, and questions "
        "about the assistant. DOCUMENT_QUERY asks for technical or uploaded-knowledge "
        "facts. CONTEXTUAL_FOLLOWUP relies on an earlier turn, such as 'why?', "
        "'make it simpler', or 'give an example'.\n\n"
        f"RECENT CONVERSATION:\n{format_router_history(history) or '(none)'}\n\n"
        f"CURRENT MESSAGE:\n{query}"
    )
    try:
        classification = generate_llm_response(
            system_prompt="You are a strict message router. Output one label only.",
            user_prompt=prompt,
            temperature=0,
            max_tokens=ROUTER_MAX_TOKENS,
        ).strip().upper()
        if classification not in ConversationRoute._value2member_map_:
            raise ValueError("Router returned no recognized label.")
        return ConversationRoute(classification)
    except Exception:
        return _fallback_route(query, normalized, history)


def _recent_document_context(history: Sequence[HistoryMessage]) -> bool:
    for message in reversed(bounded_history(history)):
        if message.role == "ASSISTANT":
            return bool(message.sources)
    return False


def rewrite_followup_query(query: str, history: Sequence[HistoryMessage]) -> str:
    prompt = (
        "Rewrite the current follow-up as one standalone semantic-search query. "
        "Resolve pronouns, numbered references, and phrases such as 'that' from the "
        "conversation. Preserve the technical subject. Output only the query.\n\n"
        f"RECENT CONVERSATION:\n{format_history(history)}\n\n"
        f"FOLLOW-UP:\n{query}"
    )
    try:
        rewritten = generate_llm_response(
            system_prompt="You rewrite contextual questions for document retrieval.",
            user_prompt=prompt,
            temperature=0,
            max_tokens=REWRITE_MAX_TOKENS,
        ).strip().strip('"')
        if rewritten:
            return rewritten
    except Exception:
        pass

    previous_context = [
        message.content
        for message in bounded_history(history)[-2:]
    ]
    return " ".join([*previous_context, query]).strip()


CASUAL_SYSTEM_PROMPT = """
You are Nexora. Be friendly, natural, concise, and
professional. For social conversation, respond directly without forcing every
reply to mention documents, engineering, or the knowledge base. When asked about
your capabilities, explain naturally that you can discuss ideas and answer grounded
questions from the user's uploaded technical knowledge. Do not claim that you
searched documents, and do not invent document facts or citations. If the user
asks about prior discussion and no history is supplied, explain that this new
conversation has no earlier context.
""".strip()


def generate_casual_answer(
    query: str,
    history: Sequence[HistoryMessage],
) -> str:
    messages = [{"role": "system", "content": CASUAL_SYSTEM_PROMPT}]
    messages.extend(
        {
            "role": "user" if message.role == "USER" else "assistant",
            "content": message.content,
        }
        for message in bounded_history(history)
    )
    messages.append({"role": "user", "content": query})
    return generate_chat_response(
        messages=messages,
        temperature=0.3,
        max_tokens=CASUAL_MAX_TOKENS,
    )


def generate_conversation_answer(
    db: Session,
    user_id: int,
    query: str,
    history: Sequence[HistoryMessage],
    top_k: int,
) -> ConversationAnswer:
    timings = RAGTimings()
    route: ConversationRoute | None = None
    result: ConversationAnswer
    with timings.measure("total"):
        recent_history = bounded_history(history)
        with timings.measure("route"):
            route = classify_message(query, recent_history)
        logger.info("Conversation route: %s", route.value)

        if route == ConversationRoute.CASUAL:
            result = ConversationAnswer(
                generate_casual_answer(query, recent_history),
                [],
                route,
            )

        elif route == ConversationRoute.CONTEXTUAL_FOLLOWUP and not _recent_document_context(recent_history):
            result = ConversationAnswer(
                generate_casual_answer(query, recent_history),
                [],
                route,
            )

        else:
            retrieval_query = None
            if route == ConversationRoute.CONTEXTUAL_FOLLOWUP:
                with timings.measure("rewrite"):
                    retrieval_query = rewrite_followup_query(query, recent_history)

            answer: GeneratedAnswer = generate_rag_answer(
                db=db,
                user_id=user_id,
                query=query,
                top_k=top_k,
                retrieval_query=retrieval_query,
                conversation_history=format_history(recent_history) or None,
                timings=timings,
            )
            result = ConversationAnswer(answer.answer, answer.sources, route)

    timing_logger.info(timings.format(route.value if route else "UNKNOWN"))
    return result
