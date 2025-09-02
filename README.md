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


# Watch Store

A clean, modular **watch e-commerce demo** built with **Django + Bulma**.  
This project is designed as a **portfolio showcase** (SafeCode).

---

## 🚀 Features
- Django 5 + modular apps (`catalog`, `orders`, `accounts`, `customers`)
- Custom User model with email authentication
- Product catalog with categories, brands, collections, variants, images
- Shopping cart + order management
- Bulma 1.x CSS framework with **custom SCSS overrides** for a luxury/modern look
- SCSS build pipeline using **Dart Sass**
- Production-ready config (Whitenoise, .env, collectstatic)

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/Fiesdazraf/watch-store.git
cd watch-store
