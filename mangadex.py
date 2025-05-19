import abc
import collections.abc
import configparser
import contextlib
import csv
import io
import json
import time
import traceback
import types
import typing

import requests


class Status(typing.NamedTuple):
    id: str
    status: str


class AlternativeTitle(typing.NamedTuple):
    language: str
    title: str


class ExternalLink(typing.NamedTuple):
    key: str
    value: str


class Manga(typing.NamedTuple):
    id: str
    type: str
    title_language: str
    title: str
    status: str
    alternative_titles: list[AlternativeTitle]
    external_links: list[ExternalLink]
    url: str


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
            raise _get_error(response)
        response_data = response.json()
        access_token = response_data['access_token']
        expires_in = response_data['expires_in']
        token_type = response_data['token_type']
        self._authentication_expires_at = time.time() + int(expires_in) / 2
        self._session.headers['Authorization'] = token_type + ' ' + access_token

    def _get_alternative_titles(self: typing.Self, data: typing.Any) -> collections.abc.Generator[AlternativeTitle]:
        if 'altTitles' not in data['data']['attributes'] or data['data']['attributes']['altTitles'] is None:
            return
        for entry in data['data']['attributes']['altTitles']:
            language = next(iter(entry))
            title = entry[language]
            yield AlternativeTitle(language, title)

    def _get_external_links(self: typing.Self, data: typing.Any) -> collections.abc.Generator[ExternalLink]:
        if 'links' not in data['data']['attributes'] or data['data']['attributes']['links'] is None:
            return
        for key, value in data['data']['attributes']['links'].items():
            yield ExternalLink(key, value)

    def _get_manga(self: typing.Self, status: Status) -> Manga:
        self._authorize()
        response = self._session.get(f'https://api.mangadex.org/manga/{status.id}')
        if response.status_code != 200:
            raise _get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise _get_error(response)
        id = data['data']['id']
        type = data['data']['type']
        title_language = next(iter(data['data']['attributes']['title']))
        title = data['data']['attributes']['title'][title_language]
        alternative_titles = list(self._get_alternative_titles(data))
        external_links = list(self._get_external_links(data))
        url = 'https://mangadex.org/title/' + data['data']['id']
        print('Fetched entry "' + title + '".')
        return Manga(id, type, title_language, title, status.status, alternative_titles, external_links, url)

    def _get_statuses(self: typing.Self) -> collections.abc.Generator[Status]:
        self._authorize()
        print('Fetching statuses list.')
        response = self._session.get('https://api.mangadex.org/manga/status')
        if response.status_code != 200:
            raise _get_error(response)
        data = response.json()
        if data['result'] != 'ok':
            raise _get_error(response)
        for id, status in data['statuses'].items():
            yield Status(id, status)

    def close(self: typing.Self) -> None:
        self._session.close()

    def get_follows(self: typing.Self) -> collections.abc.Generator[Manga]:
        for status in list(self._get_statuses()):
            yield self._get_manga(status)


class Exporter(contextlib.AbstractContextManager):

    def __enter__(self: typing.Self) -> typing.Self:
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        pass

    @abc.abstractmethod
    def export(self: typing.Self, mangas: collections.abc.Iterable[Manga]) -> None:
        raise NotImplementedError('This method has not been implemented.')


class CsvExporter(Exporter):

    _file: io.TextIOWrapper
    _name: str

    def __enter__(self: typing.Self) -> typing.Self:
        self._file = open(self._name, 'wt', encoding='utf-8', newline='')
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        self._file.close()

    def __init__(self: typing.Self, name: str):
        self._name = name

    def _get_alternative_title(self: typing.Self, manga: Manga, language: str) -> str:
        for entry in manga.alternative_titles:
            if entry.language == language:
                return entry.title
        return ''

    def export(self: typing.Self, mangas: collections.abc.Iterable[Manga]) -> None:
        print('Writing output file.')
        writer = csv.writer(self._file)
        writer.writerow(['ID', 'Type', 'Status', 'Main Title Language', 'Main Title', 'Alternative Title (EN)', 'Alternative Title (JA)', 'Alternative Title (romaji)', 'URL'])
        for manga in mangas:
            alt_title_en = self._get_alternative_title(manga, 'en')
            alt_title_ja_ro = self._get_alternative_title(manga, 'ja')
            alt_title_ja = self._get_alternative_title(manga, 'ja-RO')
            writer.writerow([manga.id, manga.type, manga.status, manga.title_language, manga.title, alt_title_en, alt_title_ja_ro, alt_title_ja, manga.url])


class MangaUpdatesCredentials(typing.NamedTuple):
    username: str
    password: str


class MangaUpdatesExporter(Exporter):

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
            raise _get_error(response)
        response_data = response.json()
        if response_data['status'] != 'success':
            raise _get_error(response)
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
                raise _get_error(response)
            response_data = response.json()
            if len(response_data['results']) == 0:
                return
            for result in response_data['results']:
                yield result['record']['series']['id']
            page += 1

    def _get_id(self: typing.Self, manga: Manga) -> int | None:
        for external_link in manga.external_links:
            if external_link.key == 'mu':
                if external_link.value in self._mappings:
                    return int(self._mappings[external_link.value], 36)
                return int(external_link.value, 36)
        return None

    def close(self: typing.Self) -> None:
        self._session.close()

    def export(self: typing.Self, mangas: collections.abc.Iterable[Manga]) -> None:
        print('Importing in MangaUpdates.')
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
                    else:
                        raise _get_error(response)
                elif response.status_code != 200:
                    raise _get_error(response)
                already_tracked_entries.add(id)
                print('"' + manga.title + '" has been added.')
        print('MangaUpdates import completed.')


def _get_error(response: requests.Response) -> RuntimeError:
    error = RuntimeError('Request failed.')
    error.add_note(f'URL: {response.request.url}')
    error.add_note(f'Status: {response.status_code}')
    error.add_note(f'Content: {response.content}')
    return error


def run() -> None:
    print('Starting export.')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read('configuration.ini', 'utf-8')
    mangadex_username = parser.get('mangadex', 'username')
    mangadex_password = parser.get('mangadex', 'password')
    mangadex_client_id = parser.get('mangadex', 'client_id')
    mangadex_client_secret = parser.get('mangadex', 'client_secret')
    mangadex_credentials = MangaDexCredentials(mangadex_username, mangadex_password, mangadex_client_id, mangadex_client_secret)
    mangaupdates_username = parser.get('mangaupdates', 'username')
    mangaupdates_password = parser.get('mangaupdates', 'password')
    mangaupdates_credentials = MangaUpdatesCredentials(mangaupdates_username, mangaupdates_password)
    with MangaDexClient(mangadex_credentials) as mangadex:
        with MangaUpdatesExporter(mangaupdates_credentials, 'mangaupdates.json', 'mangaupdates-errors.txt') as exporter:
            mangas = list(mangadex.get_follows())
            exporter.export(mangas)
    print('Export completed.')


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('The script execution has been interrupted.')
    except Exception:
        details = traceback.format_exc()
        print('An error occurred executing the script.')
        print(details)
    input('Press [enter] to exit.')
