import configparser
import time
import traceback

import csv_exporter
import excel_exporter
import mangadex_client
import mangaupdates_exporter


def run() -> None:
    print('Starting process.')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read('configuration.ini', 'utf-8')
    mangadex_username = parser.get('mangadex', 'username')
    mangadex_password = parser.get('mangadex', 'password')
    mangadex_client_id = parser.get('mangadex', 'client_id')
    mangadex_client_secret = parser.get('mangadex', 'client_secret')
    mangadex_credentials = mangadex_client.MangaDexCredentials(mangadex_username, mangadex_password, mangadex_client_id, mangadex_client_secret)
    mangaupdates_username = parser.get('mangaupdates', 'username')
    mangaupdates_password = parser.get('mangaupdates', 'password')
    mangaupdates_credentials = mangaupdates_exporter.MangaUpdatesCredentials(mangaupdates_username, mangaupdates_password)
    export_to_csv = _get_switch('Do you want to export to CSV? [y/n] ')
    export_to_excel = _get_switch('Do you want to export to Excel? [y/n] ')
    export_to_mangaupdates = _get_switch('Do you want to export to MangaUpdates? [y/n] ')
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    with mangadex_client.MangaDexClient(mangadex_credentials) as mangadex:
        mangas = list(mangadex.get_follows())
    if export_to_csv:
        output_path = f'follows_{timestamp}.csv'
        with csv_exporter.CsvExporter(output_path) as exporter:
            exporter.export(mangas)
    if export_to_excel:
        output_path = f'follows_{timestamp}.xlsx'
        with excel_exporter.ExcelExporter(output_path) as exporter:
            exporter.export(mangas)
    if export_to_mangaupdates:
        errors_path = f'mangaupdates-errors_{timestamp}.txt'
        with mangaupdates_exporter.MangaUpdatesExporter(mangaupdates_credentials, 'mangaupdates.json', errors_path) as exporter:
            exporter.export(mangas)
    print('Process completed.')


def _get_switch(prompt: str) -> bool:
    while True:
        value = input(prompt).strip().lower()
        if value == 'y':
            return True
        elif value == 'n':
            return False
        else:
            print('Invalid input.')


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('The script execution has been interrupted.')
    except Exception:
        details = traceback.format_exc()
        print('An error occurred executing the script.')
        print(details)
    input('Press [enter] to exit.')
