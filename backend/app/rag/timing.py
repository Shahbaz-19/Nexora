from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


class RAGTimings:
    def __init__(self) -> None:
        self._values: dict[str, float] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.add(name, perf_counter() - start)

    def add(self, name: str, seconds: float) -> None:
        self._values[name] = self._values.get(name, 0.0) + seconds

    def milliseconds(self, name: str) -> int:
        return round(self._values.get(name, 0.0) * 1000)

    def format(self, route: str) -> str:
        names = (
            "route",
            "rewrite",
            "embedding",
            "semantic",
            "lexical",
            "fusion",
            "rerank",
            "generation",
            "parsing",
            "total",
        )
        parts = [f"{name}={self.milliseconds(name)}ms" for name in names]
        return f"RAG timing | selected_route={route} | " + " | ".join(parts)
