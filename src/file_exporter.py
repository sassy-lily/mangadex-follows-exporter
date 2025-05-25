from abc import ABC
from collections.abc import Generator
from typing import Self

from base_exporter import BaseExporter
from common import Manga


class FileExporter(BaseExporter, ABC):

    def _get_fields(self: Self, manga: Manga) -> Generator[str]:
        alt_title_en = self._get_alternative_title(manga, 'en')
        alt_title_ja_ro = self._get_alternative_title(manga, 'ja')
        alt_title_ja = self._get_alternative_title(manga, 'ja-RO')
        yield manga.id
        yield manga.type
        yield manga.status
        yield manga.title_language
        yield manga.title
        yield alt_title_en
        yield alt_title_ja_ro
        yield alt_title_ja
        yield manga.url

    @staticmethod
    def _get_headers() -> Generator[str]:
        yield 'ID'
        yield 'Type'
        yield 'Status'
        yield 'Main Title Language'
        yield 'Main Title'
        yield 'Alternative Title (EN)'
        yield 'Alternative Title (JA)'
        yield 'Alternative Title (romaji)'
        yield 'URL'
