# Architecture

## System Overview

Kaplen is a single-process Flask application. It follows a strict **layered dependency graph** so that each feature class knows only about the things it directly uses — there is no god object and no circular imports.

```
┌─────────────────────────────────────────────────────┐
│                  Browser / API Client                │
└─────────────────────────┬───────────────────────────┘
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────┐
│                  Flask (app.py)                      │
│   CORS · JWT middleware · Security headers          │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │    api_endpoints.py     │  45 routes, all registered here
        └────────────┬────────────┘
                     │ injects dependencies
        ┌────────────▼──────────────────────────────┐
        │              Feature Layer                 │
        │                                           │
        │  Layer 2 (generators)                     │
        │  ┌──────────────────────────────────────┐ │
        │  │ ScriptGenerator                      │ │
        │  │ LongFormVideoGenerator               │ │
        │  │ EssayGenerator                       │ │
        │  │ PodcastOutlineGenerator              │ │
        │  │ StudyTipsGenerator                   │ │
        │  │ DocxExporter                         │ │
        │  └──────────────────────────────────────┘ │
        │                                           │
        │  Layer 1 (tools)                          │
        │  ┌──────────────────────────────────────┐ │
        │  │ LLMProvider (abstraction)             │ │
        │  │  ├── AnthropicProvider                │ │
        │  │  └── OpenAIProvider                   │ │
        │  │ CallawayFramework                     │ │
        │  │ YoutubePackager                       │ │
        │  │ ContentValidator                      │ │
        │  │ DataLoader (S3)                       │ │
        │  │ CurriculumRegistry / CurriculumLoader │ │
        │  │ ScriptStore / YtAnalyticsStore        │ │
        │  │ MetricsEngine                         │ │
        │  │ YouTubeOAuthManager                   │ │
        │  │ YouTubeAPIFetcher                     │ │
        │  └──────────────────────────────────────┘ │
        │                                           │
        │  Layer 0 (infrastructure)                 │
        │  ┌──────────────────────────────────────┐ │
        │  │ DB (psycopg2)                        │ │
        │  │ Dedup                                 │ │
        │  └──────────────────────────────────────┘ │
        └───────────────────────────────────────────┘
                     │              │
              ┌──────▼──────┐  ┌───▼──────┐
              │ PostgreSQL  │  │ AWS S3   │
              └─────────────┘  └──────────┘
```

## Layer Model

### Layer 0 — Infrastructure

| Class | File | Responsibility |
|---|---|---|
| `DB` | `features/database.py` | psycopg2 connection pool, table auto-creation |
| `Dedup` | `features/dedup.py` | MD5 content hash + semantic hash deduplication |

### Layer 1 — Tools

| Class | File | Responsibility |
|---|---|---|
| `LLMProvider` | `features/llm_provider.py` | Abstract base: `complete()`, `stream_complete()` |
| `AnthropicProvider` | `features/llm_provider.py` | Anthropic SDK implementation |
| `OpenAIProvider` | `features/llm_provider.py` | OpenAI / compatible endpoint implementation |
| `CallawayFramework` | `features/callaway.py` | Story direction, lens, narrative beats, rhythm |
| `YoutubePackager` | `features/youtube_packager.py` | Hook archetypes, title variants, thumbnail prompts |
| `ContentValidator` | `features/validator.py` | Curriculum-coverage scoring (0.0–1.0) |
| `DataLoader` | `features/data_loader.py` | Loads subject/topic/subtopic data from S3 |
| `CurriculumRegistry` | `features/curriculum_loader.py` | Parses `curricula/registry.json` |
| `CurriculumLoader` | `features/curriculum_loader.py` | Resolves S3 paths from curriculum path templates |
| `ScriptStore` | `features/script_store.py` | CRUD for `generated_scripts` + `teachers` tables |
| `YtAnalyticsStore` | `features/yt_analytics.py` | Saves YouTube engagement metrics |
| `MetricsEngine` | `features/metrics.py` | Aggregated improvement metrics, top-N scripts |
| `YouTubeOAuthManager` | `features/youtube_oauth_manager.py` | Google OAuth2 flow, CSRF state tokens, token storage |
| `YouTubeAPIFetcher` | `features/youtube_api_fetcher.py` | YouTube Data API v3 calls (metrics, channel videos) |

### Layer 2 — Generators

| Class | File | Responsibility |
|---|---|---|
| `ScriptGenerator` | `features/script_generator.py` | Standard curriculum-aligned YouTube scripts |
| `LongFormVideoGenerator` | `features/long_form_generator.py` | Streaming 1hr/3hr deep-dive scripts |
| `EssayGenerator` | `features/essay_generator.py` | Chunked ingestion + structured essay generation |
| `PodcastOutlineGenerator` | `features/podcast_generator.py` | Multi-segment podcast outlines |
| `StudyTipsGenerator` | `features/study_tips.py` | Motivational/study-skill scripts |
| `DocxExporter` | `features/docx_export.py` | Renders any script as a Word document |

