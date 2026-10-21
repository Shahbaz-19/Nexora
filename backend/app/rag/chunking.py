import re
from dataclasses import dataclass

from app.rag.embeddings import count_tokens


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 75


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    token_count: int


def normalize_text(text: str) -> str:
    """Normalize line endings and unnecessary whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in text.split("\n")]

    return "\n".join(lines).strip()


def split_into_paragraphs(text: str) -> list[str]:
    """Split text while preserving paragraph boundaries."""
    text = normalize_text(text)

    if not text:
        return []

    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]


def split_into_sentences(text: str) -> list[str]:
    """
    Split a paragraph at natural sentence boundaries.

    This is intentionally lightweight. More specialized parsing
    can be introduced later for code and technical documents.
    """
    text = text.strip()

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def split_long_sentence(
    text: str,
    max_tokens: int,
) -> list[str]:
    """
    Last-resort splitter for text that has no useful sentence
    boundaries.

    Splits on words rather than raw tokenizer IDs so WordPiece
    fragments such as '##ing' never appear in stored text.
    """
    words = text.split()

    pieces: list[str] = []
    current_words: list[str] = []

    for word in words:
        candidate_words = current_words + [word]
        candidate = " ".join(candidate_words)

        if (
            current_words
            and count_tokens(candidate) > max_tokens
        ):
            pieces.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words.append(word)

    if current_words:
        pieces.append(" ".join(current_words))

    return pieces


def prepare_blocks(
    text: str,
    max_tokens: int,
) -> list[str]:
    """
    Convert document text into natural blocks small enough
    to fit inside a chunk.
    """
    paragraphs = split_into_paragraphs(text)

    blocks: list[str] = []

    for paragraph in paragraphs:

        if count_tokens(paragraph) <= max_tokens:
            blocks.append(paragraph)
            continue

        sentences = split_into_sentences(paragraph)

        for sentence in sentences:

            if count_tokens(sentence) <= max_tokens:
                blocks.append(sentence)
            else:
                blocks.extend(
                    split_long_sentence(
                        sentence,
                        max_tokens,
                    )
                )

    return blocks


def build_overlap(
    blocks: list[str],
    overlap_tokens: int,
) -> list[str]:
    """
    Build overlap from complete previous blocks.

    This prevents overlap from beginning halfway through
    a word or tokenizer subword.
    """
    if overlap_tokens <= 0:
        return []

    overlap: list[str] = []
    total_tokens = 0

    for block in reversed(blocks):
        block_tokens = count_tokens(block)

        if (
            overlap
            and total_tokens + block_tokens > overlap_tokens
        ):
            break

        if block_tokens > overlap_tokens:
            break

        overlap.insert(0, block)
        total_tokens += block_tokens

    return overlap


def chunk_text(
    text: str,
    max_tokens: int = DEFAULT_CHUNK_SIZE,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:

    if not text or not text.strip():
        return []

    if max_tokens <= 0:
        raise ValueError(
            "max_tokens must be greater than 0"
        )

    if overlap_tokens < 0:
        raise ValueError(
            "overlap_tokens cannot be negative"
        )

    if overlap_tokens >= max_tokens:
        raise ValueError(
            "overlap_tokens must be smaller than max_tokens"
        )

    blocks = prepare_blocks(
        text=text,
        max_tokens=max_tokens,
    )

    if not blocks:
        return []

    chunks: list[TextChunk] = []

    current_blocks: list[str] = []

    for block in blocks:

        candidate_blocks = current_blocks + [block]
        candidate_text = "\n\n".join(candidate_blocks)

        if count_tokens(candidate_text) <= max_tokens:
            current_blocks.append(block)
            continue

        if current_blocks:
            content = "\n\n".join(current_blocks)

            chunks.append(
                TextChunk(
                    content=content,
                    chunk_index=len(chunks),
                    token_count=count_tokens(content),
                )
            )

            current_blocks = build_overlap(
                current_blocks,
                overlap_tokens,
            )

        candidate_blocks = current_blocks + [block]
        candidate_text = "\n\n".join(candidate_blocks)

        if count_tokens(candidate_text) > max_tokens:
            current_blocks = [block]
        else:
            current_blocks.append(block)

    if current_blocks:
        content = "\n\n".join(current_blocks)

        chunks.append(
            TextChunk(
                content=content,
                chunk_index=len(chunks),
                token_count=count_tokens(content),
            )
        )

    return chunks