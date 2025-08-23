# Watch Store (Django)

A clean, modular watch e‑commerce demo for portfolio showcase (SafeCode).

## Stack
- Python 3.11+, Django 5.x
- TailwindCSS (later phases)
- SQLite (dev), Postgres (prod)
- Whitenoise for static files

## Quick Start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Environment
cp .env.example .env  # Windows PowerShell: Copy-Item .env.example .env

# Run (dev)
set DJANGO_SETTINGS_MODULE=config.settings.dev  # macOS/Linux: export ...
python manage.py migrate
python manage.py runserver
