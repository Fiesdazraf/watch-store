@echo off
set DJANGO_SETTINGS_MODULE=config.settings.test
python -m pytest -v --create-db
pause
