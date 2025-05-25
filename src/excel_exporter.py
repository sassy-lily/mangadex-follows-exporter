import typing

import openpyxl

import base_exporter
import common


class ExcelFileExporter(base_exporter.BaseExporter):

    _path: str

    def __init__(self: typing.Self, path: str) -> None:
        self._path = path

    def export(self: typing.Self, mangas: list[common.Manga]) -> None:
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(['ID', 'Type', 'Status', 'Main Title Language', 'Main Title', 'Alternative Title (EN)', 'Alternative Title (JA)', 'Alternative Title (romaji)', 'URL'])
        for manga in mangas:
            alt_title_en = self._get_alternative_title(manga, 'en')
            alt_title_ja_ro = self._get_alternative_title(manga, 'ja')
            alt_title_ja = self._get_alternative_title(manga, 'ja-RO')
            worksheet.append([manga.id, manga.type, manga.status, manga.title_language, manga.title, alt_title_en, alt_title_ja_ro, alt_title_ja, manga.url])
        workbook.save(self._path)
        workbook.close()
