import asyncio
import aiosqlite
import os

DB_PATH = "C:\\Users\\shiva\\OneDrive\\Desktop\\code-ex\\exchange.db"

async def reset_db():
    print(f"Connecting to {DB_PATH}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN TRANSACTION")
        try:
            await db.execute("DELETE FROM team_scores")
            await db.execute("DELETE FROM execution_results")
            await db.execute("DELETE FROM submissions")
            await db.execute("DELETE FROM players")
            await db.execute("DELETE FROM teams")
            
            await db.execute("DELETE FROM sqlite_sequence WHERE name IN ('teams', 'players', 'submissions', 'execution_results')")
            
            await db.commit()
            print("Database safely reset. System acts like a fresh start.")
        except Exception as e:
            await db.rollback()
            print(f"Failed to reset DB: {str(e)}")

if __name__ == '__main__':
    asyncio.run(reset_db())
