# Kaplen

**Open-source AI content generation platform.** Plug in a curriculum registry, get structured video scripts, essays, podcasts, and study guides — powered by Claude and packaged for YouTube.

---

## What it does

Kaplen takes a JSON curriculum definition and generates:

- **Short-form scripts** — 10–15 min YouTube videos with hooks, titles, thumbnails
- **Long-form scripts** — multi-phase deep-dives (40–60 min)
- **Essays** — structured academic or explainer essays
- **Podcasts** — two-host dialogue scripts
- **Study tips** — meta-learning / technique videos

Every piece of content is curriculum-aware: quality rules, required concepts, and language instructions all come from the registry — no hardcoded domain knowledge in the code.

---

## Quick start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- AWS S3 bucket
- [Anthropic API key](https://console.anthropic.com)

### Install

```bash
git clone https://github.com/your-org/kaplen.git
cd kaplen
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env with your real values
```

### Run

```bash
python app.py
# → http://localhost:5000
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python) |
| Database | PostgreSQL (psycopg2) |
| Storage | Amazon S3 |
| AI | Anthropic Claude (claude-sonnet-4-6) |
| Auth | JWT |
| Payments | Stripe |
| YouTube | Google OAuth2 + Data API v3 |

---

## Project layout

```
kaplen/
├── app.py                      # Application factory
├── config.py                   # Environment-driven config
├── api_endpoints.py            # All route handlers
├── curricula/
│   └── registry.json           # Curriculum definitions
├── features/
│   ├── database.py             # Schema + table init
│   ├── auth.py                 # JWT auth
│   ├── curriculum_loader.py    # Registry + S3 content loader
│   ├── script_generator.py     # Short-form generation
│   ├── long_form_generator.py  # Long-form generation
│   ├── essay_generator.py      # Essay generation
│   ├── podcast_generator.py    # Podcast generation
│   ├── study_tips.py           # Study tips generation
│   ├── validator.py            # Curriculum coverage check
│   ├── youtube_packager.py     # Hook / title / thumbnail
│   ├── youtube_oauth_manager.py# Per-creator OAuth2
│   ├── docx_export.py          # Word document export
│   ├── payments.py             # Stripe webhooks
│   └── synthesis.py            # Streaming transcript analysis
├── .env.example
└── requirements.txt
```

---

## Adding a curriculum

No code changes needed. Add a JSON entry to `curricula/registry.json` and upload content files to S3:

```json
{
  "id": "my-curriculum",
  "name": "My Curriculum",
  "levels": ["grade", "subject", "unit", "lesson"],
  "path_template": "content/{grade}/{subject}/{unit}/{lesson}.json",
  "s3_bucket_env": "S3_BUCKET"
}
```

Then pass `curriculum_id=my-curriculum` to `/api/generate`. See [CURRICULUM_SPEC.md](CURRICULUM_SPEC.md) for the full schema.

---

## Documentation

| File | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and data flow |
| [CURRICULUM_SPEC.md](CURRICULUM_SPEC.md) | Registry JSON schema |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Production deployment guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

---

## License

MIT
