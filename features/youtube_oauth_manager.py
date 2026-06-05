"""
features/youtube_oauth_manager.py
Per-Teacher YouTube OAuth Manager
Handles OAuth flow, token storage, and refresh for each teacher.
"""

import os
import json
import logging
from datetime import datetime, timedelta
import secrets

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# YouTube OAuth configuration
YOUTUBE_CLIENT_ID = os.getenv('YOUTUBE_CLIENT_ID', '')
YOUTUBE_CLIENT_SECRET = os.getenv('YOUTUBE_CLIENT_SECRET', '')
YOUTUBE_REDIRECT_URI = os.getenv('YOUTUBE_OAUTH_REDIRECT_URI', '')

SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',  # Read-only access to channel analytics
    'https://www.googleapis.com/auth/yt-analytics.readonly',  # YouTube Analytics API
]


class YouTubeOAuthManager:
    """Manages per-teacher YouTube OAuth authentication."""

    def __init__(self, db):
        """
        Args:
            db: features.database.DB instance
        """
        self.db = db

    def get_authorization_url(self, teacher_id: str) -> tuple[str, str]:
        """
        Generate YouTube OAuth authorization URL for a teacher.
        
        Args:
            teacher_id: UUID of teacher
        
        Returns:
            (authorization_url, state_token) tuple
        """
        if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
            logger.error("YouTube OAuth credentials not configured")
            return None, None

        try:
            # Create OAuth flow
            flow = Flow.from_client_config(
                {
                    "installed": {
                        "client_id": YOUTUBE_CLIENT_ID,
                        "client_secret": YOUTUBE_CLIENT_SECRET,
                        "redirect_uris": [YOUTUBE_REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=SCOPES
            )
            
            flow.redirect_uri = YOUTUBE_REDIRECT_URI
            
            # Generate state token (for security)
            state = secrets.token_urlsafe(32)
            
            # Store state in database temporarily (expires in 10 minutes)
            self._store_oauth_state(teacher_id, state)
            
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=state,
                login_hint=f'teacher_{teacher_id}'
            )
            
            logger.info(f"OAuth URL generated for teacher {teacher_id}")
            return authorization_url, state

        except Exception as e:
            logger.error(f"OAuth URL generation error: {e}")
            return None, None

    def handle_oauth_callback(self, teacher_id: str, code: str, state: str) -> bool:
        """
        Handle OAuth callback - exchange code for tokens.
        
        Args:
            teacher_id: UUID of teacher
            code: Authorization code from Google
            state: State token for security
        
        Returns:
            True on success, False on failure
        """
        if not self._verify_oauth_state(teacher_id, state):
            logger.warning(f"Invalid OAuth state for teacher {teacher_id}")
            return False

        try:
            # Create OAuth flow
            flow = Flow.from_client_config(
                {
                    "installed": {
                        "client_id": YOUTUBE_CLIENT_ID,
                        "client_secret": YOUTUBE_CLIENT_SECRET,
                        "redirect_uris": [YOUTUBE_REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=SCOPES,
                state=state
            )
            
            flow.redirect_uri = YOUTUBE_REDIRECT_URI
            
            # Exchange code for tokens
            credentials = flow.fetch_token(code=code)
            
            # Store tokens in database
            self._save_credentials(teacher_id, credentials)
            
            logger.info(f"OAuth tokens stored for teacher {teacher_id}")
            return True

        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            return False

    def get_credentials(self, teacher_id: str) -> Credentials or None:
        """
        Get valid credentials for a teacher (refresh if needed).
        
        Args:
            teacher_id: UUID of teacher
        
        Returns:
            google.oauth2.credentials.Credentials or None if not found/expired
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT youtube_oauth_token, youtube_oauth_refresh_token, youtube_oauth_token_expires_at
                FROM teachers
                WHERE id = %s
            """, (teacher_id,))
            
            row = cur.fetchone()
            cur.close()
            
            if not row:
                logger.warning(f"No OAuth credentials found for teacher {teacher_id}")
                return None
            
            token, refresh_token, expires_at = row
            
            if not token or not refresh_token:
                logger.warning(f"Incomplete OAuth credentials for teacher {teacher_id}")
                return None
            
            # Create credentials object
            credentials = Credentials(
                token=token,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=YOUTUBE_CLIENT_ID,
                client_secret=YOUTUBE_CLIENT_SECRET,
                scopes=SCOPES
            )
            
            # Refresh if expired
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                logger.info(f"Refreshing OAuth token for teacher {teacher_id}")
                request = Request()
                credentials.refresh(request)
                
                # Update stored token
                self._save_credentials(teacher_id, credentials)
            
            return credentials

        except Exception as e:
            logger.error(f"Get credentials error: {e}")
            return None
        finally:
            conn.close()

    def _save_credentials(self, teacher_id: str, credentials: dict or Credentials):
        """
        Save OAuth credentials to database.
        
        Args:
            teacher_id: UUID of teacher
            credentials: Dict or Credentials object with token info
        """
        conn = self.db.get_connection()
        if not conn:
            return

        try:
            cur = conn.cursor()
            
            # Extract token info
            if isinstance(credentials, dict):
                token = credentials.get('access_token')
                refresh_token = credentials.get('refresh_token')
                expires_in = credentials.get('expires_in', 3600)
            else:
                token = credentials.token
                refresh_token = credentials.refresh_token
                expires_in = 3600
            
            # Calculate expiry time
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            cur.execute("""
                UPDATE teachers
                SET 
                    youtube_oauth_token = %s,
                    youtube_oauth_refresh_token = %s,
                    youtube_oauth_token_expires_at = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (token, refresh_token, expires_at, teacher_id))
            
            conn.commit()
            logger.info(f"OAuth credentials saved for teacher {teacher_id}")

        except Exception as e:
            logger.error(f"Save credentials error: {e}")
        finally:
            cur.close()
            conn.close()

    def _store_oauth_state(self, teacher_id: str, state: str, ttl_minutes: int = 10):
        """
        Persist an OAuth state token to the oauth_states table for CSRF verification.
        """
        conn = self.db.get_connection()
        if not conn:
            return

        cur = None
        try:
            cur = conn.cursor()
            expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
            cur.execute("""
                INSERT INTO oauth_states (teacher_id, state, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (state) DO UPDATE
                    SET teacher_id = EXCLUDED.teacher_id,
                        expires_at = EXCLUDED.expires_at
            """, (teacher_id, state, expires_at))
            conn.commit()
            logger.info(f"OAuth state stored for teacher {teacher_id}, expires {expires_at.isoformat()}")
        except Exception as e:
            logger.error(f"Store state error: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            if cur:
                cur.close()
            conn.close()

    def _verify_oauth_state(self, teacher_id: str, state: str) -> bool:
        """
        Verify a one-time OAuth state token: it must exist, match the teacher,
        and not be expired. The token is consumed (deleted) on verification.
        """
        if not state:
            return False

        conn = self.db.get_connection()
        if not conn:
            return False

        cur = None
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM oauth_states
                WHERE state = %s AND teacher_id = %s AND expires_at > NOW()
                RETURNING state
            """, (state, teacher_id))
            row = cur.fetchone()
            conn.commit()
            if row:
                logger.info(f"OAuth state verified for teacher {teacher_id}")
                return True
            logger.warning(f"OAuth state invalid or expired for teacher {teacher_id}")
            return False
        except Exception as e:
            logger.error(f"Verify state error: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            if cur:
                cur.close()
            conn.close()

    def revoke_credentials(self, teacher_id: str) -> bool:
        """
        Revoke teacher's YouTube OAuth credentials.
        
        Args:
            teacher_id: UUID of teacher
        
        Returns:
            True on success, False on failure
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE teachers
                SET 
                    youtube_oauth_token = NULL,
                    youtube_oauth_refresh_token = NULL,
                    youtube_oauth_token_expires_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
            """, (teacher_id,))
            
            conn.commit()
            logger.info(f"OAuth credentials revoked for teacher {teacher_id}")
            return True

        except Exception as e:
            logger.error(f"Revoke credentials error: {e}")
            return False
        finally:
            cur.close()
            conn.close()
