from configparser import ConfigParser
from json import load
from os import getcwd
from os.path import join
from typing import Self

from base_exporter import BaseExporter
from common import Manga
from mangaupdates_client import MangaUpdatesClient, MangaUpdatesOutcomes


class MangaUpdatesExporter(BaseExporter):

    def __init__(self: Self) -> None:
        super().__init__('MangaUpdates')

    @staticmethod
    def _get_entry_id(mappings: dict[str, str], manga: Manga) -> int | None:
        for external_link in manga.external_links:
            if external_link.key == 'mu':
                if external_link.value in mappings:
                    return int(mappings[external_link.value], 36)
                return int(external_link.value, 36)
        return None

    @staticmethod
    def _get_old_ids_mappings() -> dict[str, str]:
        with open('mangaupdates.json', 'rt', encoding='utf-8') as file:
            return load(file)

    def export(self: Self, config: ConfigParser, timestamp: str, mangas: list[Manga]) -> None:
        mappings = self._get_old_ids_mappings()
        cwd = getcwd()
        errors_path = join(cwd, f'mangaupdates-errors_{timestamp}.txt')
        with open(errors_path, 'wt', encoding='utf-8') as errors:
            with MangaUpdatesClient(config) as client:
                count = 0
                total = len(mangas)
                print('[MangaUpdates] Retrieving already tracked entries.')
                tracked_entries = set(client.get_list_entries())
                for manga in mangas:
                    count += 1
                    entry_id = self._get_entry_id(mappings, manga)
                    if entry_id is None:
                        print(f'[MangaUpdates] Entry {count} of {total} failed: the entry does not have a MangaUpdates ID. "{manga.title}" ({manga.id})')
                        errors.write(f'The entry does not have a MangaUpdates ID: {manga.title} ({manga.id}).')
                        continue
                    if entry_id in tracked_entries:
                        print(f'[MangaUpdates] Entry {count} of {total} skipped: the entry is already tracked. "{manga.title}" ({manga.id})')
                        continue
                    outcome = client.add_entry_to_list(entry_id)
                    if outcome == MangaUpdatesOutcomes.SUCCESS:
                        tracked_entries.add(entry_id)
                        print(f'[MangaUpdates] Entry {count} of {total} added. "{manga.title}" ({manga.id})')
                    elif outcome == MangaUpdatesOutcomes.NOT_FOUND:
                        print(f'[MangaUpdates] Entry {count} of {total} failed: the entry does not exist in MangaUpdates. "{manga.title}" ({manga.id})')
                        errors.write(f'The entry does not exist in MangaUpdates: "{manga.title}" ({manga.id}).')
                    elif outcome == MangaUpdatesOutcomes.ALREADY_TRACKED:
                        print(f'[MangaUpdates] Entry {count} of {total} skipped: the entry is already tracked, could this be a duplicate? "{manga.title}" ({manga.id})')
                        errors.write(f'The entry is already tracked, is this an error? "{manga.title}" ({manga.id}).')
                    else:
                        error = RuntimeError('Unexpected outcome.')
                        error.add_note(f'Outcome: {outcome}')
                        raise error
