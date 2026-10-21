from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


@dataclass
class ParsedSection:
    content: str
    page_number: int | None = None


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_extension(filename: str) -> str:
    extension = get_extension(filename)

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Supported formats: PDF, TXT, MD."
        )

    return extension


def parse_pdf(file_bytes: bytes) -> list[ParsedSection]:
    reader = PdfReader(BytesIO(file_bytes))

    sections: list[ParsedSection] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()

        if not text or not text.strip():
            continue

        sections.append(
            ParsedSection(
                content=text.strip(),
                page_number=page_number,
            )
        )

    if not sections:
        raise ValueError(
            "No extractable text was found in the PDF."
        )

    return sections


def parse_text_file(
    file_bytes: bytes,
) -> list[ParsedSection]:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Text file must use UTF-8 encoding."
        ) from exc

    if not text.strip():
        raise ValueError("The uploaded file is empty.")

    return [
        ParsedSection(
            content=text.strip(),
            page_number=None,
        )
    ]


def parse_document(
    filename: str,
    file_bytes: bytes,
) -> list[ParsedSection]:
    extension = validate_extension(filename)

    if extension == ".pdf":
        return parse_pdf(file_bytes)

    return parse_text_file(file_bytes)