"""
features/yt_analytics.py
YouTube Analytics Engine (v16) — FIXED FOR ACTUAL SCHEMA
Saves engagement metrics and computes weighted performance scores.
Uses video_performance table (not youtube_analytics).
"""

import uuid
import logging
from datetime import datetime
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Computes YouTube performance metrics with channel-size weighting.
    Smaller channels get proportionally higher scores for the same view counts,
    making the self-improvement loop fair across teachers of different sizes.
    """

    @staticmethod
    def calculate_engagement_rate(
        views: int,
        likes: int,
        comments: int,
        shares: int
    ) -> float:
        """
        Weighted engagement rate as a percentage of views.

        Weights:
            likes    × 1
            comments × 2  (higher intent signal)
            shares   × 3  (highest intent signal)

        Returns:
            Float capped at 100.0
        """
        if views == 0:
            return 0.0
        return min((likes + comments * 2 + shares * 3) / views * 100, 100.0)

    @staticmethod
    def calculate_weighted_view_score(views: int, channel_subscribers: int) -> float:
        """
        Normalize view count by channel size.
        A teacher with 500 subs getting 200 views outperforms
        a teacher with 50k subs getting the same 200 views.

        Returns:
            Float (views / subscribers × 100)
        """
        if channel_subscribers == 0:
            return 0.0
        return (views / max(channel_subscribers, 1)) * 100


class YtAnalyticsStore:
    """Persistence layer for YouTube analytics records."""

    def __init__(self, db):
        """
        Args:
            db: features.database.DB instance
        """
        self.db = db

    def save(
        self,
        video_id: str,
        views: int,
        channel_subscribers: int,
        likes: int,
        comments: int,
        shares: int,
    ):
        """
        Compute metrics and insert/update video_performance record.
        
        Args:
            video_id: UUID of published_videos.id
            views: view count from YouTube
            channel_subscribers: teacher's current subscriber count
            likes: like count from YouTube
            comments: comment count from YouTube
            shares: share count (if available, else 0)
        
        Returns:
            True on success, False on failure
        """
        conn = self.db.get_connection()
        if not conn:
            logger.error("Failed to get database connection")
            return False

        try:
            cur = conn.cursor()
            engagement_rate = AnalyticsEngine.calculate_engagement_rate(
                views, likes, comments, shares
            )
            weighted_score = AnalyticsEngine.calculate_weighted_view_score(
                views, channel_subscribers
            )
            
            # Calculate CTR (Click-Through Rate) - estimated from engagement
            ctr = (likes / max(views, 1)) * 100 if views > 0 else 0
            
            # Average retention - estimate from weighted score (placeholder)
            average_retention = min(weighted_score * 0.5, 100.0)  # Rough estimate

            # Insert into video_performance table
            cur.execute("""
                INSERT INTO video_performance (
                    id, video_id, measured_date, 
                    views, likes, comments, shares,
                    engagement_rate, ctr, average_retention
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (video_id) DO UPDATE SET
                    measured_date = EXCLUDED.measured_date,
                    views = EXCLUDED.views,
                    likes = EXCLUDED.likes,
                    comments = EXCLUDED.comments,
                    shares = EXCLUDED.shares,
                    engagement_rate = EXCLUDED.engagement_rate,
                    ctr = EXCLUDED.ctr,
                    average_retention = EXCLUDED.average_retention
            """, (
                str(uuid.uuid4()),  # id
                video_id,  # video_id (FK to published_videos.id)
                datetime.now(),  # measured_date
                views,
                likes,
                comments,
                shares,
                engagement_rate,
                ctr,
                average_retention,
            ))

            conn.commit()
            logger.info(f"Analytics saved: video {video_id} - {views} views, {engagement_rate:.2f}% engagement")
            return True

        except Exception as e:
            logger.error(f"Save analytics error: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            cur.close()
            conn.close()

    def get_video_analytics(self, video_id: str):
        """
        Retrieve analytics for a specific video.
        
        Args:
            video_id: UUID of published_videos.id
        
        Returns:
            Dict with analytics data, or None
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    id, video_id, measured_date,
                    views, likes, comments, shares,
                    engagement_rate, ctr, average_retention
                FROM video_performance
                WHERE video_id = %s
                ORDER BY measured_date DESC
                LIMIT 1
            """, (video_id,))
            
            result = cur.fetchone()
            cur.close()
            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Get video analytics error: {e}")
            return None
        finally:
            conn.close()

    def get_teacher_analytics(self, teacher_id: str):
        """
        Retrieve all analytics for a teacher's videos.
        
        Args:
            teacher_id: UUID of teacher
        
        Returns:
            List of dicts with analytics for each video
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    vp.id, vp.video_id, vp.measured_date,
                    vp.views, vp.likes, vp.comments, vp.shares,
                    vp.engagement_rate, vp.ctr, vp.average_retention,
                    gs.subject, gs.topic,
                    gs.word_count
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE gs.teacher_id = %s
                ORDER BY vp.measured_date DESC
            """, (teacher_id,))
            
            results = cur.fetchall()
            cur.close()
            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Get teacher analytics error: {e}")
            return []
        finally:
            conn.close()

    def get_top_videos(self, teacher_id: str, limit: int = 10):
        """
        Get teacher's top performing videos by engagement rate.
        
        Args:
            teacher_id: UUID of teacher
            limit: number of results
        
        Returns:
            List of top videos sorted by engagement_rate DESC
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    vp.id, vp.video_id, vp.measured_date,
                    vp.views, vp.likes, vp.comments, vp.shares,
                    vp.engagement_rate, vp.ctr, vp.average_retention,
                    gs.subject, gs.topic, gs.youtube_url
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE gs.teacher_id = %s
                ORDER BY vp.engagement_rate DESC
                LIMIT %s
            """, (teacher_id, limit))
            
            results = cur.fetchall()
            cur.close()
            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Get top videos error: {e}")
            return []
        finally:
            conn.close()
