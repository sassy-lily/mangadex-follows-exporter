from collections import abc
from configparser import ConfigParser
from time import sleep, time
from types import TracebackType
from typing import Any, Self

from requests import Session

from base_client import BaseClient
from common import AlternativeTitle, ExternalLink, Manga, Status


class MangaDexClient(BaseClient):

    _authentication_expires_at: float
    _client_id: str
    _client_secret: str
    _password: str
    _session: Session | None
    _username: str

    def __enter__(self: Self) -> Self:
        self._session = Session()
        return self

    def __exit__(self: Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> bool | None:
        self._session.close()

    def __init__(self: Self, config: ConfigParser) -> None:
        self._authentication_expires_at = 0
        self._client_id = config.get('mangadex', 'client_id')
        self._client_secret = config.get('mangadex', 'client_secret')
        self._password = config.get('mangadex', 'password')
        self._session = None
        self._username = config.get('mangadex', 'username')

    def _authorize(self: Self) -> None:
        if self._authentication_expires_at > time():
            return
        sleep(0.5)
        request_data = {
            'grant_type': 'password',
            'username': self._username,
            'password': self._password,
            'client_id': self._client_id,
            'client_secret': self._client_secret
        }
        response = self._session.post('https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token', request_data)
        if response.status_code != 200:
            raise self._get_error(response)
        response_data = response.json()
        access_token = response_data['access_token']
        expires_in = response_data['expires_in']
        token_type = response_data['token_type']
        self._authentication_expires_at = time() + int(expires_in) / 2
        self._session.headers['Authorization'] = token_type + ' ' + access_token

    @staticmethod
    def _get_alternative_titles(data: Any) -> abc.Generator[AlternativeTitle]:
        if 'altTitles' not in data['data']['attributes'] or data['data']['attributes']['altTitles'] is None:
            return
        for entry in data['data']['attributes']['altTitles']:
            language = next(iter(entry))
            title = entry[language]
            yield AlternativeTitle(language, title)

    @staticmethod
    def _get_external_links(data: Any) -> abc.Generator[ExternalLink]:
        if 'links' not in data['data']['attributes'] or data['data']['attributes']['links'] is None:
            return
        for key, value in data['data']['attributes']['links'].items():
            yield ExternalLink(key, value)

    def get_manga(self: Self, status: Status) -> Manga:
        self._authorize()
        sleep(0.5)
        response = self._session.get(f'https://api.mangadex.org/manga/{status.id}')
        if response.status_code != 200:
            raise self._get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise self._get_error(response)
        entry_id = data['data']['id']
        entry_type = data['data']['type']
        title_language = next(iter(data['data']['attributes']['title']))
        title = data['data']['attributes']['title'][title_language]
        alternative_titles = list(self._get_alternative_titles(data))
        external_links = list(self._get_external_links(data))
        url = 'https://mangadex.org/title/' + data['data']['id']
        return Manga(entry_id, entry_type, title_language, title, status.status, alternative_titles, external_links, url)

    def get_statuses(self: Self) -> list[Status]:
        self._authorize()
        sleep(0.5)
        response = self._session.get('https://api.mangadex.org/manga/status')
        if response.status_code != 200:
            raise self._get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise self._get_error(response)
        statuses = list[Status]()
        for key, value in data['statuses'].items():
            status = Status(key, value)
            statuses.append(status)
        return statuses
