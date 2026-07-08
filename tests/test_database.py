import pytest
from database.connection import clean_async_database_url

@pytest.mark.parametrize(
    "input_url, expected_url",
    [
        # 1. Handling empty or falsy inputs
        ("", ""),
        (None, None),

        # 2. Scheme modifications (Standard Render/Neon outputs)
        (
            "postgres://user:pass@localhost:5432/db", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),
        (
            "postgresql://user:pass@localhost:5432/db", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),

        # 3. Already correct asyncpg scheme should not be modified
        (
            "postgresql+asyncpg://user:pass@localhost:5432/db", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),

        # 4. Stripping single incompatible parameters
        (
            "postgres://user:pass@localhost:5432/db?sslmode=require", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),
        (
            "postgresql://user:pass@localhost:5432/db?channel_binding=prefer", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),

        # 5. Stripping multiple incompatible parameters simultaneously
        (
            "postgres://user:pass@localhost:5432/db?sslmode=verify-full&channel_binding=require", 
            "postgresql+asyncpg://user:pass@localhost:5432/db"
        ),

        # 6. Preserving legitimate parameters while removing bad ones
        (
            "postgres://user:pass@localhost:5432/db?sslmode=require&application_name=myapp", 
            "postgresql+asyncpg://user:pass@localhost:5432/db?application_name=myapp"
        ),
        (
            "postgresql://user:pass@localhost:5432/db?keepalives=1&channel_binding=disable&timeout=30", 
            "postgresql+asyncpg://user:pass@localhost:5432/db?keepalives=1&timeout=30"
        ),

        # 7. Testing URLs with complex symbols or parameters but no targeted bad flags
        (
            "postgresql://user:pass@localhost:5432/db?options=-c%20search_path=test", 
            "postgresql+asyncpg://user:pass@localhost:5432/db?options=-c+search_path%3Dtest"
        ),
    ]
)
def test_clean_async_database_url(input_url, expected_url):
    """Verifies that database URLs are correctly formatted for the asyncpg driver."""
    assert clean_async_database_url(input_url) == expected_url