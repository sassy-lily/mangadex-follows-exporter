"""MangaDex OAuth2 token management (Resource Owner Password Credentials).

MangaDex authenticates against a Keycloak server that is *separate from the API
host* and *not* described in the OpenAPI spec. We cache the short-lived
(~15 min) access token in memory and refresh it automatically — proactively
before expiry and reactively on a 401 — using the refresh-token grant, falling
back to a fresh password grant if the refresh token is missing or rejected.

``OAuth2Flow`` is the extension point: ROPC is implemented as ``PasswordFlow``;
other grants (client-credentials, authorization-code) can be added as new
``OAuth2Flow`` subclasses without touching ``TokenManager``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from .config import AuthConfig, resolve_secret
from .errors import AuthError

# Refresh this many seconds before the token actually expires, to avoid racing
# the boundary on a slow request.
_EXPIRY_MARGIN = 30.0


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: float


class OAuth2Flow(ABC):
    """Strategy for obtaining and renewing tokens from a token endpoint."""

    def __init__(self, token_url: str, http: httpx.Client) -> None:
        self._token_url = token_url
        self._http = http

    @abstractmethod
    def authenticate(self) -> TokenSet:
        """Perform the initial grant from scratch."""

    @abstractmethod
    def refresh(self, refresh_token: str) -> TokenSet:
        """Renew using a refresh token (may raise ``AuthError``)."""

    def _post(self, data: dict[str, str]) -> TokenSet:
        try:
            response = self._http.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise AuthError(f"token request failed: {exc}") from exc
        if response.status_code != 200:
            # Never include the response body — it may echo credentials.
            raise AuthError(
                f"token endpoint returned HTTP {response.status_code} "
                f"for grant_type={data.get('grant_type')!r}"
            )
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise AuthError("token response did not include an access_token")
        return TokenSet(
            access_token=access_token,
            refresh_token=payload.get("refresh_token"),
            expires_in=float(payload.get("expires_in", 900)),
        )


class PasswordFlow(OAuth2Flow):
    """ROPC: ``grant_type=password`` then ``grant_type=refresh_token``."""

    def __init__(self, auth: AuthConfig, http: httpx.Client) -> None:
        super().__init__(auth.token_url, http)
        # Resolve secrets once, up front, so a missing env var fails fast.
        self._username = resolve_secret(auth.username_env)
        self._password = resolve_secret(auth.password_env)
        self._client_id = resolve_secret(auth.client_id_env)
        self._client_secret = resolve_secret(auth.client_secret_env)

    def authenticate(self) -> TokenSet:
        return self._post(
            {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._post(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )


class TokenManager:
    """Caches an access token and renews it transparently."""

    def __init__(self, flow: OAuth2Flow, *, clock: object = time.monotonic) -> None:
        self._flow = flow
        self._clock = clock  # callable returning a monotonic float
        self._tokens: TokenSet | None = None
        self._expires_at = 0.0

    @classmethod
    def from_config(
        cls, auth: AuthConfig, *, http: httpx.Client | None = None
    ) -> TokenManager:
        client = http or httpx.Client(timeout=30.0)
        return cls(PasswordFlow(auth, client))

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    def _store(self, tokens: TokenSet) -> None:
        self._tokens = tokens
        self._expires_at = self._now() + tokens.expires_in - _EXPIRY_MARGIN

    def token(self) -> str:
        """Return a valid access token, authenticating/refreshing as needed."""
        if self._tokens is None:
            self._store(self._flow.authenticate())
        elif self._now() >= self._expires_at:
            self._store(self._renew())
        assert self._tokens is not None
        return self._tokens.access_token

    def invalidate(self) -> str:
        """Force a renewal (used after a 401) and return the new token."""
        self._store(self._renew())
        assert self._tokens is not None
        return self._tokens.access_token

    def _renew(self) -> TokenSet:
        refresh_token = self._tokens.refresh_token if self._tokens else None
        if refresh_token:
            try:
                return self._flow.refresh(refresh_token)
            except AuthError:
                # Refresh token missing/rejected -> fall back to a full grant.
                pass
        return self._flow.authenticate()
