import collections
import contextlib
import enum
import time
import typing

import requests

import common


class MangaUpdatesCredentials(typing.NamedTuple):
    username: str
    password: str


class MangaUpdatesOutcomes(enum.Enum):
    SUCCESS = 1
    NOT_FOUND = 2
    ALREADY_TRACKED = 3


class MangaUpdatesClient(contextlib.AbstractContextManager):

    _credentials: MangaUpdatesCredentials
    _is_authenticated: bool
    _session: requests.Session

    def __enter__(self: typing.Self) -> typing.Self:
        self._session = requests.Session()
        return self

    def __exit__(self, exc_type, exc_value, traceback, /):
        self._session.close()

    def __init__(self: typing.Self, credentials: MangaUpdatesCredentials) -> None:
        self._credentials = credentials
        self._is_authenticated = False

    def _authenticate(self: typing.Self) -> None:
        if self._is_authenticated:
            return
        print('Authenticating in MangaUpdates.')
        request_data = {
            'username': self._credentials.username,
            'password': self._credentials.password
        }
        response = self._session.put('https://api.mangaupdates.com/v1/account/login', json=request_data)
        if response.status_code != 200:
            raise common.get_error(response)
        response_data = response.json()
        if response_data['status'] != 'success':
            raise common.get_error(response)
        self._session.headers['Authorization'] = 'Bearer ' + response_data['context']['session_token']
        self.is_authenticated = True

    def add_entry_to_list(self: typing.Self, id: int) -> MangaUpdatesOutcomes:
        self._authenticate()
        time.sleep(1.1)
        request_data = [
            {
                'series': {
                    'id': id
                },
                'list_id': 0
            }
        ]
        response = self._session.post('https://api.mangaupdates.com/v1/lists/series', json=request_data)
        if response.status_code == 200:
            return MangaUpdatesOutcomes.SUCCESS
        elif response.status_code == 400:
            response_data = response.json()
            error = response_data['context']['errors'][0]['error']
            if error == 'That series does not exist':
                return MangaUpdatesOutcomes.NOT_FOUND
            elif error == 'That series is already on one of your lists.':
                return MangaUpdatesOutcomes.ALREADY_TRACKED
            else:
                raise common.get_error(response)
        else:
            raise common.get_error(response)

    def get_list_entries(self: typing.Self) -> collections.abc.Iterable[int]:
        self._authenticate()
        print('Fetching already tracked entries.')
        page = 1
        size = 100
        while True:
            time.sleep(1.1)
            request_data = {
                'page': page,
                'perpage': size
            }
            response = self._session.post('https://api.mangaupdates.com/v1/lists/0/search', json=request_data)
            if response.status_code != 200:
                raise common.get_error(response)
            response_data = response.json()
            if len(response_data['results']) == 0:
                return
            for result in response_data['results']:
                yield result['record']['series']['id']
            page += 1
