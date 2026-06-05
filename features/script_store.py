"""
features/script_store.py
Script Persistence
Save, retrieve, and manage teacher/script records in PostgreSQL.
"""

import json
import uuid
import logging
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class ScriptStore:
    """CRUD operations for teachers and generated scripts."""

    def __init__(self, db):
        """
        Args:
            db: features.database.DB instance
        """
        self.db = db

    # ── Teachers ──────────────────────────────────────────────────────────

    def create_or_get_teacher(self, teacher_name: str, center_id: str = None) -> str | None:
        """
        Return existing teacher_id by name, or create a new record.

        Args:
            teacher_name: Display name of the teacher
            center_id:    Optional UUID of the center

        Returns:
            teacher_id string, or None on failure
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT teacher_id FROM teachers WHERE name = %s", (teacher_name,))
            result = cur.fetchone()

            if result:
                return str(result['teacher_id'])

            teacher_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO teachers (teacher_id, name, center_id) VALUES (%s, %s, %s)",
                (teacher_id, teacher_name, center_id)
            )
            conn.commit()
            logger.info(f"Created teacher: {teacher_id} ({teacher_name})")
            return teacher_id

        except Exception as e:
            logger.error(f"Create/get teacher error: {e}")
            return None
        finally:
            conn.close()

    # ── Scripts ───────────────────────────────────────────────────────────

    def save_script(
        self,
        teacher_id: str,
        subject: str,
        topic: str,
        subtopic: str,
        response: dict
    ) -> str | None:
        """
        Persist a generated script to the database.

        Args:
            teacher_id: UUID of the teacher
            subject:    e.g. 'chemistry'
            topic:      e.g. 'Atomic Structure'
            subtopic:   e.g. 'Electron Configuration'
            response:   Full dict returned by generate_complete_script()

        Returns:
            script_id string, or None on failure
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor()
            script_id = str(uuid.uuid4())

            cur.execute("""
                INSERT INTO generated_scripts (
                    script_id, teacher_id, subject, topic, subtopic,
                    title, hook, hook_archetype, thumbnail_prompt, script_content,
                    callaway_direction, callaway_lens, callaway_beats,
                    content_hash, semantic_hash, quality_metrics, word_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                script_id, teacher_id, subject, topic, subtopic,
                response.get('title'),
                response.get('hook'),
                response.get('hook_archetype'),
                response.get('thumbnail_prompt'),
                response.get('script_content'),
                json.dumps(response.get('callaway_direction')),
                json.dumps(response.get('callaway_lens')),
                json.dumps(response.get('callaway_beats')),
                '',  # content_hash (populated by dedup layer)
                '',  # semantic_hash (populated by dedup layer)
                json.dumps(response.get('validation', {})),
                response.get('word_count', 0),
            ))

            conn.commit()
            logger.info(f"Script saved: {script_id} for teacher {teacher_id}")
            return script_id

        except Exception as e:
            logger.error(f"Save script error: {e}")
            return None
        finally:
            conn.close()

    def get_scripts_by_teacher(self, teacher_id: str) -> list[dict]:
        """
        Fetch all scripts for a teacher, newest first.

        Returns:
            List of script dicts (UUIDs and datetimes serialized to strings)
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM generated_scripts WHERE teacher_id = %s ORDER BY created_at DESC",
                (teacher_id,)
            )
            rows = cur.fetchall()

            scripts = []
            for row in rows:
                s = dict(row)
                for key in ('script_id', 'teacher_id'):
                    if s.get(key):
                        s[key] = str(s[key])
                for key in ('created_at', 'updated_at'):
                    if s.get(key):
                        s[key] = s[key].isoformat()
                scripts.append(s)

            return scripts

        except Exception as e:
            logger.error(f"Get scripts error: {e}")
            return []
        finally:
            conn.close()

    def get_script_by_id(self, script_id: str) -> dict | None:
        """
        Fetch a single script by its UUID.

        Returns:
            Script dict, or None if not found
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM generated_scripts WHERE script_id = %s",
                (script_id,)
            )
            row = cur.fetchone()
            if not row:
                return None

            s = dict(row)
            for key in ('script_id', 'teacher_id'):
                if s.get(key):
                    s[key] = str(s[key])
            for key in ('created_at', 'updated_at'):
                if s.get(key):
                    s[key] = s[key].isoformat()
            return s

        except Exception as e:
            logger.error(f"Get script by id error: {e}")
            return None
        finally:
            conn.close()
