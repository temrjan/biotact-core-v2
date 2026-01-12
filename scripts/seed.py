"""Seed script to populate database with initial test data."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select

from biotact.core.database import AsyncSessionLocal, engine
from biotact.core.security import hash_password
from biotact.models import Base
from biotact.models.user import User


async def create_tables() -> None:
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully")


async def seed_users() -> None:
    """Seed test users for each department."""
    users_data = [
        {
            "email": "admin@biotact.uz",
            "password": "admin123",
            "full_name": "Admin User",
            "department_id": "admin",
        },
        {
            "email": "marketing@biotact.uz",
            "password": "marketing123",
            "full_name": "Marketing Manager",
            "department_id": "marketing",
        },
        {
            "email": "sales@biotact.uz",
            "password": "sales123",
            "full_name": "Sales Representative",
            "department_id": "sales",
        },
        {
            "email": "callcenter@biotact.uz",
            "password": "callcenter123",
            "full_name": "Call Center Operator",
            "department_id": "call_center",
        },
        {
            "email": "logistics@biotact.uz",
            "password": "logistics123",
            "full_name": "Logistics Coordinator",
            "department_id": "logistics",
        },
        {
            "email": "accounting@biotact.uz",
            "password": "accounting123",
            "full_name": "Accountant",
            "department_id": "accounting",
        },
        {
            "email": "instagram@biotact.uz",
            "password": "instagram123",
            "full_name": "Instagram Bot",
            "department_id": "instagram",
        },
        {
            "email": "dashboard@biotact.uz",
            "password": "dashboard123",
            "full_name": "Dashboard User",
            "department_id": "dashboard",
        },
    ]

    async with AsyncSessionLocal() as session:
        for user_data in users_data:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.email == user_data["email"])
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"User {user_data['email']} already exists, skipping")
                continue

            user = User(
                email=user_data["email"],
                hashed_password=hash_password(user_data["password"]),
                full_name=user_data["full_name"],
                department_id=user_data["department_id"],
                is_active=True,
            )
            session.add(user)
            print(f"Created user: {user_data['email']}")

        await session.commit()

    print("\nSeed completed successfully!")
    print("\nTest credentials:")
    print("-" * 40)
    for user_data in users_data:
        print(f"  {user_data['email']} / {user_data['password']}")


async def main() -> None:
    """Run seed script."""
    print("=" * 50)
    print("Biotact v2 - Database Seed Script")
    print("=" * 50)
    print()

    # Create tables if they don't exist
    await create_tables()

    # Seed users
    await seed_users()


if __name__ == "__main__":
    asyncio.run(main())
