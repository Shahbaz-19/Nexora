from sqlalchemy import text

from app.database import engine


try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database();")
        )

        database_name = result.scalar()

        print("DATABASE CONNECTION SUCCESSFUL")
        print(f"Connected to: {database_name}")

except Exception as error:
    print("DATABASE CONNECTION FAILED")
    print(error)