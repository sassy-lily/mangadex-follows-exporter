import configparser
import time
import traceback

import clients.mangadex
import clients.mangaupdates
import common
import exporters.csv_file
import exporters.excel_file
import exporters.mangaupdates

import os

def run() -> None:
    print('Starting process.')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read('configuration.ini', 'utf-8')
    mangadex_username = parser.get('mangadex', 'username')
    mangadex_password = parser.get('mangadex', 'password')
    mangadex_client_id = parser.get('mangadex', 'client_id')
    mangadex_client_secret = parser.get('mangadex', 'client_secret')
    mangadex_credentials = clients.mangadex.MangaDexCredentials(mangadex_username, mangadex_password, mangadex_client_id, mangadex_client_secret)
    mangaupdates_username = parser.get('mangaupdates', 'username')
    mangaupdates_password = parser.get('mangaupdates', 'password')
    mangaupdates_credentials = clients.mangaupdates.MangaUpdatesCredentials(mangaupdates_username, mangaupdates_password)
    export_to_csv = _get_switch('Do you want to export to CSV? [y/n] ', 'export_to_csv', False)
    export_to_excel = _get_switch('Do you want to export to Excel? [y/n] ', 'export_to_excel', False)
    export_to_mangaupdates = _get_switch('Do you want to export to MangaUpdates? [y/n] ', 'export_to_mangaupdates', False)
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    print(f"export_to_csv: {export_to_csv}, export_to_excel: {export_to_excel}, export_to_mangaupdates: {export_to_mangaupdates}")
    print('Exporting entries from MangaDex.')
    with clients.mangadex.MangaDexClient(mangadex_credentials) as mangadex:
        print('Fetching statuses.')
        statuses = mangadex.get_statuses()
        mangas = list[common.Manga]()
        count = 0
        count_total = len(statuses)
        print(f'{count_total} entries founds.')
        print('Fetching entries.')
        for status in statuses:
            count += 1
            manga = mangadex.get_manga(status)
            mangas.append(manga)
            print(f'[MangaDex] Fetched {count} of {count_total}: {manga.title}')
    os.makedirs('output', exist_ok=True)
    if export_to_csv:
        print('Saving entries to CSV.')
        output_path = f'output/follows_{timestamp}.csv'
        with exporters.csv_file.CsvFileExporter(output_path) as exporter:
            exporter.export(mangas)
    if export_to_excel:
        print('Saving entries to Excel.')
        output_path = f'output/follows_{timestamp}.xlsx'
        with exporters.excel_file.ExcelFileExporter(output_path) as exporter:
            exporter.export(mangas)
    if export_to_mangaupdates:
        print('Saving entries to MangaUpdates.')
        errors_path = f'output/mangaupdates-errors_{timestamp}.txt'
        with exporters.mangaupdates.MangaUpdatesExporter(mangaupdates_credentials, 'mangaupdates.json', errors_path) as exporter:
            exporter.export(mangas)
    print('Process completed.')

def _get_switch(prompt: str, env_var: str, default: bool = False) -> bool:
    value = os.getenv(env_var)
    if value is not None:
        return value.strip().lower() == 'y'
    # if Env not set: ask user
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
    print("Done, you can now close the app.")
