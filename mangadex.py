import collections.abc
import configparser
import csv
import time
import typing

import requests


class EntryStatus(typing.NamedTuple):
    entry_id: str
    reading_status: str


class Entry(typing.NamedTuple):
    id: str
    type: str
    status: str
    title_language: str
    title: str
    alt_title_en: str
    alt_title_ja_ro: str
    alt_title_ja: str
    url: str


def export(username: str, password: str, client_id: str, client_secret: str) -> None:
    print('Starting.')
    session = requests.Session()
    authorization_expires_at = _authorize(session, username, password, client_id, client_secret)
    file = open('titles.csv', 'wt', encoding='utf-8', newline='')
    writer = csv.writer(file)
    writer.writerow(('ID', 'Type', 'Status', 'Main Title Language', 'Main Title', 'Alternative English Title', 'Alternative Romaji title', 'Alternative Japanese title', 'URL'))
    for entry_status in list(_get_statuses(session)):
        if authorization_expires_at < time.time():
            authorization_expires_at = _authorize(session, username, password, client_id, client_secret)
        entry = _get_entry(session, entry_status)
        writer.writerow((entry.id, entry.type, entry.status, entry.title_language, entry.title, entry.alt_title_en, entry.alt_title_ja_ro, entry.alt_title_ja, entry.url))
    file.close()
    session.close()
    print('Completed.')


def _authorize(session: requests.Session, username: str, password: str, client_id: str, client_secret: str) -> float:
    print('Authenticating.')
    response = session.post('https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token', {
        'grant_type': 'password',
        'username': username,
        'password': password,
        'client_id': client_id,
        'client_secret': client_secret
    })
    if response.status_code != 200:
        raise _get_error(response)
    data = response.json()
    expires_in = time.time() + (int(data['expires_in']) / 2)
    session.headers['Authorization'] = f'{data['token_type']} {data['access_token']}'
    response.close()
    return expires_in


def _get_alternative_title(data: typing.Any, language: str) -> str:
    for alt_title in data['data']['attributes']['altTitles']:
        if language in alt_title:
            return alt_title[language]
    return ''


def _get_error(response: requests.Response) -> RuntimeError:
    error = RuntimeError('Request failed.')
    error.add_note(f'URL: {response.request.url}')
    error.add_note(f'Status: {response.status_code}')
    error.add_note(f'Content: {response.content}')
    return error


def _get_entry(session: requests.Session, entry_status: EntryStatus) -> Entry:
    print(f'Retrieving entry {entry_status.entry_id}.')
    response = session.get(f'https://api.mangadex.org/manga/{entry_status.entry_id}')
    if response.status_code != 200:
        raise _get_error(response)
    data = response.json()
    if data['result'] != 'ok':
        raise _get_error(response)
    id = data['data']['id']
    type = data['data']['type']
    title_language = next(iter(data['data']['attributes']['title']))
    title = data['data']['attributes']['title'][title_language]
    alt_title_en = _get_alternative_title(data, 'en')
    alt_title_ja_ro = _get_alternative_title(data, 'ja-ro')
    alt_title_ja = _get_alternative_title(data, 'ja')
    url = 'https://mangadex.org/title/' + data['data']['id']
    response.close()
    return Entry(id, type, entry_status.reading_status, title_language, title, alt_title_en, alt_title_ja_ro, alt_title_ja, url)


def _get_statuses(session: requests.Session) -> collections.abc.Generator[EntryStatus]:
    print('Fetching statuses.')
    response = session.get('https://api.mangadex.org/manga/status')
    if response.status_code != 200:
        raise _get_error(response)
    data = response.json()
    if data['result'] != 'ok':
        raise _get_error(response)
    for entry_id, reading_status in data['statuses'].items():
        yield EntryStatus(entry_id, reading_status)
    response.close()


def _main() -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read('configuration.ini', 'utf-8')
    username = parser.get('mangadex', 'username')
    password = parser.get('mangadex', 'password')
    client_id = parser.get('mangadex', 'client_id')
    client_secret = parser.get('mangadex', 'client_secret')
    export(username, password, client_id, client_secret)


if __name__ == '__main__':
    _main()
