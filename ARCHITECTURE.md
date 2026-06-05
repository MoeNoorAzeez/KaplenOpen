# Architecture

## Overview

```
                          ┌──────────────┐
  Browser / API client ──►│  Flask app   │
                          │  (app.py)    │
                          └──────┬───────┘
                                 │
               ┌─────────────────┼─────────────────┐
               │                 │                 │
        ┌──────▼──────┐  ┌───────▼──────┐  ┌──────▼──────┐
        │ PostgreSQL  │  │  Amazon S3   │  │  Anthropic  │
        │  (schema)   │  │  (content)   │  │   Claude    │
        └─────────────┘  └──────────────┘  └─────────────┘
```

---

## Application factory

`app.py` is the single entry point:

1. Loads `config.py` → resolves all env vars into a `Config` object.
2. Creates Flask app, enables CORS.
3. Connects to PostgreSQL via `features/database.py` → runs `init_tables()`.
4. Creates boto3 S3 client.
5. Loads `curricula/registry.json` into a `CurriculumRegistry`.
6. Instantiates all feature classes (generator, validator, packager, …).
7. Calls `register_all_routes()` from `api_endpoints.py`, injecting dependencies.
8. Registers the `synthesis` blueprint from `features/__init__.py`.

---

## Config

`config.py` exposes four classes:

| Class | Purpose |
|---|---|
| `Config` | Base — reads all env vars with defaults |
| `DevelopmentConfig` | DEBUG=True |
| `ProductionConfig` | DEBUG=False, stricter settings |
| `TestingConfig` | In-memory overrides for unit tests |

`get_config()` returns the right class based on `FLASK_ENV`.

---

## Curriculum layer

```
curricula/registry.json
        │
        ▼
CurriculumRegistry          loads + caches all entries
        │
        ▼
CurriculumLoader            resolves path_template → S3 key → fetches JSON
        │
        ▼
ScriptGenerator / LongFormGenerator / …   receives content dict
```

The registry decouples domain knowledge from generation logic. Generators ask the loader for content; they never know the S3 key or bucket directly.

### Content JSON format (S3 leaf node)

```json
{
  "title": "Lesson title",
  "objectives": ["..."],
  "concepts": ["..."],
  "examples": ["..."],
  "practice_problems": ["..."],
  "notes": "..."
}
```

Fields beyond `title` and `objectives` are optional — validators check only the dimensions declared in `quality_rules.required_dimensions`.

---

## Generation pipeline

```
Request  →  /api/generate
              │
              ├─ resolve curriculum (registry lookup)
              ├─ fetch content (CurriculumLoader → S3)
              ├─ build prompt (ScriptGenerator)
              │     ├─ CallawayFramework  (story direction / lens / beats)
              │     └─ YoutubePackager   (hook / title / thumbnail)
              ├─ call Claude API
              ├─ ContentValidator        (coverage check)
              ├─ Dedup check
              └─ persist to DB (ScriptStore)
```

Long-form, essay, and podcast generators follow the same pattern with extra phases (outline → draft → each section).

---

## Authentication

- Signup/login via `features/auth.py` — bcrypt passwords, JWT response.
- JWT payload: `{ creator_id, teacher_id (alias), role, exp }`.
- `@require_jwt` decorator injects `request.creator_id` and `request.teacher_id`.
- `@require_admin` additionally checks `role == "admin"`.

---

## Database schema

All tables are created automatically on first run. The schema is backward-compatible — columns added in the open-source refactor use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so existing deployments upgrade in-place.

### Key tables

| Table | Primary key | Notes |
|---|---|---|
| `organizations` | `id` UUID | Multi-tenant root |
| `users` | `id` UUID | Auth accounts |
| `teachers` | `teacher_id` UUID | Legacy creator profile; used for YouTube OAuth |
| `content_creators` | `id` UUID | New canonical creator profile |
| `generated_scripts` | `script_id` UUID | All content; includes `curriculum_id`, `content_unit`, `content_leaf` |
| `essays` | `id` UUID | Essay metadata + S3 key |
| `payments` | `id` UUID | Subscription records |
| `oauth_states` | `state` TEXT | One-time CSRF tokens (10-min TTL) |
| `published_videos` | `id` UUID | YouTube publish records |
| `video_performance` | `id` UUID | Analytics snapshots |

---

## YouTube OAuth2 flow

```
Teacher clicks "Connect YouTube"
        │
        ▼
GET /api/youtube/auth
  → generate state token, store in oauth_states (10-min TTL)
  → redirect to Google consent screen
        │
        ▼
Google redirects to YOUTUBE_OAUTH_REDIRECT_URI?code=…&state=…
        │
        ▼
GET /api/youtube/callback
  → verify state (one-time DELETE from oauth_states)
  → exchange code for access + refresh tokens
  → store tokens in teachers table
```

Tokens are refreshed transparently in `YouTubeOAuthManager.get_credentials()` when the stored expiry has passed.

---

## Content delivery

- **Scripts** — stored in `generated_scripts` table; downloadable as DOCX via `/api/export/docx/<id>`.
- **Essays** — content chunked to S3 (`essays/<teacher_id>/<id>/content.txt`); metadata in `essays` table.
- **Analytics** — YouTube Data API v3 fetched on demand; snapshots stored in `video_performance`.

---

## Payments

`features/payments.py` handles Stripe webhook events:

| Event | Action |
|---|---|
| `checkout.session.completed` | Mark subscription active, set expiry |
| `customer.subscription.deleted` | Mark subscription expired |

The Stripe webhook secret is verified via HMAC before any DB write.

---

## Feature flags / extensions

There are no feature flags. To add a content type:

1. Create `features/my_type.py` with a generator class.
2. Instantiate it in `app.py`.
3. Add a route in `api_endpoints.py` (or a new blueprint).

That's it.
