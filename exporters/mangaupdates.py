import json
import types
import typing

import requests

import clients.mangaupdates
import common
import exporters.base


class MangaUpdatesExporter(exporters.base.BaseExporter):

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

    def export(self: typing.Self, mangas: list[common.Manga]) -> None:
        with open(self._errors_path, 'wt', encoding='utf-8') as errors:
            with clients.mangaupdates.MangaUpdatesClient(self._credentials) as client:
                count = 0
                count_total = len(mangas)
                tracked_entries = set(client.get_list_entries())
                for manga in mangas:
                    count += 1
                    id = self._get_id(manga)
                    if id is None:
                        print(f'[MangaUpdates] Entry {count} of {count_total} failed: the entry does not have a MangaUpdates ID. "{manga.title}" ({manga.id})')
                        errors.write(f'The entry does not have a MangaUpdates ID: {manga.title} ({manga.id}).')
                        continue
                    if id in tracked_entries:
                        print(f'[MangaUpdates] Entry {count} of {count_total} skipped: the entry is already tracked. "{manga.title}" ({manga.id})')
                        continue
                    outcome = client.add_entry_to_list(id)
                    if outcome == clients.mangaupdates.MangaUpdatesOutcomes.SUCCESS:
                        tracked_entries.add(id)
                        print(f'[MangaUpdates] Entry {count} of {count_total} added. "{manga.title}" ({manga.id})')
                    elif outcome == clients.mangaupdates.MangaUpdatesOutcomes.NOT_FOUND:
                        print(f'[MangaUpdates] Entry {count} of {count_total} failed: the entry does not exist in MangaUpdates. "{manga.title}" ({manga.id})')
                        errors.write(f'The entry does not exist in MangaUpdates: "{manga.title}" ({manga.id}).')
                    elif outcome == clients.mangaupdates.MangaUpdatesOutcomes.ALREADY_TRACKED:
                        print(f'[MangaUpdates] Entry {count} of {count_total} skipped: the entry is already tracked, could this be a duplicate?. "{manga.title}" ({manga.id})')
                        errors.write(f'The entry is already tracked, is this an error? "{manga.title}" ({manga.id}).')
                    else:
                        error = RuntimeError('Unexpected outcome.')
                        error.add_note(f'Outcome: {outcome}')
                        raise error
