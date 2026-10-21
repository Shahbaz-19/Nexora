"""Create PostgreSQL extensions required before the first Alembic table migration."""

from sqlalchemy import text

from app.database import engine


def main() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


if __name__ == "__main__":
    main()
