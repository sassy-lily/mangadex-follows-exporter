import collections
import json
import types
import typing

import requests

import base
import clients.mangaupdates
import common


class MangaUpdatesExporter(base.BaseExporter):

    _credentials: clients.mangaupdates.MangaUpdatesCredentials
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

    def __init__(self: typing.Self, credentials: clients.mangaupdates.MangaUpdatesCredentials, mappings_path: str, errors_path: str) -> None:
        self._credentials = credentials
        self._errors_path = errors_path
        self._mappings_path = mappings_path

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
        with open(self._errors_path, 'wt', encoding='utf-8') as errors:
            with clients.mangaupdates.MangaUpdatesClient(self._credentials) as client:
                already_tracked_entries = set(client.get_list_entries())
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
                    outcome = client.add_entry_to_list(id)
                    if outcome == clients.mangaupdates.MangaUpdatesOutcomes.SUCCESS:
                        already_tracked_entries.add(id)
                        print('"' + manga.title + '" has been added.')
                    elif outcome == clients.mangaupdates.MangaUpdatesOutcomes.NOT_FOUND:
                        print('"' + manga.title + '" (' + manga.id + ') has NOT be added, it does not exist in MangaUpdates.')
                        errors.write('"' + manga.title + '" (' + manga.id + ') has not been added, it does not exist in MangaUpdates. Check ' + manga.url + '\n')
                        errors.flush()
                    elif outcome == clients.mangaupdates.MangaUpdatesOutcomes.ALREADY_TRACKED:
                        print('"' + manga.title + '" is already tracked?')
                    else:
                        error = RuntimeError('Unexpected outcome.')
                        error.add_note(f'Outcome: {outcome}')
                        raise error
        print('Export completed.')
