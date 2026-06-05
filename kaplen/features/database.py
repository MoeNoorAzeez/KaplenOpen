"""
features/database.py
PostgreSQL Connection Manager
Handles connection pooling and table initialisation.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class DB:
    """PostgreSQL connection manager."""

    def __init__(
        self,
        host: str = None,
        database: str = None,
        user: str = None,
        password: str = None,
        port: int = None,
    ):
        self.host     = host     or os.getenv('DB_HOST')
        self.database = database or os.getenv('DB_NAME', 'kaplen')
        self.user     = user     or os.getenv('DB_USER', 'postgres')
        self.password = password or os.getenv('DB_PASSWORD', '')
        self.port     = port     or int(os.getenv('DB_PORT', '5432'))

    def get_connection(self):
        """Open and return a new psycopg2 connection. Caller must close it."""
        try:
            return psycopg2.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password,
                port=self.port,
            )
        except Exception as e:
            logger.error(f"DB connection error: {e}")
            return None

    def init_tables(self):
        """Create all required tables if they don't already exist."""
        conn = self.get_connection()
        if not conn:
            logger.error("Cannot initialize tables — database unavailable")
            return

        try:
            cur = conn.cursor()

            # ── Core ─────────────────────────────────────────────────────

            cur.execute("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) UNIQUE NOT NULL,
                    domain VARCHAR(255),
                    curriculum_id VARCHAR(100),
                    language VARCHAR(10) DEFAULT 'ar',
                    timezone VARCHAR(100) DEFAULT 'UTC',
                    config JSONB,
                    subscription_status VARCHAR(50) DEFAULT 'active',
                    subscription_expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'user',
                    organization_id UUID REFERENCES organizations(id),
                    creator_type VARCHAR(50) DEFAULT 'educator',
                    curriculum_context JSONB,
                    api_key VARCHAR(255),
                    subscription_status VARCHAR(50) DEFAULT 'pending',
                    subscription_expires_at TIMESTAMP,
                    is_essay_author BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Backward-compat: add new columns to existing users table
            for col_def in [
                "ADD COLUMN IF NOT EXISTS organization_id UUID",
                "ADD COLUMN IF NOT EXISTS creator_type VARCHAR(50) DEFAULT 'educator'",
                "ADD COLUMN IF NOT EXISTS curriculum_context JSONB",
                "ADD COLUMN IF NOT EXISTS api_key VARCHAR(255)",
            ]:
                try:
                    cur.execute(f"ALTER TABLE users {col_def}")
                except Exception:
                    pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS centers (
                    center_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL,
                    manager_email VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    teacher_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    center_id UUID REFERENCES centers(center_id),
                    youtube_api_key TEXT,
                    youtube_channel_id TEXT,
                    youtube_channel_name TEXT,
                    channel_subs INTEGER DEFAULT 0,
                    youtube_last_sync TIMESTAMP,
                    youtube_oauth_token TEXT,
                    youtube_oauth_refresh_token TEXT,
                    youtube_oauth_token_expires_at TEXT,
                    subscription_status VARCHAR(50) DEFAULT 'pending',
                    subscription_expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── content_creators: generalized profile (replaces teachers long-term) ──

            cur.execute("""
                CREATE TABLE IF NOT EXISTS content_creators (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id),
                    organization_id UUID REFERENCES organizations(id),
                    youtube_channel_id TEXT,
                    youtube_oauth_token TEXT,
                    linkedin_profile TEXT,
                    website TEXT,
                    bio TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Generated content ────────────────────────────────────────

            cur.execute("""
                CREATE TABLE IF NOT EXISTS generated_scripts (
                    script_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    teacher_id UUID REFERENCES teachers(teacher_id),
                    organization_id UUID REFERENCES organizations(id),
                    curriculum_id VARCHAR(100),
                    subject VARCHAR(255),
                    topic VARCHAR(255),
                    subtopic VARCHAR(255),
                    domain_category VARCHAR(255),
                    content_unit VARCHAR(255),
                    content_leaf VARCHAR(255),
                    domain_context JSONB,
                    title TEXT,
                    hook TEXT,
                    hook_archetype VARCHAR(50),
                    thumbnail_prompt TEXT,
                    script_content TEXT,
                    script_type VARCHAR(50) DEFAULT 'standard',
                    metadata JSONB,
                    outline JSONB,
                    callaway_direction JSONB,
                    callaway_lens JSONB,
                    callaway_beats JSONB,
                    content_hash VARCHAR(32),
                    semantic_hash VARCHAR(32),
                    quality_metrics JSONB,
                    word_count INTEGER,
                    status VARCHAR(50) DEFAULT 'draft',
                    center_id UUID REFERENCES centers(center_id),
                    youtube_url TEXT,
                    youtube_views INTEGER DEFAULT 0,
                    youtube_channel_subscribers INTEGER DEFAULT 1000,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Backward-compat: add new columns to existing generated_scripts table
            for col_def in [
                "ADD COLUMN IF NOT EXISTS organization_id UUID",
                "ADD COLUMN IF NOT EXISTS curriculum_id VARCHAR(100)",
                "ADD COLUMN IF NOT EXISTS domain_category VARCHAR(255)",
                "ADD COLUMN IF NOT EXISTS content_unit VARCHAR(255)",
                "ADD COLUMN IF NOT EXISTS content_leaf VARCHAR(255)",
                "ADD COLUMN IF NOT EXISTS domain_context JSONB",
            ]:
                try:
                    cur.execute(f"ALTER TABLE generated_scripts {col_def}")
                except Exception:
                    pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS essays (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id),
                    title TEXT NOT NULL,
                    content TEXT,
                    metadata JSONB,
                    status VARCHAR(50) DEFAULT 'draft',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS youtube_analytics (
                    analytics_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    script_id UUID REFERENCES generated_scripts(script_id),
                    teacher_id UUID REFERENCES teachers(teacher_id),
                    views INTEGER DEFAULT 0,
                    ctr FLOAT DEFAULT 0.0,
                    average_retention FLOAT DEFAULT 0.0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    engagement_rate FLOAT DEFAULT 0.0,
                    weighted_view_score FLOAT DEFAULT 0.0,
                    measured_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    teacher_id UUID REFERENCES teachers(teacher_id),
                    organization_id UUID REFERENCES organizations(id),
                    amount INTEGER,
                    currency VARCHAR(10) DEFAULT 'USD',
                    status VARCHAR(50),
                    transaction_id TEXT UNIQUE,
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            try:
                cur.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS organization_id UUID")
            except Exception:
                pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS published_videos (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    script_id UUID REFERENCES generated_scripts(script_id),
                    teacher_id UUID REFERENCES teachers(teacher_id),
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS video_performance (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    video_id UUID REFERENCES published_videos(id) UNIQUE,
                    measured_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    engagement_rate FLOAT DEFAULT 0.0,
                    ctr FLOAT DEFAULT 0.0,
                    average_retention FLOAT DEFAULT 0.0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    teacher_id UUID NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("Database tables initialized")

        except Exception as e:
            logger.warning(f"Table initialization warning: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# Module-level singleton
db = DB()
