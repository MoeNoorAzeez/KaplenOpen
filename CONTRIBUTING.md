# Contributing

Contributions are welcome. This document explains how to get set up, what areas need help, and how pull requests are reviewed.

---

## Getting started

```bash
git clone https://github.com/your-org/kaplen.git
cd kaplen
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in at minimum DB_HOST and ANTHROPIC_API_KEY
python app.py
```

---

## Areas that need help

### 1. Curriculum registries
The highest-impact contribution is adding real curriculum data for new domains. No Python needed — just a JSON entry in `curricula/registry.json` and content files uploaded to S3.

Examples of useful new curricula:
- UK A-Level subjects
- Egyptian Thanaweya Amma
- SAT / ACT prep
- Any university-level course

See [CURRICULUM_SPEC.md](CURRICULUM_SPEC.md) for the full schema.

### 2. Tests
There is no automated test suite. Any coverage is welcome. Suggested starting points:
- Unit tests for `CurriculumRegistry` and `CurriculumLoader`
- Unit tests for `ContentValidator`
- Integration tests for the `/api/generate` endpoint (mock Claude and S3)
- Auth tests (signup, login, JWT expiry)

### 3. Additional content types
To add a new generator (e.g. flashcard sets, quiz questions):

1. Create `features/my_type.py` with a generator class.
2. Add a route in `api_endpoints.py` inside `register_all_routes()`.
3. Instantiate the class in `app.py` and pass it as a dependency.

### 4. Frontend
The frontend is plain HTML + JavaScript in `dashboard.html` and `essay_generator.html`. Any framework migration, accessibility improvements, or mobile optimisation is welcome.

### 5. Deployment resources
- Dockerfile + docker-compose example
- Railway / Render / Fly.io one-click deploy buttons
- Helm chart or Kubernetes manifests

---

## Pull request guidelines

1. **Open an issue first** for any change larger than a bug fix, so the approach can be agreed before you write code.
2. **One concern per PR** — separate unrelated changes into separate PRs.
3. **No new secrets** — environment variables only, never hardcoded values.
4. **No new hardcoded domains, buckets, or timezones** — everything must be configurable via env vars or the registry.
5. **Keep backward compatibility** — the `teachers` table and `teacher_id` field in JWT payloads must remain functional.

---

## Code style

- Python: PEP 8, no line length limit enforced but keep lines readable.
- Comments only where the *why* is non-obvious — well-named identifiers are preferred over comments explaining *what* the code does.
- No new dependencies without a discussion in the issue first.

---

## Reporting issues

Open a GitHub issue with:
- What you expected to happen
- What actually happened
- Relevant log output
- Python version and OS
