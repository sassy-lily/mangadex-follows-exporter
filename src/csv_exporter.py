from configparser import ConfigParser
from csv import writer
from os import getcwd
from os.path import join
from typing import Self

from common import Manga
from file_exporter import FileExporter


class CsvFileExporter(FileExporter):

    def __init__(self: Self) -> None:
        super().__init__('CSV')

    def export(self: Self, config: ConfigParser, timestamp: str, mangas: list[Manga]) -> None:
        cwd = getcwd()
        output_path = join(cwd, f'follows_{timestamp}.csv')
        print(f'Writing to {output_path}.')
        with open(output_path, 'wt', encoding='utf-8', newline='') as output_file:
            output_writer = writer(output_file)
            output_writer.writerow(self._get_headers())
            for manga in mangas:
                output_writer.writerow(self._get_fields(manga))
