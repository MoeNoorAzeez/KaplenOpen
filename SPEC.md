# Technical Specification

**Kaplen Content Generation Platform**  
Version: 2.0.0 (provider-agnostic)  
Date: 2026-06-05

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Environment Variables](#2-environment-variables)
3. [LLM Provider Interface](#3-llm-provider-interface)
4. [Authentication](#4-authentication)
5. [API Endpoints](#5-api-endpoints)
6. [Database Schema](#6-database-schema)
7. [Curriculum Registry Schema](#7-curriculum-registry-schema)
8. [Content Generation Pipelines](#8-content-generation-pipelines)
9. [Streaming Protocol](#9-streaming-protocol)
10. [Error Patterns](#10-error-patterns)
11. [Extension Points](#11-extension-points)

---

## 1. System Overview

Kaplen is a Flask application that exposes a JSON REST API. It generates structured educational content (YouTube scripts, essays, podcast outlines) by orchestrating an LLM against curriculum data fetched from S3 and stored in PostgreSQL.

**Runtime dependencies:**

| Dependency | Purpose |
|---|---|
| Flask + Flask-CORS | HTTP server |
| psycopg2-binary | PostgreSQL driver |
| boto3 | AWS S3 access |
| PyJWT | JWT encode/decode |
| bcrypt | Password hashing |
| python-docx | DOCX export |
| pytz | Timezone handling |
| google-auth + google-api-python-client | YouTube OAuth |
| anthropic *(optional)* | Anthropic Claude SDK |
| openai *(optional)* | OpenAI / compatible SDK |

**Entry point:** `app.py` instantiates infrastructure, wires feature classes, and calls `register_all_routes()`.

---

## 2. Environment Variables

All configuration is read from environment variables (or `.env` via python-dotenv). No secrets are hardcoded.

### Flask / App

| Variable | Default | Required | Description |
|---|---|---|---|
| `FLASK_ENV` | `development` | — | `development` or `production` |
| `SECRET_KEY` | `dev-key-...` | **Yes** | Flask session secret |
| `JWT_SECRET` | `dev-jwt-secret-...` | **Yes** | JWT signing key (HS256) |
| `DOMAIN` | `localhost:5000` | — | Public domain (used in URLs) |
| `TIMEZONE` | `UTC` | — | App timezone |
| `FRONTEND_PATH` | `./static` | — | Directory containing HTML files |

### Database

| Variable | Default | Required | Description |
|---|---|---|---|
| `DATABASE_URL` | — | Either this or `DB_*` | Full Postgres URL |
| `DB_HOST` | — | **Yes** (if no `DATABASE_URL`) | Postgres host |
| `DB_NAME` | `kaplen` | — | Database name |
| `DB_USER` | `postgres` | — | Database user |
| `DB_PASSWORD` | `""` | — | Database password |
| `DB_PORT` | `5432` | — | Database port |

### LLM Provider

| Variable | Default | Required | Description |
|---|---|---|---|
| `LLM_PROVIDER` | `anthropic` | **Yes** | `anthropic` or `openai` |
| `LLM_API_KEY` | — | — | Universal key (overrides provider-specific keys) |
| `LLM_MODEL` | — | — | Universal model override |
| `LLM_BASE_URL` | — | — | Base URL for OpenAI-compatible endpoints |
| `ANTHROPIC_API_KEY` | — | If `LLM_PROVIDER=anthropic` | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | — | Anthropic model ID |
| `OPENAI_API_KEY` | — | If `LLM_PROVIDER=openai` | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | — | OpenAI model ID |

### AWS

| Variable | Default | Required | Description |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | — | If using S3 | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | — | If using S3 | AWS secret key |
| `AWS_REGION` | `us-east-1` | — | AWS region |
| `S3_BUCKET` | — | If using S3 | S3 bucket for curriculum data + essays |

### Curriculum

| Variable | Default | Required | Description |
|---|---|---|---|
| `CURRICULUM_REGISTRY_PATH` | `curricula/registry.json` | — | Path to registry JSON |
| `DEFAULT_CURRICULUM_ID` | `iraqi-moe-2024` | — | Fallback curriculum |

### Payments

| Variable | Default | Required | Description |
|---|---|---|---|
| `WAYL_MERCHANT_TOKEN` | — | If using Wayl | Merchant token |
| `WAYL_WEBHOOK_SECRET` | — | If using Wayl | HMAC secret for webhook signature |
| `WAYL_WEBHOOK_URL` | — | — | Webhook callback URL |
| `STRIPE_API_KEY` | — | — | Stripe key (stub, not implemented) |

### YouTube OAuth

| Variable | Default | Required | Description |
|---|---|---|---|
| `YOUTUBE_CLIENT_ID` | — | If using YouTube | Google OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | — | If using YouTube | Google OAuth client secret |
| `YOUTUBE_OAUTH_REDIRECT_URI` | — | If using YouTube | OAuth callback URL |

---

## 3. LLM Provider Interface

All generators depend on `features.llm_provider.LLMProvider`. This is the full interface contract.

### Abstract Base

```python
class LLMProvider:
    def complete(self, messages: list[dict], max_tokens: int = 2000) -> str:
        """
        Send messages to the LLM and return the full response text.

        Args:
            messages:   OpenAI-format messages list, e.g.
                        [{"role": "user", "content": "..."}]
            max_tokens: Maximum output tokens.

        Returns:
            str — full response text, stripped.

        Raises:
            NotImplementedError if not overridden.
        """

    def stream_complete(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        on_token: callable = None,
    ) -> str:
        """
        Complete with an optional per-token callback.
        Default implementation calls complete() and fires on_token once with the full text.
        Override for real token-by-token streaming.

        Args:
            messages:   OpenAI-format messages list.
            max_tokens: Maximum output tokens.
            on_token:   Optional callable(text: str) called for each token/chunk.

        Returns:
            str — full accumulated text.
        """

    @property
    def model_name(self) -> str:
        """Returns model identifier string."""
```

### Provided Implementations

#### AnthropicProvider

```python
AnthropicProvider(api_key: str, model: str)
```

- `complete()` — calls `client.messages.create()`; returns `response.content[0].text`
- `stream_complete()` — uses `client.messages.stream()`, fires `on_token` per `text_stream` chunk

Default model: `claude-sonnet-4-6`

#### OpenAIProvider

```python
OpenAIProvider(api_key: str, model: str, base_url: str = None)
```

- `complete()` — calls `client.chat.completions.create()`; returns `response.choices[0].message.content`
- `stream_complete()` — uses `stream=True`, fires `on_token` per delta chunk

Default model: `gpt-4o`

`base_url` makes this work with any OpenAI-compatible endpoint (Ollama, Together AI, Groq, LM Studio, etc.).

### Factory

```python
from features.llm_provider import get_provider
provider = get_provider()  # reads from environment
```

Key resolution order:
1. `LLM_API_KEY` (if set, overrides everything)
2. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` (provider-specific)

Model resolution order:
1. `LLM_MODEL` (if set, overrides everything)
2. `ANTHROPIC_MODEL` / `OPENAI_MODEL` (provider-specific defaults)

### Implementing a Custom Provider

```python
from features.llm_provider import LLMProvider

class MyProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._model = model
        # initialize your client here

    def complete(self, messages, max_tokens=2000):
        # call your API, return str
        ...

    def stream_complete(self, messages, max_tokens=2000, on_token=None):
        # stream tokens, call on_token(text) per chunk, return full str
        ...
```

Wire it in `app.py` instead of calling `get_provider()`.

---

## 4. Authentication

### JWT Token Structure

```json
{
  "creator_id": "<uuid>",
  "teacher_id": "<uuid>",
  "exp": 1234567890
}
```

- `creator_id` — canonical user UUID (from `users.id`)
- `teacher_id` — same UUID, kept for backward compatibility
- Algorithm: HS256
- Expiry: 7 days
- Secret: `JWT_SECRET` env var

### Request Format

```
Authorization: Bearer <jwt-token>
```

### Auth Decorators

| Decorator | Behavior | Sets on `request` |
|---|---|---|
| `@require_jwt` | Validates token, 401 if missing/invalid | `request.user_id`, `request.teacher_id`, `request.creator_id` |
| `@require_admin` | Must also follow `@require_jwt`; checks `users.role = 'admin'` | — |
| `@require_active_subscription` | Checks `users.subscription_status = 'active'` | — |
| `@require_essay_author` | Checks `users.is_essay_author = true` | — |

### Signup

`POST /api/auth/signup`

Validates email format, password ≥ 6 chars, username ≥ 3 chars. Password hashed with bcrypt (cost 12). Returns JWT on success.

### Login

`POST /api/auth/login`

Validates email format, fetches user, verifies bcrypt hash. Returns JWT + subscription status.

---

## 5. API Endpoints

### Overview Table

| # | Method | Path | Auth | Description |
|---|---|---|---|---|
| 1 | GET | `/api/health` | — | Full health check |
| 2 | GET | `/api/status` | — | Liveness probe |
| 3 | GET | `/api/subjects` | — | List subjects |
| 4 | GET | `/api/topics/<subject>` | — | Topics for a subject |
| 5 | GET | `/api/subtopics/<subject>/<topic>` | — | Subtopics |
| 6 | GET | `/api/curricula` | — | List curricula |
| 7 | GET | `/api/curricula/<curriculum_id>` | — | Curriculum metadata |
| 8 | GET | `/api/curricula/<curriculum_id>/hierarchy/<level>` | — | Hierarchy items at level |
| 9 | GET | `/api/curricula/<curriculum_id>/hierarchy/<level>/<item>/children` | — | Children of item |
| 10 | POST | `/api/auth/signup` | — | Register |
| 11 | POST | `/api/auth/login` | — | Login |
| 12 | GET | `/api/auth/me` | JWT | Current user |
| 13 | POST | `/api/auth/teacher` | — | Legacy teacher login |
| 14 | GET | `/api/billing/status` | JWT | Subscription + last 12 payments |
| 15 | GET | `/api/billing/history` | JWT | Full payment history |
| 16 | POST | `/api/payment/webhook` | Signature | Wayl webhook |
| 17 | POST | `/api/generate` | JWT + subscription | Generate script |
| 18 | POST | `/api/generate-study-tips` | — | Study tips script |
| 19 | GET | `/api/scripts/<teacher_id>` | JWT | List teacher scripts |
| 20 | GET | `/api/export/<script_id>` | JWT | Download script DOCX |
| 21 | GET | `/api/analytics/<teacher_id>` | JWT | Improvement metrics |
| 22 | GET | `/api/analytics/top/<teacher_id>` | JWT | Top scripts by score |
| 23 | POST | `/api/analytics/save` | JWT | Save engagement metrics |
| 24 | GET | `/api/admin/teachers` | JWT + admin | List all teachers |
| 25 | GET | `/api/center/<center_id>/dashboard` | — | Center dashboard data |
| 26 | GET | `/center-dashboard` | — | Center dashboard HTML |
| 27 | GET | `/api/teacher/youtube/auth-url` | JWT | YouTube OAuth URL |
| 28 | GET | `/api/teacher/youtube/oauth-callback` | — | OAuth callback |
| 29 | POST | `/api/teacher/youtube/sync-analytics` | JWT | Sync video metrics |
| 30 | POST | `/api/teacher/youtube/sync-all-videos` | JWT | Sync all channel videos |
| 31 | POST | `/api/teacher/youtube/disconnect` | JWT | Revoke YouTube access |
| 32 | GET | `/api/teacher/youtube/status` | JWT | YouTube connection status |
| 33 | POST | `/api/generate-long-form` | JWT + subscription | Streaming long-form video |
| 34 | GET | `/api/long-form/<script_id>` | JWT | Retrieve long-form script |
| 35 | GET | `/api/long-form/export/<script_id>` | JWT | Export long-form DOCX |
| 36 | POST | `/api/essay/ingest-chunk` | JWT + essay_author | Upload source chunk to S3 |
| 37 | POST | `/api/essay/generate` | JWT + essay_author | Generate essay |
| 38 | GET | `/api/essay/<essay_id>` | JWT + essay_author | Retrieve essay |
| 39 | GET | `/api/essay/<essay_id>/export` | JWT + essay_author | Export essay DOCX/MD |
| 40 | GET | `/api/essays` | JWT + essay_author | List all essays |
| 41 | GET | `/essay_generator.html` | — | Essay generator UI |
| 42 | GET | `/` | — | Landing page |
| 43 | GET | `/dashboard` | — | Dashboard HTML |
| 44 | POST | `/api/podcast/generate` | JWT + subscription | Podcast outline |
| 45 | POST | `/api/teachers/synthesis/...` | JWT | Transcript synthesis (Blueprint) |

---

### Health

#### GET /api/health

Full health check — makes a real DB query and a real LLM API call.

**Response 200:**
```json
{
  "status": "healthy",
  "database": {"status": "healthy", "message": "Connected"},
  "llm_api":  {"status": "healthy", "message": "LLM API connected (claude-sonnet-4-6)"},
  "timestamp": "2026-06-05T10:00:00+00:00"
}
```

If any component is unhealthy the top-level `status` is `"unhealthy"` and the individual component shows `"status": "unhealthy"`.

#### GET /api/status

Liveness probe — no external calls.

**Response 200:**
```json
{"status": "ok", "timestamp": "2026-06-05T10:00:00+00:00"}
```

---

### Curriculum

#### GET /api/subjects

Returns all subjects from S3 data loader.

**Response 200:**
```json
{"subjects": ["mathematics", "physics", "chemistry", "biology", "history"]}
```

#### GET /api/topics/`<subject>`

**Response 200:**
```json
{"subject": "mathematics", "topics": ["algebra", "geometry", "calculus"]}
```

#### GET /api/subtopics/`<subject>`/`<topic>`

**Query params:** `curriculum_id` (optional)

**Response 200:**
```json
{
  "subject": "mathematics",
  "topic": "algebra",
  "subtopics": ["linear-equations", "quadratic-equations", "polynomials"]
}
```

#### GET /api/curricula

**Response 200:**
```json
{
  "curricula": [
    {
      "curriculum_id": "iraqi-moe-2024",
      "name": "Iraqi Ministry of Education 2024",
      "language": "ar",
      "region": "Iraq",
      "subjects": ["mathematics", "physics", "chemistry"]
    }
  ]
}
```

#### GET /api/curricula/`<curriculum_id>`

**Response 200:** Full curriculum metadata object from registry.  
**Response 404:** `{"error": "Curriculum not found"}`

#### GET /api/curricula/`<curriculum_id>`/hierarchy/`<level>`

Returns items at the given hierarchy level (e.g., `subject`, `topic`, `subtopic`).

**Response 200:**
```json
{"curriculum_id": "...", "level": "subject", "items": ["mathematics", "physics"]}
```

#### GET /api/curricula/`<curriculum_id>`/hierarchy/`<level>`/`<item>`/children

Returns children of `item` at the next level down in the hierarchy.

**Response 200:**
```json
{
  "curriculum_id": "...",
  "parent_level": "subject",
  "parent_item": "mathematics",
  "child_level": "topic",
  "children": ["algebra", "geometry"]
}
```

---

### Authentication

#### POST /api/auth/signup

**Request:**
```json
{
  "email": "teacher@example.com",
  "password": "min6chars",
  "username": "myusername",
  "name": "Full Name"
}
```

**Response 201:**
```json
{
  "user_id": "<uuid>",
  "email": "teacher@example.com",
  "username": "myusername",
  "token": "<jwt>"
}
```

**Response 400:** Validation errors (invalid email, short password, short username)  
**Response 409:** Email or username already exists

#### POST /api/auth/login

**Request:**
```json
{"email": "teacher@example.com", "password": "mypassword"}
```

**Response 200:**
```json
{
  "user_id": "<uuid>",
  "email": "teacher@example.com",
  "username": "myusername",
  "token": "<jwt>",
  "subscription_status": "active",
  "teacher_id": "<uuid>"
}
```

**Response 401:** Invalid credentials

#### GET /api/auth/me

**Headers:** `Authorization: Bearer <token>`

**Response 200:**
```json
{
  "user_id": "<uuid>",
  "email": "teacher@example.com",
  "username": "myusername",
  "name": "Full Name",
  "role": "user",
  "subscription_status": "active"
}
```

#### POST /api/auth/teacher

Legacy flow — creates or retrieves a teacher record by name (no JWT required).

**Request:**
```json
{"teacher_name": "Teacher Name", "center_id": "<uuid-optional>"}
```

**Response 200:**
```json
{"success": true, "teacher_id": "<uuid>", "teacher_name": "Teacher Name"}
```

---

### Billing

#### GET /api/billing/status

**Response 200:**
```json
{
  "subscription_status": "active",
  "subscription_expires_at": "2027-01-01T00:00:00",
  "recent_payments": [
    {
      "id": "<uuid>",
      "amount": 1000,
      "currency": "USD",
      "status": "completed",
      "paid_at": "2026-05-01T12:00:00"
    }
  ]
}
```

#### GET /api/billing/history

**Response 200:**
```json
{"payments": [...]}   // last 50 payments
```

#### POST /api/payment/webhook

Wayl payment gateway webhook. HMAC-SHA256 signature required.

**Headers:** `X-Webhook-Signature: <sha256-hmac>`

**Request:**
```json
{
  "status": "completed",
  "transaction_id": "txn_123",
  "teacher_id": "<uuid>",
  "amount": 1000,
  "currency": "USD"
}
```

**Response 200:** `{"status": "received"}`  
**Response 401:** Invalid signature

---

### Script Generation

#### POST /api/generate

Requires JWT + active subscription.

**Request:**
```json
{
  "subject": "mathematics",
  "topic": "algebra",
  "subtopic": "linear-equations",
  "duration_minutes": 14,
  "hook_archetype": "default",
  "teacher_name": "Optional",
  "curriculum_id": "iraqi-moe-2024",
  "path_args": {"subject": "mathematics", "topic": "algebra", "subtopic": "linear-equations"}
}
```

Either `subject`/`topic`/`subtopic` or `path_args` must be provided. If both are provided, `path_args` takes precedence for S3 key resolution.

`hook_archetype` values: `default`, `story`, `question`, `fact`, `teacher`

**Response 201:**
```json
{
  "success": true,
  "script_id": "<uuid>",
  "teacher_id": "<uuid>",
  "title": "Understanding Linear Equations",
  "hook": "Did you know that every time you...",
  "hook_archetype": "question",
  "thumbnail_prompt": "...",
  "script_content": "...",
  "callaway_direction": {"direction": "...", "lens": "..."},
  "callaway_beats": {"beats": [...], "rhythm": "..."},
  "quality_metrics": {"coverage_score": 0.87, "word_count": 1850},
  "is_duplicate": false,
  "word_count": 1850
}
```

#### POST /api/generate-study-tips

No auth required.

**Request:**
```json
{
  "tip_topic": "exam preparation",
  "duration_minutes": 10,
  "hook_archetype": "teacher",
  "teacher_name": "Optional"
}
```

**Response 200:** Same shape as `/api/generate` response.

#### GET /api/scripts/`<teacher_id>`

Returns own scripts only (JWT must match teacher_id).

**Response 200:**
```json
{
  "success": true,
  "teacher_id": "<uuid>",
  "scripts": [
    {
      "script_id": "<uuid>",
      "subject": "mathematics",
      "topic": "algebra",
      "subtopic": "linear-equations",
      "title": "...",
      "status": "draft",
      "word_count": 1850,
      "created_at": "2026-06-05T10:00:00"
    }
  ],
  "total": 12
}
```

#### GET /api/export/`<script_id>`

Downloads the script as a `.docx` file. Cache-first (in-memory `scripts_cache`), then falls back to DB.

**Response:** Binary DOCX download  
**Content-Type:** `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

---

### Analytics

#### GET /api/analytics/`<teacher_id>`

Aggregated improvement metrics comparing early vs. recent script performance.

**Response 200:**
```json
{
  "teacher_id": "<uuid>",
  "total_scripts": 20,
  "avg_views": 1234.5,
  "avg_engagement_rate": 0.042,
  "improvement_rate": 0.15,
  "best_performing_topic": "algebra"
}
```

#### GET /api/analytics/top/`<teacher_id>`

**Query params:** `limit` (default: 5)

**Response 200:**
```json
{
  "teacher_id": "<uuid>",
  "top_scripts": [
    {
      "script_id": "<uuid>",
      "title": "...",
      "weighted_view_score": 9823.4,
      "views": 10000,
      "engagement_rate": 0.05
    }
  ]
}
```

#### POST /api/analytics/save

**Request:**
```json
{
  "video_id": "yt-video-id",
  "views": 5000,
  "channel_subscribers": 10000,
  "likes": 200,
  "comments": 50,
  "shares": 30
}
```

**Response 200:**
```json
{"success": true, "analytics_id": "<uuid>"}
```

---

### Admin

#### GET /api/admin/teachers

Requires JWT + `users.role = 'admin'`.

**Response 200:**
```json
{
  "teachers": [
    {
      "id": "<uuid>",
      "username": "teacher1",
      "email": "teacher1@example.com",
      "subscription_status": "active",
      "subscription_expires_at": "2027-01-01T00:00:00",
      "created_at": "2026-01-01T00:00:00"
    }
  ],
  "total": 42
}
```

---

### Center Dashboard

#### GET /api/center/`<center_id>`/dashboard

Returns all teachers and their scripts for a center, with aggregate stats.

**Response 200:**
```json
{
  "success": true,
  "center_id": "<uuid>",
  "teachers": [
    {
      "teacher_id": "<uuid>",
      "username": "teacher1",
      "subscription_status": "active",
      "youtube_channel": "UC...",
      "channel_subscribers": 5000,
      "total_scripts": 15,
      "scripts": [
        {
          "id": "<uuid>",
          "subject": "mathematics",
          "topic": "algebra",
          "status": "published",
          "word_count": 1850,
          "youtube_url": "https://youtube.com/...",
          "created_at": "2026-06-01T10:00:00",
          "views": 1200,
          "likes": 45,
          "engagement_rate": 0.038
        }
      ]
    }
  ],
  "stats": {
    "total_teachers": 8,
    "total_scripts": 120,
    "published_count": 95,
    "draft_count": 25,
    "total_views": 98000,
    "avg_engagement_rate": 0.041
  }
}
```

---

### YouTube OAuth

#### GET /api/teacher/youtube/auth-url

**Response 200:**
```json
{
  "success": true,
  "auth_url": "https://accounts.google.com/o/oauth2/...",
  "state": "<one-time-csrf-token>"
}
```

#### GET /api/teacher/youtube/oauth-callback

Query params: `code`, `state`, `teacher_id`

On success: redirects to `/dashboard?youtube=connected`  
On failure: `{"error": "OAuth failed"}` 500

#### POST /api/teacher/youtube/sync-analytics

**Request:**
```json
{"video_id": "yt-video-id"}
```

**Response 200:**
```json
{
  "success": true,
  "metrics": {
    "views": 5000,
    "likes": 200,
    "comments": 50,
    "ctr": 0.042,
    "average_retention": 0.61
  }
}
```

#### POST /api/teacher/youtube/sync-all-videos

Fetches metrics for up to 50 most recent channel videos.

**Response 200:**
```json
{
  "success": true,
  "synced_count": 48,
  "total_count": 48,
  "videos": [
    {"video_id": "yt-id", "views": 1200, "likes": 45, "comments": 12}
  ]
}
```

#### POST /api/teacher/youtube/disconnect

**Response 200:**
```json
{"success": true, "message": "YouTube account disconnected"}
```

#### GET /api/teacher/youtube/status

**Response 200:**
```json
{
  "connected": true,
  "channel_id": "UC...",
  "channel_name": "My Channel",
  "subscribers": 5000,
  "last_sync": "2026-06-05T08:00:00"
}
```

---

### Long-Form Videos

#### POST /api/generate-long-form

Requires JWT + active subscription. Returns Server-Sent Events stream.

**Request:**
```json
{
  "subject": "physics",
  "topic": "mechanics",
  "subtopic": "newtons-laws",
  "duration_minutes": 60
}
```

`duration_minutes` must be `60` or `180`.

**Response:** `text/event-stream`

```
event: outline
data: {"sections": [...], "total_sections": 8}

event: section_start
data: {"section_index": 0, "section_title": "Introduction"}

event: section_stream
data: {"text": "Welcome to..."}

event: section_complete
data: {"section_index": 0, "word_count": 450}

event: complete
data: {"success": true, "script_id": "<uuid>", "full_script": "...", "final_word_count": 8400, "outline": {...}, "validation": {...}, "is_duplicate": false}
```

#### GET /api/long-form/`<script_id>`

**Response 200:**
```json
{
  "success": true,
  "script_id": "<uuid>",
  "subject": "physics",
  "topic": "mechanics",
  "subtopic": "newtons-laws",
  "duration_minutes": 60,
  "word_count": 8400,
  "outline": {"sections": [...]},
  "full_script": "...",
  "validation": {"coverage_score": 0.91},
  "is_duplicate": false,
  "generated_at": "2026-06-05T10:00:00"
}
```

#### GET /api/long-form/export/`<script_id>`

**Query params:** `include_outline=true` (default: false)

**Response:** Binary DOCX download

---

### Essay Generator

All essay routes require JWT + `users.is_essay_author = true`.

#### POST /api/essay/ingest-chunk

Upload source material in chunks. Each chunk is stored as `essay-sources/<session_id>/chunk_<index>.txt` in S3.

**Request:**
```json
{
  "session_id": "my-session-uuid",
  "chunk_index": 0,
  "chunk_text": "...source material text...",
  "total_chunks": 3
}
```

**Response 200:**
```json
{"success": true, "chunk_index": 0, "total_chunks": 3}
```

#### POST /api/essay/generate

**Request:**
```json
{
  "title": "The Impact of Newton's Laws",
  "source_material": "...full text...",
  "session_id": "my-session-uuid",
  "essay_type": "medium",
  "tone": "academic",
  "target_audience": "educated general reader"
}
```

Either `source_material` or `session_id` (to load from S3 chunks) must be provided.

`essay_type` values: `short` (~800 words), `medium` (~1500 words), `long` (~3000 words)  
`tone` values: `academic`, `conversational`, `journalistic`

**Response 201:**
```json
{
  "success": true,
  "essay_id": "<uuid>",
  "title": "...",
  "full_essay": "...",
  "final_word_count": 1520,
  "outline": {"sections": [...]},
  "validation": {"coverage_score": 0.88},
  "source_hash": "md5hash",
  "is_duplicate": false
}
```

#### GET /api/essay/`<essay_id>`

**Response 200:**
```json
{
  "success": true,
  "essay_id": "<uuid>",
  "title": "...",
  "content": "...",
  "essay_type": "medium",
  "tone": "academic",
  "target_audience": "educated general reader",
  "word_count": 1520,
  "outline": {...},
  "status": "draft",
  "created_at": "2026-06-05T10:00:00"
}
```

#### GET /api/essay/`<essay_id>`/export

**Query params:** `format=docx` (default) or `format=md`

**Response:** File download (DOCX or Markdown)

#### GET /api/essays

**Response 200:**
```json
{
  "essays": [
    {
      "essay_id": "<uuid>",
      "title": "...",
      "essay_type": "medium",
      "tone": "academic",
      "word_count": 1520,
      "status": "draft",
      "created_at": "2026-06-05T10:00:00"
    }
  ],
  "total": 5
}
```

---

### Podcast

#### POST /api/podcast/generate

Requires JWT + active subscription.

**Request:**
```json
{
  "speaker_profile": "Host: Dr. Sarah, physics professor at MIT, specializes in quantum mechanics",
  "guest_profile": "Guest: Ahmed, PhD student researching quantum computing applications",
  "episode_context": "Discussing practical applications of quantum computing in education"
}
```

**Response 200:**
```json
{
  "success": true,
  "outline": {
    "episode_title": "...",
    "segments": [
      {
        "segment": 1,
        "title": "Introduction",
        "duration_minutes": 5,
        "talking_points": ["...", "..."],
        "transition": "..."
      }
    ],
    "total_duration_minutes": 45
  },
  "show_notes": "...",
  "episode_description": "..."
}
```

---

## 6. Database Schema

All 12 tables are created automatically by `DB.init_tables()` on startup. New columns are added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — no destructive migrations.

### organizations

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | — |
| `name` | VARCHAR(255) | UNIQUE NOT NULL | Organization name |
| `domain` | VARCHAR(255) | — | Email domain |
| `curriculum_id` | VARCHAR(100) | — | Default curriculum |
| `language` | VARCHAR(10) | DEFAULT 'ar' | Content language |
| `timezone` | VARCHAR(100) | DEFAULT 'UTC' | — |
| `config` | JSONB | — | Arbitrary config |
| `subscription_status` | VARCHAR(50) | DEFAULT 'active' | — |
| `subscription_expires_at` | TIMESTAMP | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | — |

### users

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `email` | VARCHAR(255) | UNIQUE NOT NULL | — |
| `password_hash` | TEXT | NOT NULL | bcrypt hash |
| `username` | VARCHAR(255) | UNIQUE NOT NULL | — |
| `name` | VARCHAR(255) | — | Display name |
| `role` | VARCHAR(50) | DEFAULT 'user' | `user` or `admin` |
| `organization_id` | UUID | FK → organizations | — |
| `creator_type` | VARCHAR(50) | DEFAULT 'educator' | — |
| `curriculum_context` | JSONB | — | User curriculum preferences |
| `api_key` | VARCHAR(255) | — | Optional API key |
| `subscription_status` | VARCHAR(50) | DEFAULT 'pending' | `pending`, `active`, `expired` |
| `subscription_expires_at` | TIMESTAMP | — | — |
| `is_essay_author` | BOOLEAN | DEFAULT false | Essay feature gate |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | — |

### centers

| Column | Type | Constraints | Description |
|---|---|---|---|
| `center_id` | UUID | PK | — |
| `name` | VARCHAR(255) | NOT NULL | — |
| `manager_email` | VARCHAR(255) | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |

### teachers

| Column | Type | Constraints | Description |
|---|---|---|---|
| `teacher_id` | UUID | PK | — |
| `user_id` | UUID | FK → users | — |
| `name` | VARCHAR(255) | NOT NULL | — |
| `username` | VARCHAR(255) | — | — |
| `center_id` | UUID | FK → centers | — |
| `youtube_api_key` | TEXT | — | Legacy API key (pre-OAuth) |
| `youtube_channel_id` | TEXT | — | — |
| `youtube_channel_name` | TEXT | — | — |
| `channel_subs` | INTEGER | DEFAULT 0 | — |
| `youtube_last_sync` | TIMESTAMP | — | Last analytics sync |
| `youtube_oauth_token` | TEXT | — | Encrypted access token |
| `youtube_oauth_refresh_token` | TEXT | — | Encrypted refresh token |
| `youtube_oauth_token_expires_at` | TEXT | — | ISO datetime string |
| `subscription_status` | VARCHAR(50) | DEFAULT 'pending' | — |
| `subscription_expires_at` | TIMESTAMP | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | — |

### content_creators

Generalized creator profile (intended to replace `teachers` long-term).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | FK → users | — |
| `organization_id` | UUID | FK → organizations | — |
| `youtube_channel_id` | TEXT | — | — |
| `youtube_oauth_token` | TEXT | — | — |
| `linkedin_profile` | TEXT | — | — |
| `website` | TEXT | — | — |
| `bio` | TEXT | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |

### generated_scripts

| Column | Type | Constraints | Description |
|---|---|---|---|
| `script_id` | UUID | PK | — |
| `teacher_id` | UUID | FK → teachers | — |
| `organization_id` | UUID | FK → organizations | — |
| `curriculum_id` | VARCHAR(100) | — | Source curriculum |
| `subject` | VARCHAR(255) | — | — |
| `topic` | VARCHAR(255) | — | — |
| `subtopic` | VARCHAR(255) | — | — |
| `domain_category` | VARCHAR(255) | — | Curriculum hierarchy alias |
| `content_unit` | VARCHAR(255) | — | — |
| `content_leaf` | VARCHAR(255) | — | — |
| `domain_context` | JSONB | — | S3-loaded curriculum context |
| `title` | TEXT | — | Generated title |
| `hook` | TEXT | — | Opening hook |
| `hook_archetype` | VARCHAR(50) | — | Hook type |
| `thumbnail_prompt` | TEXT | — | DALL-E / MidJourney prompt |
| `script_content` | TEXT | — | Full script body |
| `script_type` | VARCHAR(50) | DEFAULT 'standard' | `standard`, `long-form`, `study-tips` |
| `metadata` | JSONB | — | Generation metadata |
| `outline` | JSONB | — | Section outline |
| `callaway_direction` | JSONB | — | Story direction + lens |
| `callaway_lens` | JSONB | — | Narrative lens analysis |
| `callaway_beats` | JSONB | — | Beat analysis |
| `content_hash` | VARCHAR(32) | — | MD5 of script content |
| `semantic_hash` | VARCHAR(32) | — | MD5 of normalized content |
| `quality_metrics` | JSONB | — | Coverage score, word count |
| `word_count` | INTEGER | — | — |
| `status` | VARCHAR(50) | DEFAULT 'draft' | `draft`, `published` |
| `center_id` | UUID | FK → centers | — |
| `youtube_url` | TEXT | — | Published URL |
| `youtube_views` | INTEGER | DEFAULT 0 | Cached view count |
| `youtube_channel_subscribers` | INTEGER | DEFAULT 1000 | Cached sub count |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | — |

### essays

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | FK → users | Owner |
| `title` | TEXT | NOT NULL | — |
| `content` | TEXT | — | Full essay text |
| `metadata` | JSONB | — | type, tone, word_count, outline, validation |
| `status` | VARCHAR(50) | DEFAULT 'draft' | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | — |

### youtube_analytics

| Column | Type | Constraints | Description |
|---|---|---|---|
| `analytics_id` | UUID | PK | — |
| `script_id` | UUID | FK → generated_scripts | — |
| `teacher_id` | UUID | FK → teachers | — |
| `views` | INTEGER | DEFAULT 0 | — |
| `ctr` | FLOAT | DEFAULT 0.0 | Click-through rate |
| `average_retention` | FLOAT | DEFAULT 0.0 | Watch time % |
| `likes` | INTEGER | DEFAULT 0 | — |
| `comments` | INTEGER | DEFAULT 0 | — |
| `shares` | INTEGER | DEFAULT 0 | — |
| `engagement_rate` | FLOAT | DEFAULT 0.0 | (likes+comments+shares)/views |
| `weighted_view_score` | FLOAT | DEFAULT 0.0 | views × engagement_rate × retention |
| `measured_date` | TIMESTAMP | DEFAULT NOW() | — |

### payments

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `teacher_id` | UUID | FK → teachers | — |
| `organization_id` | UUID | FK → organizations | — |
| `amount` | INTEGER | — | Amount in smallest currency unit |
| `currency` | VARCHAR(10) | DEFAULT 'USD' | — |
| `status` | VARCHAR(50) | — | `completed`, `pending`, `failed` |
| `transaction_id` | TEXT | UNIQUE | Gateway transaction ID |
| `paid_at` | TIMESTAMP | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |

### published_videos

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `script_id` | UUID | FK → generated_scripts | — |
| `teacher_id` | UUID | FK → teachers | — |
| `youtube_video_id` | TEXT | — | YouTube video ID |
| `youtube_url` | TEXT | — | Full YouTube URL |
| `published_at` | TIMESTAMP | — | — |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |

### video_performance

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | — |
| `video_id` | UUID | FK → published_videos, UNIQUE | — |
| `measured_date` | TIMESTAMP | DEFAULT NOW() | — |
| `views` | INTEGER | DEFAULT 0 | — |
| `likes` | INTEGER | DEFAULT 0 | — |
| `comments` | INTEGER | DEFAULT 0 | — |
| `shares` | INTEGER | DEFAULT 0 | — |
| `engagement_rate` | FLOAT | DEFAULT 0.0 | — |
| `ctr` | FLOAT | DEFAULT 0.0 | — |
| `average_retention` | FLOAT | DEFAULT 0.0 | — |

### oauth_states

CSRF protection table for YouTube OAuth. Tokens expire after 10 minutes.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `state` | TEXT | PK | Random one-time token |
| `teacher_id` | UUID | NOT NULL | Owner |
| `expires_at` | TIMESTAMP | NOT NULL | 10 minutes from creation |
| `created_at` | TIMESTAMP | DEFAULT NOW() | — |

---

## 7. Curriculum Registry Schema

`curricula/registry.json` is a flat object keyed by curriculum ID.

```json
{
  "<curriculum-id>": {
    "name": "Human-readable name",
    "language": "ar",
    "region": "Iraq",
    "status": "active",
    "metadata": {
      "subjects": ["mathematics", "physics", "chemistry"],
      "grade_levels": ["grade-10", "grade-11", "grade-12"],
      "academic_year": "2024-2025"
    },
    "structure": {
      "levels": ["subject", "topic", "subtopic"],
      "s3_path_template": "{subject}/{topic}/{subtopic}.json"
    },
    "quality": {
      "min_word_count": 800,
      "max_word_count": 2500,
      "required_sections": ["introduction", "main_content", "summary"]
    },
    "generation_hints": {
      "tone": "educational",
      "audience": "high school students",
      "language_style": "formal arabic",
      "examples_per_concept": 2
    }
  }
}
```

### Field Reference

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Display name |
| `language` | Yes | BCP-47 language code |
| `region` | No | Geographic region |
| `status` | No | `active` or `template` |
| `metadata.subjects` | No | List of available subjects |
| `metadata.grade_levels` | No | Grade level identifiers |
| `structure.levels` | Yes | Ordered hierarchy level names |
| `structure.s3_path_template` | Yes | S3 key template using `{level_name}` placeholders |
| `quality.min_word_count` | No | Minimum script word count |
| `quality.max_word_count` | No | Maximum script word count |
| `quality.required_sections` | No | Section names that must appear |
| `generation_hints.tone` | No | Tone instruction passed to LLM |
| `generation_hints.audience` | No | Target audience description |
| `generation_hints.language_style` | No | Writing style instruction |
| `generation_hints.examples_per_concept` | No | Number of examples to include |

### S3 Path Template

The template `{subject}/{topic}/{subtopic}.json` with `path_args = {"subject": "mathematics", "topic": "algebra", "subtopic": "linear-equations"}` resolves to:

```
s3://your-bucket/mathematics/algebra/linear-equations.json
```

Level names must exactly match the keys in `path_args` passed to the `/api/generate` endpoint.

---

## 8. Content Generation Pipelines

### Standard Script Pipeline

`ScriptGenerator.generate(subject, topic, subtopic, duration_minutes, hook_archetype, curriculum_id, path_args)`

1. **Curriculum resolution** — `CurriculumLoader.resolve_s3_key(curriculum_id, path_args)`
2. **Data loading** — `DataLoader.load_topic_data(s3_key)` — fetches JSON from S3
3. **Story direction** — `CallawayFramework.get_direction(topic, curriculum_data)` — returns narrative approach
4. **Narrative lens** — `CallawayFramework.get_lens(direction)` — deepens the storytelling angle
5. **Hook generation** — `YoutubePackager.generate_hook(topic, archetype, duration)` — opening hook text
6. **Script generation** — `LLMProvider.complete([system_prompt, curriculum_prompt])` — full script body
7. **Title generation** — `YoutubePackager.generate_title(script, topic)` — 3 title variants
8. **Thumbnail prompt** — `YoutubePackager.generate_thumbnail(title, hook)` — image generation prompt
9. **Coverage validation** — `ContentValidator.score(script, curriculum_context)` — returns 0.0–1.0 float
10. **Beat analysis** — `CallawayFramework.analyze_beats(script)` — structural beat map
11. **Deduplication** — `Dedup.check_and_store(content_hash)` — skips save if exact duplicate

Total LLM calls per script: **5** (direction, lens, hook, script, title+thumbnail as one prompt or separate)

### Long-Form Pipeline

`LongFormVideoGenerator.generate(subject, topic, subtopic, duration_minutes, stream_callback)`

1. Load curriculum data from S3
2. Generate multi-section outline (8 sections for 60 min, 24 sections for 180 min)
3. For each section:
   a. Call `LLMProvider.stream_complete(section_prompt, on_token=stream_callback('section_stream', token))`
   b. Emit `section_start` → token stream → `section_complete` events
4. Assemble full script
5. Run `ContentValidator.score()` on assembled script
6. Run `Dedup.check_and_store()`
7. Emit `complete` event with full result

### Essay Pipeline

`EssayGenerator.generate(title, source_material, essay_type, tone, target_audience, stream_callback)`

1. Analyze source material — extract key themes and arguments
2. Generate essay outline (introduction + body sections + conclusion)
3. For each section:
   a. Call `LLMProvider.stream_complete(section_prompt, on_token=stream_callback('section_stream', token))`
4. Assemble full essay
5. Run `ContentValidator.score()` (optional, if `validator` was injected)
6. Run `Dedup.check_and_store(source_hash)`

### Podcast Pipeline

`PodcastOutlineGenerator.generate(speaker_profile, guest_profile, episode_context)`

1. Single `LLMProvider.complete()` call with structured prompt
2. Returns JSON outline with segments, talking points, and show notes

---

## 9. Streaming Protocol

Long-form video and essay generation use **Server-Sent Events (SSE)**.

### Response Headers

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Important:** Nginx must be configured with `proxy_buffering off` for SSE to work through a reverse proxy.

### Event Types

| Event | Direction | Payload |
|---|---|---|
| `outline` | Server → Client | `{"sections": [...]}` |
| `section_start` | Server → Client | `{"section_index": N, "section_title": "..."}` |
| `section_stream` | Server → Client | `{"text": "token-text"}` |
| `section_complete` | Server → Client | `{"section_index": N, "word_count": N}` |
| `complete` | Server → Client | Full result object with `script_id` / `essay_id` |
| `error` | Server → Client | `{"message": "..."}` |

### SSE Wire Format

```
event: section_stream
data: {"text": "This is the content"}

event: complete
data: {"success": true, "script_id": "uuid", ...}

```

Each event block is followed by a blank line. The `complete` event carries the full result object; the client should use this to extract `script_id` / `essay_id` for subsequent retrieval.

---

## 10. Error Patterns

### Standard Error Response

All errors return JSON:

```json
{"error": "Human-readable description"}
```

### HTTP Status Code Reference

| Code | Meaning | Common causes |
|---|---|---|
| 400 | Bad Request | Missing required fields, invalid field values |
| 401 | Unauthorized | Missing/expired/invalid JWT, invalid webhook signature |
| 403 | Forbidden | Accessing another user's resource, essay feature not enabled |
| 404 | Not Found | Script/essay not found for this user |
| 409 | Conflict | Email or username already registered |
| 500 | Internal Server Error | LLM API error, DB error, S3 error |
| 503 | Service Unavailable | Curriculum registry not configured |

### Auth Errors

`AuthError` is raised by `features/auth.py` for:
- Token expired: `"Token expired"`
- Invalid token: `"Invalid token"`
- User not found: `"User not found"`
- Invalid password: `"Invalid credentials"`
- Duplicate email: `"Email already registered"`

---

## 11. Extension Points

### Adding a New LLM Provider

1. Subclass `LLMProvider` in `features/llm_provider.py`
2. Implement `complete()` and optionally `stream_complete()`
3. Add a new branch in `get_provider()`:

```python
if name == "myprovider":
    api_key = os.getenv("LLM_API_KEY") or os.getenv("MYPROVIDER_API_KEY", "")
    model = os.getenv("LLM_MODEL") or os.getenv("MYPROVIDER_MODEL", "default-model")
    return MyProvider(api_key, model)
```

4. Document the new env vars in `.env.example`

### Adding a New Curriculum

1. Add an entry to `curricula/registry.json`
2. Upload curriculum data files to S3 following the `s3_path_template`
3. Pass `curriculum_id` in `/api/generate` requests

### Adding a New Content Type

1. Create `features/my_generator.py` with a class that accepts `provider: LLMProvider`
2. Add routes in `api_endpoints.py`
3. Wire the new class in `app.py` and pass it to `register_all_routes()`

### Adding a New Route Group (Blueprint)

1. Create `features/my_feature.py` with:

```python
from flask import Blueprint

bp = Blueprint('my_feature', __name__, url_prefix='/api/my-feature')

@bp.route('/action', methods=['POST'])
def my_action():
    ...
```

2. Register in `features/__init__.py`:

```python
from features.my_feature import bp as my_feature_bp
app.register_blueprint(my_feature_bp)
```

### Adding a Database Table

Add the `CREATE TABLE IF NOT EXISTS` statement to `DB.init_tables()` in `features/database.py`. The table is created automatically on next startup. For adding columns to existing tables, use the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern already used throughout the file.
