"""
features/metrics.py
Improvement Metrics — Self-Improvement Loop
Aggregates YouTube analytics per teacher AND platform-wide.
Platform-wide patterns feed into every script generation call.
"""

import logging
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class MetricsEngine:
    """
    Reads aggregated YouTube performance data.
    Two modes:
        1. Per-teacher: dashboard metrics, top scripts
        2. Platform-wide: extracts winning patterns across ALL teachers
           to feed into the self-improvement loop
    """

    def __init__(self, db):
        """
        Args:
            db: features.database.DB instance
        """
        self.db = db

    # ══════════════════════════════════════════════════════════════
    # PER-TEACHER METRICS
    # ══════════════════════════════════════════════════════════════

    def get_improvement_metrics(self, teacher_id: str) -> dict | None:
        """
        Aggregate analytics for a teacher across all their scripts.

        Returns:
            {teacher_id, total_scripts, avg_views, avg_engagement_rate, best_weighted_score}
            or None on failure.
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT
                    COUNT(*)                AS total_scripts,
                    AVG(vp.views)           AS avg_views,
                    AVG(vp.engagement_rate) AS avg_engagement,
                    MAX(vp.engagement_rate) AS best_score
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE gs.teacher_id = %s
            """, (teacher_id,))

            result = cur.fetchone()
            if not result:
                return None

            return {
                'teacher_id':          teacher_id,
                'total_scripts':       int(result['total_scripts'] or 0),
                'avg_views':           float(result['avg_views'] or 0),
                'avg_engagement_rate': float(result['avg_engagement'] or 0),
                'best_weighted_score': float(result['best_score'] or 0),
            }

        except Exception as e:
            logger.error(f"Get metrics error: {e}")
            return None
        finally:
            conn.close()

    def get_top_scripts(self, teacher_id: str, limit: int = 5) -> list[dict]:
        """
        Return the top N scripts for a teacher ranked by engagement_rate.

        Returns:
            List of {script_id, views, engagement_rate, measured_date}
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT gs.id AS script_id, vp.views, vp.engagement_rate, vp.measured_date
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE gs.teacher_id = %s
                ORDER BY vp.engagement_rate DESC
                LIMIT %s
            """, (teacher_id, limit))

            rows = cur.fetchall()
            result = []
            for row in rows:
                r = dict(row)
                if r.get('script_id'):
                    r['script_id'] = str(r['script_id'])
                if r.get('measured_date'):
                    r['measured_date'] = r['measured_date'].isoformat()
                result.append(r)
            return result

        except Exception as e:
            logger.error(f"Get top scripts error: {e}")
            return []
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════
    # PLATFORM-WIDE PATTERNS (Self-Improvement Loop)
    # ══════════════════════════════════════════════════════════════

    def get_platform_winning_patterns(self, limit: int = 20) -> dict:
        """
        Extract patterns from the highest-performing scripts across ALL teachers.
        This is the core of the self-improvement loop: every new script
        benefits from what worked across the entire platform.

        Queries the top N scripts by engagement_rate, then aggregates:
            - Which hook archetypes perform best
            - Which subjects/topics get highest engagement
            - Average word count of top performers
            - Callaway direction/lens patterns that win

        Returns:
            {
                'has_data': bool,
                'total_tracked_scripts': int,
                'platform_avg_engagement': float,
                'top_hook_archetypes': [{'archetype': str, 'avg_engagement': float, 'count': int}],
                'top_subjects': [{'subject': str, 'avg_engagement': float, 'count': int}],
                'winning_word_count': {'avg': float, 'min': int, 'max': int},
                'top_scripts': [{'subject', 'topic', 'hook_archetype', 'word_count',
                                 'callaway_direction', 'callaway_lens', 'engagement_rate', 'views'}],
            }
        """
        conn = self.db.get_connection()
        if not conn:
            return {'has_data': False}

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 1. Platform-wide averages
            cur.execute("""
                SELECT
                    COUNT(*)                AS total,
                    AVG(vp.engagement_rate) AS avg_engagement
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE vp.views > 0
            """)
            totals = cur.fetchone()
            total_tracked = int(totals['total'] or 0) if totals else 0

            if total_tracked == 0:
                return {'has_data': False, 'total_tracked_scripts': 0}

            platform_avg = float(totals['avg_engagement'] or 0)

            # 2. Top hook archetypes by avg engagement
            cur.execute("""
                SELECT
                    gs.hook_archetype                AS archetype,
                    AVG(vp.engagement_rate)          AS avg_engagement,
                    COUNT(*)                         AS cnt
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE vp.views > 0
                  AND gs.hook_archetype IS NOT NULL
                  AND gs.hook_archetype != ''
                GROUP BY gs.hook_archetype
                ORDER BY avg_engagement DESC
            """)
            hook_rows = cur.fetchall()
            top_hooks = [
                {'archetype': r['archetype'], 'avg_engagement': round(float(r['avg_engagement']), 2), 'count': int(r['cnt'])}
                for r in hook_rows
            ]

            # 3. Top subjects by avg engagement
            cur.execute("""
                SELECT
                    gs.subject                       AS subject,
                    AVG(vp.engagement_rate)           AS avg_engagement,
                    COUNT(*)                          AS cnt
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE vp.views > 0
                  AND gs.subject IS NOT NULL
                GROUP BY gs.subject
                ORDER BY avg_engagement DESC
            """)
            subject_rows = cur.fetchall()
            top_subjects = [
                {'subject': r['subject'], 'avg_engagement': round(float(r['avg_engagement']), 2), 'count': int(r['cnt'])}
                for r in subject_rows
            ]

            # 4. Word count stats of top performers (above-average engagement)
            cur.execute("""
                SELECT
                    AVG(gs.word_count) AS avg_wc,
                    MIN(gs.word_count) AS min_wc,
                    MAX(gs.word_count) AS max_wc
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE vp.views > 0
                  AND vp.engagement_rate > %s
                  AND gs.word_count IS NOT NULL
                  AND gs.word_count > 0
            """, (platform_avg,))
            wc_row = cur.fetchone()
            winning_wc = {
                'avg': round(float(wc_row['avg_wc'] or 0)),
                'min': int(wc_row['min_wc'] or 0),
                'max': int(wc_row['max_wc'] or 0),
            } if wc_row else {'avg': 0, 'min': 0, 'max': 0}

            # 5. Top N individual scripts with full metadata
            cur.execute("""
                SELECT
                    gs.subject,
                    gs.topic,
                    gs.subtopic,
                    gs.hook_archetype,
                    gs.word_count,
                    gs.callaway_direction,
                    gs.callaway_lens,
                    vp.engagement_rate,
                    vp.views
                FROM video_performance vp
                JOIN published_videos pv ON vp.video_id = pv.id
                JOIN generated_scripts gs ON pv.script_id = gs.id
                WHERE vp.views > 0
                ORDER BY vp.engagement_rate DESC
                LIMIT %s
            """, (limit,))
            top_rows = cur.fetchall()
            top_scripts = []
            for r in top_rows:
                top_scripts.append({
                    'subject':             r['subject'],
                    'topic':               r['topic'],
                    'subtopic':            r['subtopic'],
                    'hook_archetype':      r['hook_archetype'],
                    'word_count':          int(r['word_count'] or 0),
                    'callaway_direction':  r['callaway_direction'] or '',
                    'callaway_lens':       r['callaway_lens'] or '',
                    'engagement_rate':     round(float(r['engagement_rate']), 2),
                    'views':               int(r['views'] or 0),
                })

            return {
                'has_data':                True,
                'total_tracked_scripts':   total_tracked,
                'platform_avg_engagement': round(platform_avg, 2),
                'top_hook_archetypes':     top_hooks,
                'top_subjects':            top_subjects,
                'winning_word_count':      winning_wc,
                'top_scripts':             top_scripts,
            }

        except Exception as e:
            logger.error(f"Get platform patterns error: {e}", exc_info=True)
            return {'has_data': False}
        finally:
            conn.close()

    def get_platform_prompt_context(self, limit: int = 10) -> str:
        """
        Returns a plain-text summary of platform winning patterns,
        ready to inject directly into a Claude prompt.

        If no data exists yet, returns empty string (no impact on generation).
        """
        patterns = self.get_platform_winning_patterns(limit=limit)

        if not patterns.get('has_data'):
            return ''

        lines = []
        lines.append("=== PLATFORM PERFORMANCE DATA (use this to improve the script) ===")
        lines.append(f"Total tracked scripts: {patterns['total_tracked_scripts']}")
        lines.append(f"Platform avg engagement rate: {patterns['platform_avg_engagement']}%")
        lines.append("")

        # Hook archetypes
        if patterns.get('top_hook_archetypes'):
            lines.append("Best-performing hook archetypes:")
            for h in patterns['top_hook_archetypes'][:5]:
                lines.append(f"  - {h['archetype']}: {h['avg_engagement']}% avg engagement ({h['count']} scripts)")
            lines.append("")

        # Subjects
        if patterns.get('top_subjects'):
            lines.append("Highest-engagement subjects:")
            for s in patterns['top_subjects'][:5]:
                lines.append(f"  - {s['subject']}: {s['avg_engagement']}% avg engagement ({s['count']} scripts)")
            lines.append("")

        # Word count
        wc = patterns.get('winning_word_count', {})
        if wc.get('avg'):
            lines.append(f"Top-performing scripts word count: avg {wc['avg']}, range {wc['min']}-{wc['max']}")
            lines.append("")

        # Top scripts — show patterns
        if patterns.get('top_scripts'):
            lines.append("Top-performing scripts on this platform:")
            for i, s in enumerate(patterns['top_scripts'][:5], 1):
                lines.append(f"  {i}. {s['subject']}/{s['topic']} — hook: {s['hook_archetype']}, "
                             f"{s['word_count']} words, {s['engagement_rate']}% engagement, "
                             f"{s['views']} views")
                if s.get('callaway_direction'):
                    lines.append(f"     Direction: {s['callaway_direction'][:80]}")
                if s.get('callaway_lens'):
                    lines.append(f"     Lens: {s['callaway_lens'][:80]}")
            lines.append("")

        lines.append("Use these patterns to make this script perform better than the platform average.")
        lines.append("=== END PLATFORM DATA ===")

        return '\n'.join(lines)
