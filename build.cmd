CALL ".venv/Scripts/activate.bat"
pyinstaller -F application.py
COPY configuration.ini dist
COPY mangaupdates.json dist