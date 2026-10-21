import asyncio

from sqlalchemy import text

from app.db.session import engine

async def main():
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT current_database(), current_user")
        )

        print("Databse connection:", result.one())

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
