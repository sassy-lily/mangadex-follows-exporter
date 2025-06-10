from configparser import ConfigParser
from locale import LC_ALL, setlocale
from os import getcwd
from os.path import join
from time import strftime
from traceback import format_exc

from base_exporter import BaseExporter
from common import Manga
from csv_exporter import CsvFileExporter
from excel_exporter import ExcelFileExporter
from mangadex_client import MangaDexClient
from mangaupdates_exporter import MangaUpdatesExporter


def export() -> None:
    print('Starting process.')
    cwd = getcwd()
    config_path = join(cwd, 'configuration.ini')
    timestamp = strftime("%Y-%m-%d_%H-%M-%S")
    print(f'Loading configuration from "{config_path}".')
    config = ConfigParser(interpolation=None)
    config.read(config_path, 'utf-8')
    exporters: list[BaseExporter] = [CsvFileExporter(), ExcelFileExporter(), MangaUpdatesExporter()]
    for exporter in exporters:
        exporter.query_activation()
    print('Fetching data from MangaDex.')
    with MangaDexClient(config) as mangadex:
        print('Fetching statuses.')
        statuses = list(mangadex.get_statuses())
        mangas: list[Manga] = []
        count = 0
        total = len(statuses)
        print('Fetching entries.')
        for status in statuses:
            count += 1
            manga = mangadex.get_manga(status)
            mangas.append(manga)
            print(f'[MangaDex] Fetched {count} of {total}: {manga.title} ({manga.id})')
    print('Exporting entries.')
    for exporter in exporters:
        if exporter.is_enabled:
            print(f'Exporting to {exporter.name}.')
            exporter.export(config, timestamp, mangas)
    print('Process completed.')


def _main() -> None:
    setlocale(LC_ALL, '')
    try:
        export()
    except KeyboardInterrupt:
        print('The script execution has been interrupted.')
    except Exception:
        details = format_exc()
        print('An error occurred executing the script.')
        print(details)
    input('Press [enter] to exit.')


if __name__ == '__main__':
    _main()
