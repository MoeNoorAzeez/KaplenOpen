# Deployment

## Requirements

| Component | Minimum |
|---|---|
| Python | 3.11 |
| PostgreSQL | 14 |
| RAM | 512 MB |
| Disk | 1 GB |

---

## Environment variables

Copy `.env.example` to `.env` and fill in every value. For production, inject env vars via your platform's secret manager — never commit `.env`.

The two variables that must be set before first boot:

```
DB_HOST=...
ANTHROPIC_API_KEY=...
```

Everything else has a safe default, but you should set `SECRET_KEY`, `JWT_SECRET`, and `S3_BUCKET` for any real deployment.

---

## Database

Kaplen creates all tables automatically on startup via `init_tables()`. No migration tool is required for a fresh install.

**For an existing deployment** — the schema additions (new columns, new tables) use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS`, so running the new code against an existing database is safe.

---

## Option 1 — bare metal / VPS

```bash
# Clone and install
git clone https://github.com/your-org/kaplen.git
cd kaplen
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env && nano .env

# Run (dev)
python app.py

# Run (production) — gunicorn + nginx recommended
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Serve the static HTML files (`dashboard.html`, `essay_generator.html`) from nginx directly to avoid serving them through Flask.

---

## Option 2 — Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

Build and run:

```bash
docker build -t kaplen .
docker run -p 5000:5000 --env-file .env kaplen
```

---

## Option 3 — Railway / Render / Fly.io

All three platforms support Flask apps with a `Procfile`:

```
web: gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

Set environment variables in the platform dashboard (never commit `.env`). Provision a managed PostgreSQL instance and set `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

---

## Production checklist

- [ ] `FLASK_ENV=production` — disables debug mode and detailed error pages
- [ ] `SECRET_KEY` — long random string (not the default)
- [ ] `JWT_SECRET` — long random string (not the default)
- [ ] `DB_PASSWORD` — set; not empty
- [ ] `ANTHROPIC_API_KEY` — valid key
- [ ] `S3_BUCKET` — bucket exists and IAM credentials have `s3:GetObject` / `s3:PutObject`
- [ ] HTTPS — terminate TLS at a load balancer or nginx; Flask should not serve HTTP in production
- [ ] PostgreSQL — run as a managed service (RDS, Supabase, Neon, Railway Postgres); do not run Postgres in the same container as the app
- [ ] Logs — configure a log aggregator; Flask writes to stdout by default
- [ ] `STRIPE_API_KEY` — set if using payments
- [ ] `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_OAUTH_REDIRECT_URI` — set if using YouTube OAuth

---

## YouTube OAuth

The OAuth redirect URI must match exactly what is registered in [Google Cloud Console](https://console.cloud.google.com) under your OAuth 2.0 client. Set `YOUTUBE_OAUTH_REDIRECT_URI` to your production callback URL:

```
https://yourdomain.com/api/youtube/callback
```

---

## Health check

```
GET /api/health
```

Returns `200 OK` with a JSON body when the app is running and can reach the database and Anthropic API. Use this as your load balancer or uptime monitor target.

---

## Scaling

Kaplen is stateless — all session state is in PostgreSQL or JWT tokens. You can run multiple instances behind a load balancer without sticky sessions. The in-memory `scripts_cache` dict in `api_endpoints.py` is session-local and non-critical (DOCX export falls back to the database if the cache misses).
