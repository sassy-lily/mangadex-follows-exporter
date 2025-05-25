from abc import ABC, abstractmethod
from configparser import ConfigParser
from typing import Self

from common import Manga


class BaseExporter(ABC):

    is_enabled: bool
    name: str

    def __init__(self: Self, name: str) -> None:
        self.is_enabled = False
        self.name = name

    @staticmethod
    def _get_alternative_title(manga: Manga, language: str) -> str:
        for entry in manga.alternative_titles:
            if entry.language == language:
                return entry.title
        return ''

    @staticmethod
    def _query_activation(name: str) -> bool:
        while True:
            value = input(f'Do you want to export to {name}? [y/n] ').strip().lower()
            if value == 'y':
                return True
            if value == 'n':
                return False
            print('Invalid input.')

    @abstractmethod
    def export(self: Self, config: ConfigParser, timestamp: str, mangas: list[Manga]) -> None:
        raise NotImplementedError('This method has not been implemented.')

    def query_activation(self: Self) -> None:
        self.is_enabled = self._query_activation(self.name)
