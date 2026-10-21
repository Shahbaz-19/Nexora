from functools import lru_cache
from groq import Groq
from app.core.config import settings


DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 1200


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    return Groq(api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds)


def get_model_name() -> str:
    return settings.groq_model


def generate_llm_response(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    response_format: dict | None = None,
) -> str:

    return generate_chat_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )


def generate_chat_response(
    messages: list[dict[str, str]],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    response_format: dict | None = None,
) -> str:
    """Send an already-structured conversation through the shared Groq client."""

    client = get_groq_client()
    options = {}
    if response_format is not None:
        options["response_format"] = response_format

    response = client.chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
        **options,
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "The language model returned an empty response."
        )

    return content.strip()
