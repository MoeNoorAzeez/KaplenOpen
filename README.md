<div align="center">

# Kaplen

**Turn written content into video-ready scripts — powered by any LLM**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-blue.svg)](https://postgresql.org)
[![Provider Agnostic](https://img.shields.io/badge/LLM-Anthropic%20%7C%20OpenAI%20%7C%20Ollama-purple.svg)](#switching-llm-providers)

[**Quick Start**](#quick-start) · [**API Reference**](docs/SPEC.md) · [**Architecture**](docs/ARCHITECTURE.md) · [**Deploy**](docs/DEPLOYMENT.md)

</div>

---

Kaplen is an open-source B2B SaaS platform that converts source material — curriculum PDFs, articles, research papers, essays — into structured, spoken-word video scripts. It was built to serve **Iraqi schoolteachers** creating YouTube content from the national curriculum, and later extended to serve **writers and journalists** turning their existing work into video.

The generation pipeline outputs YouTube scripts with timed sections, Callaway narrative beats, thumbnail prompts, titles, and DOCX exports. No LLM lock-in: switch between Anthropic, OpenAI, Ollama, Groq, or Together AI with a single environment variable.

---

## Built as a Research Project

Kaplen was designed from the start as a research instrument, not just a product. The system was built in **32 calendar days** at a total tooling cost of **USD 500** by a single operator with a computer science background who wrote no code directly — all implementation was delegated to Claude through conversational interface across 18 documented sessions and 3,662 operator-model turns.

The completed platform shipped **34 production modules**, passed **99.7% uptime** across the production period, and was validated commercially — one customer reached letter-of-intent stage before sales were paused for the research period.

This build is the subject of a practitioner study:

> **"Engineering Without Coding: A Practitioner Study of Operator-Driven AI Development"**
> MohamadAlmstafa Azeez — Independent Researcher, Baghdad, Iraq (2026)
>
> The paper documents four failure modes that appear consistently when an LLM is used as a sole implementation agent (configuration blindness, fragmentation, accumulation without consolidation, scope creep), the compensating behaviors the operator developed in response, and evidence that software engineering competence and coding ability functioned as separable skills in this case.

**Build stats at a glance:**

| Metric | Value |
|---|---|
| Calendar days to production | 32 |
| Total tooling cost | USD 500 |
| Estimated traditional equivalent | USD 150,000–280,000 |
| Cost compression ratio | ~300× |
| Documented modules | 34 |
| Operator-model turns | 3,662 |
| System uptime | 99.7% |

### Production metrics

The first video produced using a Kaplen-generated script, thumbnail, and title achieved:

| Metric | Result | Benchmark |
|---|---|---|
| Average View Duration (AVD) | **60%** | 50% = strong for educational content |
| Click-Through Rate (CTR) | **7%** | 2–3% = YouTube platform average |

The platform processed **200 curriculum textbooks** across **3 grade levels, 18 subjects, 108 topics, and 432 subtopics**. Unit economics validated at **USD 67/teacher/month**, billing at the educational center level (7–20 teachers per center) at **USD 469–1,340/center/month**.

Full write-up: [OVERVIEW.md](OVERVIEW.md)

---

## What Kaplen Does

### For educators
Upload a curriculum PDF. Select a subject, topic, and subtopic. Get a complete Arabic-language YouTube script — hook, timed sections, Callaway beats, thumbnail prompt, and YouTube metadata — ready to record.

### For writers and journalists
Paste an article or research piece. Select a video duration (10, 15, or 25 minutes) and style (Explainer / Commentary / Analysis / Personal Take). Get a spoken-word script that converts your written argument into a format that earns watch-time on YouTube.

### For developers
A clean Flask API with a provider-agnostic LLM abstraction, 12 Postgres tables (auto-created on first boot), 45 documented endpoints, SSE streaming for long-form generation, and a curriculum registry you can extend for any subject hierarchy.

---

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- An API key for your chosen LLM provider (or [Ollama](https://ollama.ai) running locally)

### 1 — Clone and install

```bash
git clone https://github.com/your-org/kaplen.git
cd kaplen
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Configure

```bash
cp .env.example .env
```

Open `.env` and fill in the minimum required values:

```env
# Database
DB_HOST=localhost
DB_NAME=kaplen
DB_USER=postgres
DB_PASSWORD=yourpassword

# LLM — pick one provider
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# App secrets
SECRET_KEY=change-me-in-production
JWT_SECRET=change-me-in-production
```

### 3 — Run

```bash
python app.py
```

The server starts at **http://localhost:5000**. All 12 database tables are created automatically on first boot — no migrations to run.

### 4 — Verify

```bash
curl http://localhost:5000/api/health
# → {"status": "ok", "db": "connected", "llm": "connected"}
```

### Docker (optional)

```bash
docker compose up
```

---

## Switching LLM Providers

Set `LLM_PROVIDER` and the matching key in `.env`. **No code changes.**

| Provider | `LLM_PROVIDER` | Key variable | Extra |
|---|---|---|---|
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | Default |
| OpenAI GPT | `openai` | `OPENAI_API_KEY` | |
| Ollama (local) | `openai` | `OPENAI_API_KEY=ollama` | `LLM_BASE_URL=http://localhost:11434/v1` |
| Together AI | `openai` | `OPENAI_API_KEY=<key>` | `LLM_BASE_URL=https://api.together.xyz/v1` |
| Groq | `openai` | `OPENAI_API_KEY=<key>` | `LLM_BASE_URL=https://api.groq.com/openai/v1` |

Override the model name with `LLM_MODEL=model-id`.

---

## API

The API is JWT-authenticated. Register an account, log in, and pass the token as `Authorization: Bearer <token>`.

### Core endpoints

```
GET  /api/health                     → system health (DB + LLM)
POST /api/auth/signup                → register
POST /api/auth/login                 → login → JWT
GET  /api/auth/me                    → current user

GET  /api/curricula                  → list available curricula
POST /api/generate            [JWT]  → generate curriculum script (SSE)
POST /api/generate-long-form  [JWT]  → 1hr/3hr deep-dive script (SSE)
POST /api/essay/generate      [JWT]  → article → YouTube script (SSE)
POST /api/podcast/generate    [JWT]  → podcast outline

GET  /api/export/<script_id>  [JWT]  → download as DOCX
GET  /api/analytics/<id>      [JWT]  → channel improvement metrics
```

**Generate a script** (example):

```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "curriculum_id": "iraqi-moe-2024",
    "subject": "physics",
    "topic": "mechanics",
    "subtopic": "newtons-laws",
    "duration": 10
  }'
```

**Convert an article to a YouTube script**:

```bash
curl -X POST http://localhost:5000/api/essay/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_text": "your article or research content here...",
    "essay_type": "youtube_15",
    "style": "explainer",
    "audience": "general"
  }'
```

Full schema for every endpoint, request body, and response: [docs/SPEC.md](docs/SPEC.md)

---

## Curriculum Registry

Register any subject hierarchy by editing `curricula/registry.json`:

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
    "quality": {
      "min_word_count": 800
    },
    "generation_hints": {
      "tone": "conversational",
      "audience": "high school students"
    }
  }
}
```

The platform ships with the Iraqi Ministry of Education curriculum pre-registered. Full schema and validation rules: [docs/SPEC.md § Curriculum Registry](docs/SPEC.md).

---

## Project Structure

```
kaplen/
├── app.py                       # entry point and route wiring
├── api_endpoints.py             # all 45 routes
├── config.py                    # env-var config
│
├── features/
│   ├── llm_provider.py          # provider abstraction (Anthropic / OpenAI-compat)
│   ├── auth.py                  # JWT helpers and decorators
│   ├── database.py              # Postgres — 12 tables, auto-init on boot
│   ├── script_generator.py      # curriculum script pipeline
│   ├── long_form_generator.py   # 1hr / 3hr streaming generator
│   ├── essay_generator.py       # article → YouTube script
│   ├── podcast_generator.py     # podcast outlines
│   ├── study_tips.py            # motivational / study-skill scripts
│   ├── callaway.py              # narrative beats and direction
│   ├── youtube_packager.py      # hook / title / thumbnail prompts
│   ├── validator.py             # curriculum coverage scoring
│   ├── payments.py              # Stripe subscription checks
│   ├── analytics.py             # per-teacher metrics
│   ├── dedup.py                 # dual-hash deduplication
│   └── ...
│
├── curricula/
│   └── registry.json            # curriculum definitions
│
├── dashboard.html               # teacher dashboard UI
├── essay_generator.html         # Script Studio UI
├── tests/
│   ├── conftest.py
│   └── test_smoke.py            # 24 tests — no live DB/LLM required
│
├── Dockerfile
├── docker-compose.yml
├── Procfile                     # Heroku
└── .env.example
```

---

## Tests

```bash
pip install pytest
pytest
# 24 smoke tests — all pass without a live DB, S3, or LLM
```

---

## Deployment

| Target | Guide |
|---|---|
| Local | This README |
| Docker Compose | [docs/DEPLOYMENT.md § Docker](docs/DEPLOYMENT.md) |
| Heroku | [docs/DEPLOYMENT.md § Heroku](docs/DEPLOYMENT.md) |
| AWS EC2 + Nginx + RDS | [docs/DEPLOYMENT.md § EC2](docs/DEPLOYMENT.md) |

The production system runs on EC2 t3.small with PostgreSQL on RDS, S3 for curriculum storage, and Nginx as a reverse proxy. Nginx configuration for SSE (streaming) responses is included in the deploy guide.

---

## Documentation

| File | What's in it |
|---|---|
| [OVERVIEW.md](OVERVIEW.md) | Platform overview — education, script studio, research background |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layer diagram, all 34 modules, LLM abstraction, DB schema |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Full deploy guides — local, Docker, Heroku, EC2 |
| [docs/SPEC.md](docs/SPEC.md) | Every endpoint, every DB table, SSE protocol, error codes |

---

## Contributing

Pull requests are welcome. For significant changes, open an issue first.

To add a new LLM provider, implement the `LLMProvider` interface in `features/llm_provider.py`:

```python
class MyProvider(LLMProvider):
    def complete(self, prompt: str, **kwargs) -> str: ...
    def stream_complete(self, prompt: str, on_token: Callable[[str], None], **kwargs) -> str: ...
```

Register it in `config.py` and set `LLM_PROVIDER=myprovider` in `.env`.

---

## License

MIT — see [LICENSE](LICENSE).
