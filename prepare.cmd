git reset --hard
git clean -d -f -x
python -m venv .venv
CALL ".venv/Scripts/activate.bat"
python -m pip install -r requirements.txt