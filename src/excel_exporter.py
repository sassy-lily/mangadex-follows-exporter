from configparser import ConfigParser
from os import getcwd
from os.path import join
from typing import Self

from openpyxl import Workbook

from common import Manga
from file_exporter import FileExporter


class ExcelFileExporter(FileExporter):

    def __init__(self: Self) -> None:
        super().__init__('Excel')

    def export(self: Self, config: ConfigParser, timestamp: str, mangas: list[Manga]) -> None:
        cwd = getcwd()
        output_path = join(cwd, f'follows_{timestamp}.xlsx')
        print(f'Writing to {output_path}.')
        workbook = Workbook()
        workbook.active.append(list(self._get_headers()))
        for manga in mangas:
            workbook.active.append(list(self._get_fields(manga)))
        workbook.save(output_path)
        workbook.close()
