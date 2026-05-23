import asyncio
from app.database import engine, AsyncSessionLocal
from app.models import User, QueryLog, Base
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

async def migrate():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Get unique user_ids from query_logs
        result = await session.execute(select(QueryLog.user_id).distinct())
        user_ids = [row[0] for row in result.fetchall()]
        
        print(f"Found {len(user_ids)} unique users in logs.")
        
        migrated = 0
        for uid in user_ids:
            if not uid: continue
            stmt = insert(User).values(
                user_id=uid,
                username=None,
                full_name="Legacy User"
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            migrated += 1
        
        await session.commit()
        print(f"Successfully ensured {migrated} users are in the Users table.")

if __name__ == "__main__":
    asyncio.run(migrate())
