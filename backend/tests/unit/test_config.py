import pytest

from app.config import Settings


def settings_with(monkeypatch: pytest.MonkeyPatch, cors: str | None) -> Settings:
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    if cors is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", cors)
    return Settings(_env_file=None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ('["https://marg.vercel.app"]', ["https://marg.vercel.app"]),
        ('["https://a.app", "https://b.app"]', ["https://a.app", "https://b.app"]),
        ("https://marg.vercel.app", ["https://marg.vercel.app"]),
        ("https://a.app,https://b.app", ["https://a.app", "https://b.app"]),
        (" https://a.app , https://b.app ", ["https://a.app", "https://b.app"]),
        ("https://marg.vercel.app/", ["https://marg.vercel.app"]),
        ('["https://marg.vercel.app/"]', ["https://marg.vercel.app"]),
    ],
)
def test_cors_origins_accepts_a_list_a_plain_url_or_a_comma_separated_list(monkeypatch, raw, expected):
    assert settings_with(monkeypatch, raw).cors_origins == expected


def test_a_plain_url_no_longer_stops_the_app_from_starting(monkeypatch):
    # Before, "http://localhost:5173" (no brackets) raised a SettingsError on start.
    assert settings_with(monkeypatch, "http://localhost:5173").cors_origins == ["http://localhost:5173"]


def test_the_jwt_secret_is_still_required(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(Exception):  # noqa: B017 - pydantic's ValidationError
        Settings(_env_file=None)
