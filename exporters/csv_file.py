import collections
import csv
import io
import types
import typing

import exporters.base
import common


class CsvFileExporter(exporters.base.BaseExporter):

    _file: io.TextIOWrapper
    _name: str

    def __enter__(self: typing.Self) -> typing.Self:
        self._file = open(self._name, 'wt', encoding='utf-8', newline='')
        return self

    def __exit__(self: typing.Self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> bool | None:
        self._file.close()

    def __init__(self: typing.Self, name: str):
        self._name = name

    def export(self: typing.Self, mangas: collections.abc.Iterable[common.Manga]) -> None:
        print('Exporting to CSV.')
        writer = csv.writer(self._file)
        writer.writerow(['ID', 'Type', 'Status', 'Main Title Language', 'Main Title', 'Alternative Title (EN)', 'Alternative Title (JA)', 'Alternative Title (romaji)', 'URL'])
        for manga in mangas:
            alt_title_en = self._get_alternative_title(manga, 'en')
            alt_title_ja_ro = self._get_alternative_title(manga, 'ja')
            alt_title_ja = self._get_alternative_title(manga, 'ja-RO')
            writer.writerow([manga.id, manga.type, manga.status, manga.title_language, manga.title, alt_title_en, alt_title_ja_ro, alt_title_ja, manga.url])
        print('Export completed.')
