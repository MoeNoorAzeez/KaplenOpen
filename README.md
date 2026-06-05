# Kaplen — AI-Powered Curriculum Content Generator

Kaplen is an open-source platform that helps educators produce curriculum-aligned YouTube scripts, long-form video content, study-tip scripts, essays, and podcast outlines — powered by **any LLM**: Anthropic Claude, OpenAI GPT, or any OpenAI-compatible endpoint (Ollama, Together AI, Groq, and more).

## What It Does

| Feature | Description |
|---|---|
| **Curriculum scripts** | 8–20 min YouTube scripts matched to subject/topic/subtopic, with Callaway narrative beats, hooks, and thumbnail prompts |
| **Long-form videos** | 1-hour or 3-hour deep-dive scripts generated section-by-section with real-time streaming |
| **Study tips** | Motivational/study-skill scripts — no curriculum dataset required |
| **Essays** | Chunked source-material ingestion → structured essay with streaming output |
| **Podcast outlines** | Multi-segment show notes and talking points |
| **YouTube analytics** | Per-teacher channel metrics via Google OAuth, stored in Postgres |
| **DOCX export** | Every content type downloadable as a Word document |

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/your-org/kaplen.git
cd kaplen
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set DB_* variables and your LLM key
```

Minimum required:

```env
DB_HOST=localhost
DB_NAME=kaplen
DB_USER=postgres
DB_PASSWORD=yourpassword

LLM_PROVIDER=anthropic           # or: openai
ANTHROPIC_API_KEY=sk-ant-...     # if using Anthropic
# OPENAI_API_KEY=sk-...          # if using OpenAI

SECRET_KEY=change-me-in-production
JWT_SECRET=change-me-in-production
```

### 3. Run

```bash
python app.py
# App starts at http://localhost:5000
# Database tables are created automatically on first boot
```

### 4. Docker (optional)

```bash
docker compose up
```

## Switching LLM Providers

Set `LLM_PROVIDER` and the matching key — **no code changes needed**.

| Provider | `LLM_PROVIDER` | Key variable | Notes |
|---|---|---|---|
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | Default |
| OpenAI GPT | `openai` | `OPENAI_API_KEY` | |
| Ollama (local) | `openai` | `OPENAI_API_KEY=ollama` | Add `LLM_BASE_URL=http://localhost:11434/v1` |
| Together AI | `openai` | `OPENAI_API_KEY=...` | Add `LLM_BASE_URL=https://api.together.xyz/v1` |
| Groq | `openai` | `OPENAI_API_KEY=...` | Add `LLM_BASE_URL=https://api.groq.com/openai/v1` |

Override the model with `LLM_MODEL=model-id`.

## Custom Curriculum

Edit `curricula/registry.json` to register your curriculum. Example entry:

```json
{
  "my-curriculum-2024": {
    "name": "My Curriculum",
    "language": "en",
    "region": "US",
    "structure": {
      "levels": ["subject", "topic", "subtopic"],
      "s3_path_template": "{subject}/{topic}/{subtopic}.json"
    },
    "quality": { "min_word_count": 800 },
    "generation_hints": {
      "tone": "conversational",
      "audience": "high school students"
    }
  }
}
```

See [CURRICULUM_SPEC.md](CURRICULUM_SPEC.md) for the full schema.

## Running Tests

```bash
pip install pytest
pytest
# 24 smoke tests — no live DB, S3, or LLM calls required
```

## API Overview

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | — | Full health check (DB + LLM) |
| GET | `/api/status` | — | Liveness probe |
| POST | `/api/auth/signup` | — | Register |
| POST | `/api/auth/login` | — | Login → JWT |
| GET | `/api/auth/me` | JWT | Current user profile |
| GET | `/api/curricula` | — | List registered curricula |
| POST | `/api/generate` | JWT + subscription | Generate curriculum script |
| POST | `/api/generate-study-tips` | — | Study tips (no auth) |
| POST | `/api/generate-long-form` | JWT | Streaming long-form video |
| POST | `/api/essay/generate` | JWT | Essay from source material |
| POST | `/api/podcast/generate` | JWT | Podcast outline |
| GET | `/api/export/<script_id>` | JWT | Download script as DOCX |
| GET | `/api/analytics/<teacher_id>` | JWT | Improvement metrics |

Complete endpoint reference with request/response schemas: [SPEC.md](SPEC.md).

## Project Structure

```
kaplen/
├── app.py                      # entry point, wiring
├── api_endpoints.py            # all 45 routes
├── config.py                   # env-var config class
├── features/
│   ├── llm_provider.py         # LLM abstraction (Anthropic / OpenAI)
│   ├── auth.py                 # JWT auth helpers + decorators
│   ├── database.py             # Postgres (12 tables, auto-init)
│   ├── script_generator.py     # standard curriculum scripts
│   ├── long_form_generator.py  # 1hr / 3hr streaming generator
│   ├── essay_generator.py      # essay from source material
│   ├── podcast_generator.py    # podcast outlines
│   ├── study_tips.py           # study-tip scripts
│   ├── callaway.py             # narrative direction + beat analysis
│   ├── youtube_packager.py     # hook / title / thumbnail
│   ├── validator.py            # curriculum-coverage scoring
│   ├── payments.py             # Wayl webhook + subscription checks
│   ├── youtube_oauth_manager.py
│   ├── youtube_api_fetcher.py
│   └── ...
├── curricula/
│   └── registry.json
├── static/                     # frontend HTML files
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
├── Dockerfile
├── docker-compose.yml
├── Procfile
└── .env.example
```

## Documentation

| File | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Component diagram, layer model, data flow |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, Heroku, EC2 — full deploy guide |
| [CURRICULUM_SPEC.md](CURRICULUM_SPEC.md) | Curriculum registry JSON schema |
| [SPEC.md](SPEC.md) | Complete API + DB + provider technical spec |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

## License

MIT — see [LICENSE](LICENSE).
