from collections import abc
from configparser import ConfigParser
from enum import Enum
from time import sleep
from typing import Self

from requests import Session

from base_client import BaseClient


class MangaUpdatesOutcomes(Enum):
    SUCCESS = 1
    NOT_FOUND = 2
    ALREADY_TRACKED = 3


class MangaUpdatesClient(BaseClient):

    _is_authenticated: bool
    _password: str
    _session: Session | None
    _username: str

    def __enter__(self: Self) -> Self:
        self._session = Session()
        return self

    def __exit__(self, exc_type, exc_value, traceback, /):
        self._session.close()

    def __init__(self: Self, config: ConfigParser) -> None:
        self._is_authenticated = False
        self._password = config.get('mangaupdates', 'password')
        self._session = None
        self._username = config.get('mangaupdates', 'username')

    def _authenticate(self: Self) -> None:
        if self._is_authenticated:
            return
        sleep(1.1)
        request_data = {
            'username': self._username,
            'password': self._password
        }
        response = self._session.put('https://api.mangaupdates.com/v1/account/login', json=request_data)
        if response.status_code != 200:
            raise self._get_error(response)
        response_data = response.json()
        if response_data['status'] != 'success':
            raise self._get_error(response)
        self._session.headers['Authorization'] = 'Bearer ' + response_data['context']['session_token']
        self._is_authenticated = True

    def add_entry_to_list(self: Self, entry_id: int) -> MangaUpdatesOutcomes:
        self._authenticate()
        sleep(1.1)
        request_data = [
            {
                'series': {
                    'id': entry_id
                },
                'list_id': 0
            }
        ]
        response = self._session.post('https://api.mangaupdates.com/v1/lists/series', json=request_data)
        if response.status_code == 200:
            return MangaUpdatesOutcomes.SUCCESS
        if response.status_code == 400:
            response_data = response.json()
            error = response_data['context']['errors'][0]['error']
            if error == 'That series does not exist':
                return MangaUpdatesOutcomes.NOT_FOUND
            if error == 'That series is already on one of your lists.':
                return MangaUpdatesOutcomes.ALREADY_TRACKED
            raise self._get_error(response)
        raise self._get_error(response)

    def get_list_entries(self: Self) -> abc.Iterable[int]:
        self._authenticate()
        page = 1
        size = 100
        while True:
            sleep(1.1)
            request_data = {
                'page': page,
                'perpage': size
            }
            response = self._session.post('https://api.mangaupdates.com/v1/lists/0/search', json=request_data)
            if response.status_code != 200:
                raise self._get_error(response)
            response_data = response.json()
            if len(response_data['results']) == 0:
                return
            for result in response_data['results']:
                yield result['record']['series']['id']
            page += 1
