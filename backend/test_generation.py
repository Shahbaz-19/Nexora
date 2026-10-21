from app.database import SessionLocal
from app.rag.generation import generate_rag_answer


QUERY = "Why is NPV considered better than IRR?"
USER_ID = 2


def main():
    db = SessionLocal()

    try:
        result = generate_rag_answer(
            db=db,
            user_id=USER_ID,
            query=QUERY,
            top_k=3,
        )

        print("\nQUESTION")
        print("=" * 70)
        print(QUERY)

        print("\nANSWER")
        print("=" * 70)
        print(result.answer)

        print("\nSOURCES")
        print("=" * 70)

        for index, source in enumerate(
            result.sources,
            start=1,
        ):
            print(
                f"[Source {index}] "
                f"{source.filename} | "
                f"Page: {source.page_number} | "
                f"Chunk: {source.chunk_index} | "
                f"Similarity: {source.similarity_score:.4f}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()