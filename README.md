# PTIT Lab Progress (Flask)

A Flask application for managing lab progress and commitments using Flask + SQLite.

## Prerequisites

- Python 3.10+
- Windows / Linux / Mac

## Installation

1. Clone the repository.
2. Create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # Linux / Mac
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running locally (demo)

### 1. Set required environment variables

**Windows (PowerShell):**
```powershell
$env:SECRET_KEY    = (python -c "import secrets; print(secrets.token_hex(32))")
$env:ADMIN_USERNAME = "myadmin"
$env:ADMIN_PASSWORD = "ChangeMe!2024"
```

**Linux / Mac:**
```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export ADMIN_USERNAME="myadmin"
export ADMIN_PASSWORD="ChangeMe!2024"
```

### 2. Initialize the database

```
flask db upgrade
```

### 3. Create the first admin account

```
python seed_admin.py
```

Output:
```
Admin created: "myadmin"
```

### 4. Start the app

```
python app.py
```

Access at http://127.0.0.1:5000/ and log in with the credentials you chose above.

### Enable debug mode (optional, local dev only)

```powershell
$env:FLASK_DEBUG = "1"
python app.py
```

> ⚠️ Never run with `FLASK_DEBUG=1` in production.

## Configuration reference

| Variable        | Required | Description                                      |
|-----------------|----------|--------------------------------------------------|
| `SECRET_KEY`    | ✅ Yes   | Flask session signing key (generate fresh each time) |
| `ADMIN_USERNAME`| For seed | Username for the first admin account             |
| `ADMIN_PASSWORD`| For seed | Password for the first admin account             |
| `FLASK_DEBUG`   | No       | Set to `1` to enable debug mode (default: off)   |

## Project Structure

- `app.py` — Main application
- `models.py` — Database models
- `config.py` — Configuration (reads from environment)
- `seed_admin.py` — One-time admin creation helper
- `templates/` — HTML templates
- `static/` — CSS, JS
- `migrations/` — Database migration scripts

### Local generated folders (Not tracked in Git)
- `.venv/` — Python virtual environment
- `instance/` — SQLite database file (created automatically)
- `uploads/` — Uploaded attachments (created automatically)
- `__pycache__/` — Python bytecode cache