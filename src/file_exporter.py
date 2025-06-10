from abc import ABC
from collections.abc import Generator
from typing import Self

from base_exporter import BaseExporter
from common import Entry


class FileExporter(BaseExporter, ABC):

    def _get_fields(self: Self, entry: Entry) -> Generator[str]:
        yield entry.manga.id
        yield entry.manga.type
        yield entry.manga.status
        yield entry.manga.title_language
        yield entry.manga.title
        yield self._get_alternative_title(entry.manga, 'en')
        yield self._get_alternative_title(entry.manga, 'ja')
        yield self._get_alternative_title(entry.manga, 'ja-RO')
        yield str(entry.rating)
        yield str(entry.personal_rating)
        yield entry.manga.url

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
        yield 'Rating'
        yield 'Personal Rating'
        yield 'URL'
