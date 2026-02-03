import asyncio
import os
from database.connection import engine
from database.models import Base
from dotenv import load_dotenv

load_dotenv()

async def init_db():
    print(f"Connecting to {os.getenv('DATABASE_URL')}...")
    async with engine.begin() as conn:
        # Import models here to ensure they are registered with Base.metadata
        from database.models import Campus, Department, User, UserCredential, Course, Assessment, AuditLog, GradeCheckStatus, SystemSetting, SemesterResult, Grade
        
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        
        # Seed default data
        from sqlalchemy.dialects.postgresql import insert
        from database.models import Campus, Department
        
        print("Seeding default data...")
        await conn.execute(insert(Campus).values(campus_id="CTBE", full_name="College of Technology and Built Environment").on_conflict_do_nothing())
        await conn.execute(insert(Department).values(department_id="SITE", full_name="School of Information Technology Education", campus_id="CTBE").on_conflict_do_nothing())
        # Add a few common ones
        await conn.execute(insert(Department).values(department_id="ELECT", full_name="Electrical Engineering", campus_id="CTBE").on_conflict_do_nothing())
        await conn.execute(insert(Department).values(department_id="MECH", full_name="Mechanical Engineering", campus_id="CTBE").on_conflict_do_nothing())

        print("Tables created and seeded successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())
