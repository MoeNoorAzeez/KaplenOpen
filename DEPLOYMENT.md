# Deployment

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Python | 3.10 | 3.11+ |
| PostgreSQL | 13 | 16 |
| AWS S3 | — | — (required for curriculum data) |
| RAM | 512 MB | 1 GB+ |
| CPU | 1 vCPU | 2+ vCPU |

## Environment Variables

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

### Required

```env
# Database
DB_HOST=localhost
DB_NAME=kaplen
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_PORT=5432

# Flask
SECRET_KEY=<random-64-char-string>
JWT_SECRET=<random-64-char-string>

# LLM (pick one block)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OR:
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Optional

```env
# AWS S3 (needed for curriculum data loader)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
S3_BUCKET=your-curriculum-bucket

# LLM overrides
LLM_MODEL=claude-sonnet-4-6    # override model
LLM_BASE_URL=                  # OpenAI-compatible endpoint

# Curriculum
CURRICULUM_REGISTRY_PATH=curricula/registry.json
DEFAULT_CURRICULUM_ID=iraqi-moe-2024

# Payments (Wayl)
WAYL_MERCHANT_TOKEN=
WAYL_WEBHOOK_SECRET=
WAYL_WEBHOOK_URL=

# YouTube OAuth
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_OAUTH_REDIRECT_URI=https://yourdomain.com/api/teacher/youtube/oauth-callback

# Application
DOMAIN=yourdomain.com
TIMEZONE=UTC
FRONTEND_PATH=./static
FLASK_ENV=production
```

Generate strong secrets:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Option 1: Local / Development

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env

python app.py
# http://localhost:5000
```

## Option 2: Docker Compose (recommended for evaluation)

```bash
cp .env.example .env
# edit .env — at minimum set LLM_PROVIDER and the matching API key

docker compose up --build
# http://localhost:5000
```

The `docker-compose.yml` starts:
- `postgres:16-alpine` on port 5432 (data in named volume `pgdata`)
- `kaplen` app on port 5000, waits for Postgres health check

Stop and remove:
```bash
docker compose down        # keep data
docker compose down -v     # also remove database volume
```

## Option 3: Heroku

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:mini
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
heroku config:set JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
heroku config:set LLM_PROVIDER=anthropic
heroku config:set ANTHROPIC_API_KEY=sk-ant-...
heroku config:set FLASK_ENV=production
heroku config:set DOMAIN=your-app-name.herokuapp.com
git push heroku main
heroku open
```

Heroku reads `DATABASE_URL` automatically from the Postgres add-on. Kaplen checks `DATABASE_URL` first, then falls back to individual `DB_*` vars.

## Option 4: AWS EC2

### 1. Launch Instance

- AMI: Amazon Linux 2023 or Ubuntu 22.04
- Instance type: t3.small (minimum), t3.medium (recommended)
- Security group: inbound 22 (SSH), 80 (HTTP), 443 (HTTPS)

### 2. Install Dependencies

```bash
# Amazon Linux 2023
sudo dnf install -y python3.11 python3.11-pip postgresql16-server nginx git

# Ubuntu 22.04
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql nginx git
```

### 3. Set Up Postgres

```bash
sudo postgresql-setup --initdb   # Amazon Linux
sudo systemctl enable --now postgresql

sudo -u postgres psql -c "CREATE DATABASE kaplen;"
sudo -u postgres psql -c "CREATE USER kaplen WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kaplen TO kaplen;"
```

### 4. Deploy App

```bash
cd /opt
sudo git clone https://github.com/your-org/kaplen.git
cd kaplen
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn

sudo cp .env.example .env
sudo nano .env   # fill in all values
```

### 5. Systemd Service

```ini
# /etc/systemd/system/kaplen.service
[Unit]
Description=Kaplen
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/opt/kaplen
EnvironmentFile=/opt/kaplen/.env
ExecStart=/opt/kaplen/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 120 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kaplen
```

### 6. Nginx Reverse Proxy

```nginx
# /etc/nginx/conf.d/kaplen.conf
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;   # long-form generation can take time
        proxy_buffering off;       # required for SSE streaming
    }
}
```

```bash
sudo systemctl reload nginx
```

### 7. TLS (Let's Encrypt)

```bash
sudo dnf install -y certbot python3-certbot-nginx   # Amazon Linux
sudo certbot --nginx -d yourdomain.com
```

## Database Migrations

Kaplen uses backward-compatible `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations run automatically on startup. There is no migration framework — new columns are added idempotently.

For destructive changes (dropping columns, renaming tables) you must write and run manual SQL before deploying the new code.

## Health Checks

```bash
curl https://yourdomain.com/api/status   # liveness — no external calls
curl https://yourdomain.com/api/health   # full check: DB + LLM API
```

Response shapes:
```json
// /api/status — always fast
{"status": "ok", "timestamp": "2026-06-05T10:00:00Z"}

// /api/health
{
  "status": "healthy",
  "database": {"status": "healthy", "message": "Connected"},
  "llm_api":  {"status": "healthy", "message": "LLM API connected (claude-sonnet-4-6)"},
  "timestamp": "2026-06-05T10:00:00Z"
}
```

## YouTube OAuth Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials (type: Web application)
4. Add your redirect URI: `https://yourdomain.com/api/teacher/youtube/oauth-callback`
5. Set in `.env`:
   ```env
   YOUTUBE_CLIENT_ID=...
   YOUTUBE_CLIENT_SECRET=...
   YOUTUBE_OAUTH_REDIRECT_URI=https://yourdomain.com/api/teacher/youtube/oauth-callback
   ```

## S3 Curriculum Data

Curriculum content files live in S3. The path template in `registry.json` determines the key format. For example, with template `{subject}/{topic}/{subtopic}.json`:

```
s3://your-bucket/mathematics/algebra/linear-equations.json
```

Each file contains the raw curriculum content (learning objectives, key concepts, examples) that the script generator uses as context.

IAM permissions required:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
  "Resource": ["arn:aws:s3:::your-bucket", "arn:aws:s3:::your-bucket/*"]
}
```

## Production Checklist

- [ ] `SECRET_KEY` and `JWT_SECRET` are long random strings (not defaults)
- [ ] `FLASK_ENV=production`
- [ ] `.env` is not committed to version control
- [ ] PostgreSQL accepts connections only from the app server
- [ ] TLS certificate is installed and auto-renewing
- [ ] `proxy_buffering off` in Nginx (required for SSE streaming)
- [ ] `proxy_read_timeout 300s` (long-form generation needs extra time)
- [ ] Health check endpoint monitored by uptime service
- [ ] Database backups configured (pg_dump cron or RDS automated backups)