## LLM Provider Abstraction

All generators depend on `LLMProvider`, not on any vendor SDK directly. This means swapping LLM vendors requires only `.env` changes.

```python
class LLMProvider:
    def complete(self, messages: list[dict], max_tokens: int = 2000) -> str:
        raise NotImplementedError

    def stream_complete(self, messages, max_tokens=2000, on_token=None) -> str:
        # Default: calls complete(), then fires on_token once
        # Subclasses override for real token-by-token streaming
        ...
```

`get_provider()` is the factory — it reads `LLM_PROVIDER` from the environment and returns the correct subclass. All vendor SDK imports (`import anthropic`, `import openai`) are deferred inside `__init__` so installing only one SDK is sufficient.

## Content Generation Pipeline

### Standard Script

```
POST /api/generate
        │
        ├─ CurriculumLoader.resolve_s3_key(curriculum_id, path_args)
        ├─ DataLoader.load_topic_data(s3_key)          ← fetch from S3
        ├─ CallawayFramework.get_direction(topic)      ← story direction
        ├─ CallawayFramework.get_lens(direction)       ← narrative lens
        ├─ YoutubePackager.generate_hook(topic, arch)  ← opening hook
        ├─ LLMProvider.complete([prompt])              ← main script
        ├─ YoutubePackager.generate_title(script)      ← title variants
        ├─ YoutubePackager.generate_thumbnail(script)  ← thumbnail prompt
        ├─ ContentValidator.score(script, curriculum)  ← coverage check
        ├─ CallawayFramework.analyze_beats(script)     ← beat analysis
        └─ Dedup.check_and_store(content_hash)         ← dedup
```

### Long-Form Video

Generates section-by-section with streaming via `LLMProvider.stream_complete(on_token=callback)`. Each section token is pushed to the client via Server-Sent Events. Final assembled document is stored in S3.

### Essay

1. Client uploads source material in chunks via `POST /api/essay/ingest-chunk`
2. Chunks are assembled in S3
3. `POST /api/essay/generate` triggers `EssayGenerator.generate()` which calls `stream_complete()` per section

## Authentication & Authorization

```
Authorization: Bearer <jwt-token>
```

JWT payload:
```json
{
  "creator_id": "<uuid>",   // canonical user identity
  "teacher_id": "<uuid>",   // backward-compat alias (same UUID)
  "exp": 1234567890
}
```

Decorators in `features/auth.py`:
- `@require_jwt` — decodes token, sets `request.user_id` / `request.teacher_id`
- `@require_admin` — additionally checks `users.role = 'admin'`
- `@require_active_subscription` — checks `users.subscription_status = 'active'`

Passwords are hashed with bcrypt. Tokens are signed with `JWT_SECRET` (HS256, 7-day expiry).

## YouTube OAuth Flow

```
Teacher browser                  Kaplen API            Google OAuth
      │                               │                      │
      │  GET /api/teacher/youtube/auth-url                   │
      │──────────────────────────────►│                      │
      │  ◄── { auth_url, state }      │                      │
      │                               │                      │
      │  redirect to auth_url ────────────────────────────► │
      │                               │                      │
      │  ◄─────────────────────── callback with code+state ─│
      │  GET /api/teacher/youtube/oauth-callback             │
      │──────────────────────────────►│                      │
      │                               │  exchange code ─────►│
      │                               │  ◄── access_token    │
      │                               │                      │
      │  ◄── redirect /dashboard?youtube=connected           │
```

CSRF protection: `oauth_states` table stores one-time `state` tokens with 10-minute TTL. The callback validates the state before accepting the OAuth code.

## Database Schema

12 tables — all created automatically by `DB.init_tables()` on startup. Foreign key graph:

```
organizations
    └── users
            └── content_creators
            └── teachers
                    └── generated_scripts
                    │       └── youtube_analytics
                    │       └── essays
                    │       └── published_videos
                    │               └── video_performance
                    └── payments
oauth_states  (standalone)
centers       (standalone, referenced by teachers + generated_scripts)
```

Full column details: [SPEC.md § Database Schema](SPEC.md#database-schema).

## Security

- Passwords: bcrypt (cost 12)
- JWT: HS256, `JWT_SECRET` from env, 7-day expiry
- Webhook signatures: HMAC-SHA256 (`WAYL_WEBHOOK_SECRET`)
- HTTPS redirect: enforced in production by `setup_https_redirect()`
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, `X-XSS-Protection` via `setup_security_headers()`
- No secrets in source code — all from `.env`

## Feature Blueprints

Four feature modules register Flask Blueprints via `features/__init__.py`:

| Blueprint prefix | Module | Status |
|---|---|---|
| `/api/teachers/synthesis/` | `features/synthesis.py` | Active — transcript synthesis |
| `/api/teachers/analytics/` | `features/analytics.py` | Stub |
| `/api/teachers/batch/` | `features/batch.py` | Stub |
| `/api/teachers/timeline/` | `features/timeline.py` | Stub |
