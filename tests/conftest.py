"""Shared test fixtures and helpers (no live network anywhere)."""

from __future__ import annotations

import httpx
import pytest

from exporter.config import ApiConfig, AuthConfig
from exporter.ratelimit import RateLimiter


class FakeClock:
    """Deterministic monotonic clock for token-expiry / pacing tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeTokens:
    """Stand-in for TokenManager that never hits the network."""

    def __init__(self) -> None:
        self.invalidated = 0

    def token(self) -> str:
        if not self.invalidated:
            return "TEST-TOKEN"
        return f"TEST-TOKEN-{self.invalidated}"

    def invalidate(self) -> str:
        self.invalidated += 1
        return self.token()


def mock_client(handler) -> httpx.Client:
    """An httpx.Client whose requests are served by ``handler``."""
    return httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )


def fast_limiter() -> RateLimiter:
    return RateLimiter(rate=100000)


def noop_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
def mangadex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGADEX_USERNAME", "user")
    monkeypatch.setenv("MANGADEX_PASSWORD", "pass")
    monkeypatch.setenv("MANGADEX_CLIENT_ID", "personal-client-abc")
    monkeypatch.setenv("MANGADEX_CLIENT_SECRET", "secret")


@pytest.fixture
def mangaupdates_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGAUPDATES_USERNAME", "mu-user")
    monkeypatch.setenv("MANGAUPDATES_PASSWORD", "mu-pass")


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig()


@pytest.fixture
def api_config() -> ApiConfig:
    return ApiConfig(base_url="http://testserver", max_retries=3, backoff_factor=0.0)
