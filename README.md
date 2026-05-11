# API

FastAPI service with CRUD for items, optional PostgreSQL (via Docker Compose), SQLite fallback for local dev, and pytest + GitHub Actions CI.

## Requirements

- **Python** 3.12 or newer  
- **pip**  
- **Docker Desktop** (optional, for Compose / container runs)  
- **Git**

## Clone and enter the project

```bash
cd path/to/API
```

Paths below assume the project root contains `pyproject.toml`, `src/`, and `dockerfile`.

---

## Local setup (no Docker)

### 1. Create and activate a virtual environment

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install the application (editable install)

```bash
pip install --upgrade pip
pip install -e .
```

### 3. Environment variables

Create a `.env` in the project root if you need a database URL (optional for local SQLite).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLAlchemy URL. If unset, the app defaults to SQLite file `api.sqlite` in the current working directory. |

**PostgreSQL example** (passwords with `@` must be URL-encoded as `%40`):

```env
DATABASE_URL=postgresql://user:pass%401234@host:5432/items
```

### 4. Run the API

From the project root, with `src` on the import path:

```bash
uvicorn app.main:app --reload --app-dir src
```

The server listens at `http://127.0.0.1:8000` by default.

### 5. Quick checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/items
```

Open interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 6. Stop the server

Press `Ctrl+C` in the terminal where `uvicorn` is running.

---

## Run with Docker Compose (API + PostgreSQL)

From the project root:

```bash
docker compose up --build -d
```

Check containers:

```bash
docker compose ps
```

Test:

```bash
curl http://127.0.0.1:8000/health
```

View logs:

```bash
docker compose logs -f api
```

Stop and remove containers:

```bash
docker compose down
```

Remove containers **and** the Postgres data volume:

```bash
docker compose down -v
```

Ensure `DATABASE_URL` in `docker-compose.yml` matches your Postgres user/password/database, and **encode special characters** in the password for the URL.

---

## Run with Docker only (single container, no Compose)

Build:

```bash
docker build -f dockerfile -t api-local:latest .
```

Run (API only; set `DATABASE_URL` if you use an external database):

```bash
docker run --rm -p 8000:8000 api-local:latest
```

Test:

```bash
curl http://127.0.0.1:8000/health
```

---

## Development: tests, lint, types

Install dev tools as needed:

```bash
pip install pytest pytest-cov httpx ruff mypy
```

**Tests with coverage**

```bash
pytest --cov=src/app --cov-report=term-missing
```

**Ruff**

```bash
ruff check .
```

**Mypy**

```bash
mypy .
```

---

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml` — runs Ruff, Mypy, pytest with coverage, and a Docker build on pushes and pull requests.

---

## Troubleshooting

- **`curl` connection refused on port 8000** — Uvicorn is not running, or another process is using the port.
- **`could not translate host name "1234@db"`** — `DATABASE_URL` is malformed; usually an unescaped `@` in the password. Use `%40` instead of `@` in the URL.
- **PowerShell JSON with `curl.exe`** — Prefer `Invoke-RestMethod` or build the JSON in a variable; see FastAPI docs for examples.
