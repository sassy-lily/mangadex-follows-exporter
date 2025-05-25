CALL ".venv\Scripts\activate.bat"
pyinstaller -F src\mangadex_follows_exporter.py
COPY configuration.ini dist
COPY mangaupdates.json dist