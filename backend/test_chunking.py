from app.rag.chunking import chunk_text


sample_text = """
Cooling System

The cooling system maintains the correct operating temperature
of the engine and prevents important components from overheating
during normal operation.

Coolant pressure must remain within the recommended operating
range to ensure that coolant circulates correctly throughout
the entire system.

If coolant pressure drops, engineers should inspect the coolant
reservoir, pump, hoses, and connections for leaks or other damage.

The equipment should not be restarted until the cause of the
pressure loss has been identified and the cooling system is
operating normally.
"""


chunks = chunk_text(
    text=sample_text,
    max_tokens=50,
    overlap_tokens=10,
)


for chunk in chunks:
    print("\n" + "=" * 60)
    print(f"Chunk: {chunk.chunk_index}")
    print(f"Tokens: {chunk.token_count}")
    print("-" * 60)
    print(chunk.content)


print("\nTotal chunks:", len(chunks))