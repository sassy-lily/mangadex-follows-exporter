from __future__ import annotations

from urllib.parse import parse_qsl

import httpx
import pytest

from conftest import FakeClock, mock_client
from exporter.auth import PasswordFlow, TokenManager
from exporter.errors import AuthError


def _grant(request: httpx.Request) -> str:
    return dict(parse_qsl(request.content.decode()))["grant_type"]


@pytest.mark.usefixtures("mangadex_env")
def test_proactive_refresh_before_expiry(auth_config):
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        grant = _grant(request)
        grants.append(grant)
        token = "AT1" if grant == "password" else "AT2"
        refresh = "RT1" if grant == "password" else "RT2"
        return httpx.Response(
            200,
            json={"access_token": token, "refresh_token": refresh, "expires_in": 900},
        )

    clock = FakeClock()
    flow = PasswordFlow(auth_config, mock_client(handler))
    manager = TokenManager(flow, clock=clock)

    assert manager.token() == "AT1"  # initial password grant
    assert manager.token() == "AT1"  # cached, no new request
    clock.advance(900)  # past expiry (margin 30 -> threshold 870)
    assert manager.token() == "AT2"  # refreshed
    assert grants == ["password", "refresh_token"]


@pytest.mark.usefixtures("mangadex_env")
def test_invalidate_uses_refresh_token(auth_config):
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        grant = _grant(request)
        grants.append(grant)
        return httpx.Response(
            200,
            json={
                "access_token": f"AT-{len(grants)}",
                "refresh_token": "RT",
                "expires_in": 900,
            },
        )

    flow = PasswordFlow(auth_config, mock_client(handler))
    manager = TokenManager(flow, clock=FakeClock())
    assert manager.token() == "AT-1"
    assert manager.invalidate() == "AT-2"
    assert grants == ["password", "refresh_token"]


@pytest.mark.usefixtures("mangadex_env")
def test_refresh_rejected_falls_back_to_password(auth_config):
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        grant = _grant(request)
        grants.append(grant)
        if grant == "refresh_token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200,
            json={"access_token": "AT", "refresh_token": "RT", "expires_in": 900},
        )

    clock = FakeClock()
    flow = PasswordFlow(auth_config, mock_client(handler))
    manager = TokenManager(flow, clock=clock)
    manager.token()
    clock.advance(1000)
    assert manager.token() == "AT"  # refresh failed -> new password grant
    assert grants == ["password", "refresh_token", "password"]


@pytest.mark.usefixtures("mangadex_env")
def test_token_endpoint_error_raises(auth_config):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    flow = PasswordFlow(auth_config, mock_client(handler))
    manager = TokenManager(flow, clock=FakeClock())
    with pytest.raises(AuthError):
        manager.token()
