import collections
import json
import time
import types
import typing

import requests

import exporter
import common


class MangaUpdatesCredentials(typing.NamedTuple):
    username: str
    password: str


class MangaUpdatesExporter(exporter.Exporter):

    _credentials: MangaUpdatesCredentials
    _errors_path: str
    _mappings: dict[str, str]
    _mappings_path: str
    _session: requests.Session

    def __enter__(self: typing.Self) -> typing.Self:
        with open(self._mappings_path, 'rt', encoding='utf-8') as file:
            self._mappings = json.load(file)
        self._session = requests.Session()
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        self.close()

    def __init__(self: typing.Self, credentials: MangaUpdatesCredentials, mappings_path: str, errors_path: str) -> None:
        self._credentials = credentials
        self._errors_path = errors_path
        self._mappings_path = mappings_path

    def _authenticate(self: typing.Self) -> None:
        print('Authenticating in MangaUpdates.')
        request_data = {
            'username': self._credentials.username,
            'password': self._credentials.password
        }
        response = self._session.put('https://api.mangaupdates.com/v1/account/login', json=request_data)
        if response.status_code != 200:
            raise common._get_error(response)
        response_data = response.json()
        if response_data['status'] != 'success':
            raise common._get_error(response)
        self._session.headers['Authorization'] = 'Bearer ' + response_data['context']['session_token']

    def _fetch_already_tracked_entries(self: typing.Self) -> collections.abc.Iterable[int]:
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
                raise common._get_error(response)
            response_data = response.json()
            if len(response_data['results']) == 0:
                return
            for result in response_data['results']:
                yield result['record']['series']['id']
            page += 1

    def _get_id(self: typing.Self, manga: common.Manga) -> int | None:
        for external_link in manga.external_links:
            if external_link.key == 'mu':
                if external_link.value in self._mappings:
                    return int(self._mappings[external_link.value], 36)
                return int(external_link.value, 36)
        return None

    def close(self: typing.Self) -> None:
        self._session.close()

    def export(self: typing.Self, mangas: collections.abc.Iterable[common.Manga]) -> None:
        print('Exporting to MangaUpdates.')
        self._authenticate()
        already_tracked_entries = set(self._fetch_already_tracked_entries())
        with open(self._errors_path, 'wt', encoding='utf-8') as errors:
            for manga in mangas:
                id = self._get_id(manga)
                if id is None:
                    print('"' + manga.title + '" (' + manga.id + ') has NOT be added, its ID is not available in MangaDex.')
                    errors.write('"' + manga.title + '" (' + manga.id + ') has not been added, its ID is not available in MangaDex. Check ' + manga.url + '\n')
                    errors.flush()
                    continue
                if id in already_tracked_entries:
                    print('"' + manga.title + '" is already tracked.')
                    continue
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
                if response.status_code == 400:
                    response_data = response.json()
                    reason = response_data['context']['errors'][0]['error']
                    if reason == 'That series does not exist':
                        print('"' + manga.title + '" (' + manga.id + ') has NOT be added, it does not exist in MangaUpdates.')
                        errors.write('"' + manga.title + '" (' + manga.id + ') has not been added, it does not exist in MangaUpdates. Check ' + manga.url + '\n')
                        errors.flush()
                        continue
                    elif reason == 'That series is already on one of your lists.':
                        print('"' + manga.title + '" is already tracked?')
                        continue
                    else:
                        raise common._get_error(response)
                elif response.status_code != 200:
                    raise common._get_error(response)
                already_tracked_entries.add(id)
                print('"' + manga.title + '" has been added.')
        print('Export completed.')
