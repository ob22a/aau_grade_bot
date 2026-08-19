import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.connection import create_engine_from_url
from src.config import load_settings
from src.database.models import Campus

async def seed_campuses():
    settings = load_settings()
    engine = create_engine_from_url(settings.database_url)
    async with AsyncSession(engine) as session:
        # Check existing
        result = await session.execute(select(Campus))
        existing = {c.campus_id for c in result.scalars().all()}
        
        campuses = [
            Campus(campus_id="CTBE", full_name="College of Telecommunications and Broadcast Engineering"),
            Campus(campus_id="Main", full_name="Main Campus")
        ]
        
        added = 0
        for c in campuses:
            if c.campus_id not in existing:
                session.add(c)
                added += 1
                
        if added > 0:
            await session.commit()
            print(f"Added {added} campuses.")
        else:
            print("Campuses already exist.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_campuses())
