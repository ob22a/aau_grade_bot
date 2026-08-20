from config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "bot-token")
    monkeypatch.setenv("PORT", "12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("REDIS_URL", raising=False)

    settings = Settings()

    assert settings.bot_token == "bot-token"
    assert settings.port == 12345
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.portal_semaphore_limit == 3


def test_settings_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "bot-token")
    monkeypatch.setenv("PORT", "-1")

    try:
        Settings()
        assert False, "Settings() should have raised ValueError for invalid port"
    except ValueError as exc:
        assert "PORT must be a positive integer" in str(exc)
