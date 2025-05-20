import collections
import contextlib
import time
import types
import typing

import requests

import common


class MangaDexCredentials(typing.NamedTuple):
    user: str
    password: str
    client_id: str
    client_secret: str


class MangaDexClient(contextlib.AbstractContextManager):

    _authentication_expires_at: float | None
    _credentials: MangaDexCredentials | None
    _session: requests.Session | None

    def __enter__(self: typing.Self) -> typing.Self:
        self._session = requests.Session()
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        self.close()

    def __init__(self: typing.Self, credentials: MangaDexCredentials) -> None:
        self._authentication_expires_at = None
        self._credentials = credentials

    def _authorize(self: typing.Self) -> None:
        if self._authentication_expires_at is not None and self._authentication_expires_at > time.time():
            return
        print('Authenticating in MangaDex.')
        request_data = {
            'grant_type': 'password',
            'username': self._credentials.user,
            'password': self._credentials.password,
            'client_id': self._credentials.client_id,
            'client_secret': self._credentials.client_secret
        }
        response = self._session.post('https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token', request_data)
        if response.status_code != 200:
            raise common._get_error(response)
        response_data = response.json()
        access_token = response_data['access_token']
        expires_in = response_data['expires_in']
        token_type = response_data['token_type']
        self._authentication_expires_at = time.time() + int(expires_in) / 2
        self._session.headers['Authorization'] = token_type + ' ' + access_token

    def _get_alternative_titles(self: typing.Self, data: typing.Any) -> collections.abc.Generator[common.AlternativeTitle]:
        if 'altTitles' not in data['data']['attributes'] or data['data']['attributes']['altTitles'] is None:
            return
        for entry in data['data']['attributes']['altTitles']:
            language = next(iter(entry))
            title = entry[language]
            yield common.AlternativeTitle(language, title)

    def _get_external_links(self: typing.Self, data: typing.Any) -> collections.abc.Generator[common.ExternalLink]:
        if 'links' not in data['data']['attributes'] or data['data']['attributes']['links'] is None:
            return
        for key, value in data['data']['attributes']['links'].items():
            yield common.ExternalLink(key, value)

    def _get_manga(self: typing.Self, status: common.Status) -> common.Manga:
        self._authorize()
        response = self._session.get(f'https://api.mangadex.org/manga/{status.id}')
        if response.status_code != 200:
            raise common._get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise common._get_error(response)
        id = data['data']['id']
        type = data['data']['type']
        title_language = next(iter(data['data']['attributes']['title']))
        title = data['data']['attributes']['title'][title_language]
        alternative_titles = list(self._get_alternative_titles(data))
        external_links = list(self._get_external_links(data))
        url = 'https://mangadex.org/title/' + data['data']['id']
        print('Fetched entry "' + title + '".')
        return common.Manga(id, type, title_language, title, status.status, alternative_titles, external_links, url)

    def _get_statuses(self: typing.Self) -> collections.abc.Generator[common.Status]:
        self._authorize()
        print('Fetching statuses list.')
        response = self._session.get('https://api.mangadex.org/manga/status')
        if response.status_code != 200:
            raise common._get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise common._get_error(response)
        for id, status in data['statuses'].items():
            yield common.Status(id, status)

    def close(self: typing.Self) -> None:
        self._session.close()

    def get_follows(self: typing.Self) -> collections.abc.Generator[common.Manga]:
        for status in list(self._get_statuses()):
            yield self._get_manga(status)
