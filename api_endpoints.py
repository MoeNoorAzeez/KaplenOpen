"""
api_endpoints.py — All API Routes
Single entry point for every route the app exposes.

Called from app.py:
    from api_endpoints import register_all_routes
    register_all_routes(app, ...)

Route inventory:
    ── Public ──────────────────────────────────────────────────────────────
    GET  /api/health                    Full health check (DB + Claude API)
    GET  /api/status                    Quick liveness probe
    GET  /api/subjects                  List subjects
    GET  /api/topics/<subject>          List topics
    GET  /api/subtopics/<s>/<t>         List subtopics
    POST /api/generate-study-tips       Generate study tips script (no auth)
    POST /api/auth/signup               Register new user
    POST /api/auth/login                Login
    POST /api/auth/teacher              Legacy teacher login (by name)
    POST /api/payment/webhook           Wayl payment webhook

    ── Authenticated (JWT) ──────────────────────────────────────────────────
    GET  /api/auth/me                   Current user profile
    GET  /api/billing/status            Subscription status + last 12 payments
    GET  /api/billing/history           Full payment history
    GET  /api/analytics/<teacher_id>    Improvement metrics
    GET  /api/analytics/top/<t_id>      Top scripts by weighted score
    POST /api/analytics/save            Save YouTube engagement metrics
    GET  /api/scripts/<teacher_id>      List teacher's scripts
    GET  /api/export/<script_id>        Download script as DOCX

    ── Authenticated + Active Subscription ─────────────────────────────────
    POST /api/generate                  Generate curriculum script

    ── Admin ────────────────────────────────────────────────────────────────
    GET  /api/admin/teachers            List all teachers

    ── Center Dashboard ────────────────────────────────────────────────
    GET  /api/center/<center_id>/dashboard    Center stats & all teachers
    GET  /center-dashboard                     Center dashboard HTML

    ── Frontend ─────────────────────────────────────────────────────────────
    GET  /                              Landing page
    GET  /dashboard                     Dashboard HTML

    ── YouTube Analytics (Per-Teacher) ────────────────────────────────────
    GET  /api/teacher/youtube/auth-url              Get OAuth authorization URL
    GET  /api/teacher/youtube/oauth-callback        OAuth callback handler
    POST /api/teacher/youtube/sync-analytics        Sync single video metrics
    POST /api/teacher/youtube/sync-all-videos       Sync all channel videos
    POST /api/teacher/youtube/disconnect            Revoke YouTube access
    GET  /api/teacher/youtube/status                Check connection status

    ── Long-Form Videos (1hr / 3hr) ──────────────────────────────────────
    POST /api/generate-long-form             Generate long-form video (streaming)
    GET  /api/long-form/<script_id>          Retrieve long-form script
    GET  /api/long-form/export/<script_id>   Export as DOCX

    ── Essay Generator (Hidden, Premium) ──────────────────────────────────
    POST /api/essay/generate                 Generate essay from source material
    GET  /api/essay/<essay_id>               Retrieve generated essay
    GET  /api/essay/<essay_id>/export        Export essay (DOCX/MD)
    GET  /api/essays                         List all user essays

    ── Feature Blueprints (registered via features/__init__.py) ─────────────
    /api/teachers/synthesis/*           Transcript synthesis (streaming)
    /api/teachers/analytics/*           Analytics (stub)
    /api/teachers/batch/*               Batch generation (stub)
    /api/teachers/timeline/*            Timeline (stub)
"""

import os
import uuid
import logging
import traceback

from flask import jsonify, request

from features.auth     import require_jwt, require_admin, signup_user, login_user, get_current_user, AuthError
from features.payments import handle_wayl_webhook, verify_wayl_webhook_signature, get_billing_status, get_payment_history
from features.security import validate_email, validate_password, validate_username, setup_security_headers, setup_https_redirect
from features.health   import get_full_health_check, get_quick_health_check
from features          import register_features
from features.payments import require_active_subscription

logger = logging.getLogger(__name__)


def register_all_routes(app, data_loader, script_generator, study_tips_generator,
                        script_store, yt_store, metrics, docx_exporter, scripts_cache,
                        long_form_gen=None, s3_client=None, bucket=None,
                        llm_provider=None, validator=None, dedup=None,
                        curriculum_registry=None, curriculum_loader=None, config=None,
                        # backward-compat aliases — ignored if llm_provider is set
                        anthropic_client=None, model=None):
    """
    Register every route with the Flask app.

    Args:
        app:                  Flask app instance
        data_loader:          features.data_loader.DataLoader
        script_generator:     features.script_generator.ScriptGenerator
        study_tips_generator: features.study_tips.StudyTipsGenerator
        script_store:         features.script_store.ScriptStore
        yt_store:             features.yt_analytics.YtAnalyticsStore
        metrics:              features.metrics.MetricsEngine
        docx_exporter:        features.docx_export.DocxExporter
        scripts_cache:        dict — shared in-memory {script_id: script_data}
    """

    # Security middleware
    setup_https_redirect(app)
    setup_security_headers(app)

    # Feature blueprints (synthesis, analytics, batch, timeline)
    register_features(app)

    # ════════════════════════════════════════════════════════════════════
    # HEALTH
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Full health check — DB + Claude API."""
        return jsonify(get_full_health_check()), 200

    @app.route('/api/status', methods=['GET'])
    def quick_status():
        """Fast liveness probe — no external calls."""
        return jsonify(get_quick_health_check()), 200

    # ════════════════════════════════════════════════════════════════════
    # CURRICULUM (public)
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/subjects', methods=['GET'])
    def get_subjects():
        """List all supported subjects."""
        try:
            return jsonify({'subjects': data_loader.get_subjects()})
        except Exception as e:
            logger.error(f"Get subjects error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/topics/<subject>', methods=['GET'])
    def get_topics(subject):
        """List all topics for a subject."""
        try:
            return jsonify({'subject': subject, 'topics': data_loader.get_topics(subject)})
        except Exception as e:
            logger.error(f"Get topics error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/subtopics/<subject>/<topic>', methods=['GET'])
    def get_subtopics(subject, topic):
        """List all subtopics for a subject/topic pair."""
        try:
            curriculum_id = request.args.get('curriculum_id')
            return jsonify({
                'subject':   subject,
                'topic':     topic,
                'subtopics': data_loader.get_subtopics(subject, topic, curriculum_id=curriculum_id)
            })
        except Exception as e:
            logger.error(f"Get subtopics error: {e}")
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # CURRICULUM REGISTRY (public)
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/curricula', methods=['GET'])
    def list_curricula():
        """List all available curricula from the registry."""
        try:
            if not curriculum_registry:
                return jsonify({'curricula': []}), 200
            all_curricula = curriculum_registry.get_all()
            result = []
            for cid, meta in all_curricula.items():
                result.append({
                    'curriculum_id': cid,
                    'name': meta.get('name'),
                    'language': meta.get('language'),
                    'region': meta.get('region'),
                    'subjects': meta.get('metadata', {}).get('subjects', []),
                })
            return jsonify({'curricula': result}), 200
        except Exception as e:
            logger.error(f"List curricula error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/curricula/<curriculum_id>', methods=['GET'])
    def get_curriculum_metadata(curriculum_id):
        """Return metadata for a specific curriculum."""
        try:
            if not curriculum_registry:
                return jsonify({'error': 'Curriculum registry not configured'}), 503
            meta = curriculum_registry.get_curriculum(curriculum_id)
            if not meta:
                return jsonify({'error': 'Curriculum not found'}), 404
            return jsonify({'curriculum_id': curriculum_id, **meta}), 200
        except Exception as e:
            logger.error(f"Get curriculum error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/curricula/<curriculum_id>/hierarchy/<level>', methods=['GET'])
    def get_curriculum_level(curriculum_id, level):
        """Return items at the given hierarchy level for a curriculum."""
        try:
            if not curriculum_loader:
                return jsonify({'error': 'Curriculum loader not configured'}), 503
            items = curriculum_loader.get_hierarchy_level(curriculum_id, level)
            return jsonify({'curriculum_id': curriculum_id, 'level': level, 'items': items}), 200
        except Exception as e:
            logger.error(f"Get curriculum level error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/curricula/<curriculum_id>/hierarchy/<level>/<item>/children', methods=['GET'])
    def get_curriculum_children(curriculum_id, level, item):
        """Return children of the given item at the next hierarchy level."""
        try:
            if not curriculum_loader:
                return jsonify({'error': 'Curriculum loader not configured'}), 503
            path_args = dict(request.args)
            path_args[level] = item
            meta = curriculum_registry.get_curriculum(curriculum_id) if curriculum_registry else {}
            levels = meta.get('structure', {}).get('levels', []) if meta else []
            if not levels:
                return jsonify({'error': 'Curriculum structure not defined'}), 400
            level_idx = levels.index(level) if level in levels else -1
            if level_idx < 0 or level_idx + 1 >= len(levels):
                return jsonify({'error': f"No child level after '{level}'"}), 400
            child_level = levels[level_idx + 1]
            children = curriculum_loader.get_children(curriculum_id, path_args, child_level)
            return jsonify({
                'curriculum_id': curriculum_id,
                'parent_level': level,
                'parent_item': item,
                'child_level': child_level,
                'children': children,
            }), 200
        except Exception as e:
            logger.error(f"Get curriculum children error: {e}")
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # AUTH
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/auth/signup', methods=['POST'])
    def signup():
        """
        Register a new teacher account.

        Request JSON: {email, password, username, name?}
        Response 201: {user_id, email, username, token}
        """
        try:
            data = request.get_json(force=True) or {}

            if not validate_email(data.get('email', '')):
                return jsonify({'error': 'Invalid email'}), 400
            if not validate_password(data.get('password', '')):
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            if not validate_username(data.get('username', '')):
                return jsonify({'error': 'Username must be at least 3 characters'}), 400

            result = signup_user(
                email=data['email'], password=data['password'],
                username=data['username'], name=data.get('name')
            )
            return jsonify(result), 201

        except AuthError as e:
            return jsonify({'error': str(e)}), 409
        except Exception as e:
            logger.error(f"Signup error: {e}", exc_info=True)
            return jsonify({'error': 'Signup failed'}), 500

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        """
        Login with email + password.

        Request JSON: {email, password}
        Response 200: {user_id, email, username, token, subscription_status, teacher_id}
        """
        try:
            data = request.get_json(force=True) or {}

            if not validate_email(data.get('email', '')):
                return jsonify({'error': 'Invalid email'}), 400
            if not data.get('password'):
                return jsonify({'error': 'Password required'}), 400

            result = login_user(email=data['email'], password=data['password'])
            return jsonify(result), 200

        except AuthError as e:
            return jsonify({'error': str(e)}), 401
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return jsonify({'error': 'Login failed'}), 500

    @app.route('/api/auth/me', methods=['GET'])
    @require_jwt
    def get_user_info():
        """
        Return the currently authenticated user's profile.

        Headers: Authorization: Bearer <token>
        Response 200: {user_id, email, username, name, role, subscription_status}
        """
        try:
            user = get_current_user(request.user_id)
            return jsonify({
                'user_id':             str(user['id']),
                'email':               user['email'],
                'username':            user['username'],
                'name':                user.get('name'),
                'role':                user['role'],
                'subscription_status': user['subscription_status'],
            }), 200
        except AuthError as e:
            return jsonify({'error': str(e)}), 401
        except Exception as e:
            logger.error(f"Get user error: {e}", exc_info=True)
            return jsonify({'error': 'Could not retrieve user'}), 500

    @app.route('/api/auth/teacher', methods=['POST'])
    def teacher_login():
        """
        Legacy flow: create or retrieve a teacher record by name.

        Request JSON: {teacher_name, center_id?}
        """
        try:
            data         = request.get_json(force=True) or {}
            teacher_name = data.get('teacher_name')
            center_id    = data.get('center_id')

            if not teacher_name:
                return jsonify({'error': 'teacher_name required'}), 400

            teacher_id = script_store.create_or_get_teacher(teacher_name, center_id)
            if teacher_id:
                return jsonify({'success': True, 'teacher_id': teacher_id, 'teacher_name': teacher_name})
            return jsonify({'error': 'Could not create/get teacher'}), 500

        except Exception as e:
            logger.error(f"Teacher login error: {e}")
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # BILLING
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/billing/status', methods=['GET'])
    @require_jwt
    def billing_status():
        """
        Subscription status + last 12 payments.

        Headers: Authorization: Bearer <token>
        """
        try:
            return jsonify(get_billing_status(request.teacher_id)), 200
        except Exception as e:
            logger.error(f"Billing status error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/billing/history', methods=['GET'])
    @require_jwt
    def billing_history():
        """
        Full payment history (last 50 transactions).

        Headers: Authorization: Bearer <token>
        """
        try:
            return jsonify({'payments': get_payment_history(request.teacher_id)}), 200
        except Exception as e:
            logger.error(f"Billing history error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/payment/webhook', methods=['POST'])
    def payment_webhook():
        """
        Wayl payment gateway webhook.

        Headers: X-Webhook-Signature: <sha256-hmac>
        Request JSON: {status, transaction_id, teacher_id, amount, currency}
        """
        try:
            signature = request.headers.get('X-Webhook-Signature', '')
            body      = request.get_data()

            if not verify_wayl_webhook_signature(body, signature):
                logger.warning("Payment webhook: invalid signature")
                return jsonify({'error': 'Invalid signature'}), 401

            data = request.get_json(force=True)
            handle_wayl_webhook(data)
            return jsonify({'status': 'received'}), 200

        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # SCRIPT GENERATION
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/generate', methods=['POST'])
    @require_jwt
    @require_active_subscription
    def generate_script():
        """
        Generate a curriculum-aligned YouTube script.
        Requires JWT + active subscription.

        Headers: Authorization: Bearer <token>
        Request JSON: {subject, topic, subtopic, duration_minutes?, hook_archetype?, teacher_name?}
        Response 201: Full script result dict with script_id
        """
        try:
            data          = request.get_json(force=True) or {}
            subject       = data.get('subject')
            topic         = data.get('topic')
            subtopic      = data.get('subtopic')
            duration      = int(data.get('duration_minutes', 14))
            archetype     = data.get('hook_archetype', 'default')
            teacher_name  = data.get('teacher_name')
            curriculum_id = data.get('curriculum_id')
            path_args     = data.get('path_args')

            # Support both legacy (subject/topic/subtopic) and new (curriculum_id/path_args)
            if not path_args and not all([subject, topic, subtopic]):
                return jsonify({'error': 'Provide either subject/topic/subtopic or path_args'}), 400

            response = script_generator.generate(
                subject=subject,
                topic=topic,
                subtopic=subtopic,
                duration_minutes=duration,
                hook_archetype=archetype,
                curriculum_id=curriculum_id,
                path_args=path_args,
            )

            if response.get('success'):
                script_id = str(uuid.uuid4())
                response['script_id'] = script_id
                scripts_cache[script_id] = response

                if teacher_name:
                    teacher_id = script_store.create_or_get_teacher(teacher_name)
                    if teacher_id:
                        script_store.save_script(teacher_id, subject, topic, subtopic, response)
                        response['teacher_id'] = teacher_id

                return jsonify(response), 201

            return jsonify(response), 500

        except Exception as e:
            logger.error(f"Generate script error: {e}\n{traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/generate-study-tips', methods=['POST'])
    def generate_study_tips():
        """
        Generate a study tips script — no S3 curriculum, no auth required.

        Request JSON: {tip_topic, duration_minutes?, hook_archetype?, teacher_name?}
        """
        try:
            data         = request.get_json(force=True) or {}
            tip_topic    = data.get('tip_topic')
            duration     = int(data.get('duration_minutes', 14))
            archetype    = data.get('hook_archetype', 'teacher')
            teacher_name = data.get('teacher_name')

            if not tip_topic:
                return jsonify({'error': 'Missing tip_topic'}), 400

            response = study_tips_generator.generate(tip_topic, duration, archetype)

            if response.get('success'):
                script_id = str(uuid.uuid4())
                response['script_id'] = script_id
                scripts_cache[script_id] = response

                if teacher_name:
                    teacher_id = script_store.create_or_get_teacher(teacher_name)
                    if teacher_id:
                        script_store.save_script(teacher_id, 'general', tip_topic, 'study_tips', response)
                        response['teacher_id'] = teacher_id

            return jsonify(response)

        except Exception as e:
            logger.error(f"Study tips error: {e}\n{traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/scripts/<teacher_id>', methods=['GET'])
    @require_jwt
    def get_scripts(teacher_id):
        """
        List all scripts for a teacher (own scripts only).

        Headers: Authorization: Bearer <token>
        Response 200: {success, teacher_id, scripts: [...], total}
        """
        try:
            if request.teacher_id != teacher_id:
                return jsonify({'error': 'Unauthorized'}), 403

            scripts = script_store.get_scripts_by_teacher(teacher_id)
            return jsonify({'success': True, 'teacher_id': teacher_id,
                            'scripts': scripts, 'total': len(scripts)}), 200
        except Exception as e:
            logger.error(f"Get scripts error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/export/<script_id>', methods=['GET'])
    @require_jwt
    def export_script(script_id):
        """
        Download a script as DOCX. Cache-first, then DB.

        Headers: Authorization: Bearer <token>
        Response: Binary DOCX file download
        """
        try:
            return docx_exporter.export(script_id)
        except Exception as e:
            logger.error(f"Export error: {e}")
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # ANALYTICS
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/analytics/<teacher_id>', methods=['GET'])
    @require_jwt
    def get_analytics(teacher_id):
        """Get aggregated improvement metrics for a teacher."""
        try:
            result = metrics.get_improvement_metrics(teacher_id)
            if result:
                return jsonify(result)
            return jsonify({'error': 'Cannot retrieve metrics'}), 500
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/analytics/top/<teacher_id>', methods=['GET'])
    @require_jwt
    def get_top_scripts(teacher_id):
        """Return top N scripts by weighted view score."""
        try:
            limit = int(request.args.get('limit', 5))
            return jsonify({'teacher_id': teacher_id, 'top_scripts': metrics.get_top_scripts(teacher_id, limit)})
        except Exception as e:
            logger.error(f"Top scripts error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/analytics/save', methods=['POST'])
    @require_jwt
    def save_analytics():
        """
        Save YouTube engagement metrics for a script.

        Request JSON: {script_id, teacher_id, views, channel_subscribers?,
                       likes?, comments?, shares?}
        """
        try:
            data = request.get_json(force=True) or {}

            analytics_id = yt_store.save(
                video_id            = data.get('video_id'),
                views               = int(data.get('views', 0)),
                channel_subscribers = int(data.get('channel_subscribers', 1000)),
                likes               = int(data.get('likes', 0)),
                comments            = int(data.get('comments', 0)),
                shares              = int(data.get('shares', 0)),
            )

            if analytics_id:
                return jsonify({'success': True, 'analytics_id': analytics_id})
            return jsonify({'error': 'Could not save analytics'}), 500

        except Exception as e:
            logger.error(f"Analytics save error: {e}")
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # ADMIN
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/admin/teachers', methods=['GET'])
    @require_jwt
    @require_admin
    def admin_list_teachers():
        """List all teachers. Admin only."""
        try:
            from features.database import DB
            from psycopg2.extras import RealDictCursor

            conn = DB().get_connection()
            cur  = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT t.id, t.username, t.subscription_status, t.subscription_expires_at,
                       u.email, u.created_at
                FROM teachers t
                JOIN users u ON u.id = t.user_id
                ORDER BY u.created_at DESC
            """)
            teachers = []
            for row in cur.fetchall():
                t = dict(row)
                t['id'] = str(t['id'])
                for key in ('subscription_expires_at', 'created_at'):
                    if t.get(key):
                        t[key] = t[key].isoformat()
                teachers.append(t)
            cur.close()
            conn.close()
            return jsonify({'teachers': teachers, 'total': len(teachers)}), 200

        except Exception as e:
            logger.error(f"Admin list teachers error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    # ════════════════════════════════════════════════════════════════════
    # CENTER DASHBOARD
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/center/<center_id>/dashboard', methods=['GET'])
    def center_dashboard(center_id):
        """
        Get center dashboard data — all teachers and their scripts
        
        Returns: {
            "center_id": "uuid",
            "teachers": [...],
            "stats": {
                "total_teachers": int,
                "total_scripts": int,
                "published_count": int,
                "draft_count": int,
                "total_views": int,
                "avg_engagement_rate": float
            }
        }
        """
        try:
            conn = script_store.db.get_connection()
            cur = conn.cursor()
            
            # Get all teachers for this center
            cur.execute("""
                SELECT DISTINCT t.id, t.username, t.subscription_status, t.youtube_channel_id, t.channel_subs
                FROM teachers t
                INNER JOIN generated_scripts gs ON t.id = gs.teacher_id
                WHERE gs.center_id = %s
                ORDER BY t.username
            """, (center_id,))
            
            teachers_data = cur.fetchall()
            teachers = []
            
            total_scripts = 0
            total_views = 0
            published_count = 0
            draft_count = 0
            engagement_rates = []
            
            for teacher_id, username, sub_status, youtube_ch, subs in teachers_data:
                # Get all scripts for this teacher
                cur.execute("""
                    SELECT 
                        gs.id, gs.subject, gs.topic, gs.status, gs.word_count, 
                        gs.youtube_url, gs.created_at,
                        COALESCE(vp.views, 0) as views,
                        COALESCE(vp.likes, 0) as likes,
                        COALESCE(vp.engagement_rate, 0) as engagement_rate
                    FROM generated_scripts gs
                    LEFT JOIN published_videos pv ON gs.id = pv.script_id
                    LEFT JOIN video_performance vp ON pv.id = vp.video_id
                    WHERE gs.teacher_id = %s AND gs.center_id = %s
                    ORDER BY gs.created_at DESC
                """, (teacher_id, center_id))
                
                scripts_data = cur.fetchall()
                scripts = []
                
                for script in scripts_data:
                    script_obj = {
                        "id": str(script[0]),
                        "subject": script[1],
                        "topic": script[2],
                        "status": script[3],
                        "word_count": script[4],
                        "youtube_url": script[5],
                        "created_at": script[6].isoformat() if script[6] else None,
                        "views": script[7] or 0,
                        "likes": script[8] or 0,
                        "engagement_rate": script[9] or 0.0
                    }
                    scripts.append(script_obj)
                    
                    total_scripts += 1
                    total_views += script[7] or 0
                    
                    if script[3] == 'published':
                        published_count += 1
                    else:
                        draft_count += 1
                    
                    if script[9]:
                        engagement_rates.append(script[9])
                
                teacher_obj = {
                    "teacher_id": str(teacher_id),
                    "username": username,
                    "subscription_status": sub_status,
                    "youtube_channel": youtube_ch or "Not connected",
                    "channel_subscribers": subs or 0,
                    "total_scripts": len(scripts),
                    "scripts": scripts
                }
                teachers.append(teacher_obj)
            
            avg_engagement = sum(engagement_rates) / len(engagement_rates) if engagement_rates else 0
            
            stats = {
                "total_teachers": len(teachers),
                "total_scripts": total_scripts,
                "published_count": published_count,
                "draft_count": draft_count,
                "total_views": total_views,
                "avg_engagement_rate": round(avg_engagement, 4)
            }
            
            cur.close()
            conn.close()
            
            return jsonify({
                "success": True,
                "center_id": center_id,
                "teachers": teachers,
                "stats": stats
            }), 200
        
        except Exception as e:
            logger.error(f"Center dashboard error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route('/center-dashboard', methods=['GET'])
    def serve_center_dashboard():
        try:
            frontend_path = os.getenv('FRONTEND_PATH', './static')
            with open(f'{frontend_path}/center_dashboard.html', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error loading center dashboard: {e}", 500



    # ════════════════════════════════════════════════════════════════════
    # YOUTUBE ANALYTICS (Per-Teacher OAuth)
    # ════════════════════════════════════════════════════════════════════
    
    # Initialize YouTube managers
    from features.youtube_oauth_manager import YouTubeOAuthManager
    from features.youtube_api_fetcher import YouTubeAPIFetcher
    
    oauth_manager = YouTubeOAuthManager(script_store.db)
    api_fetcher = YouTubeAPIFetcher(oauth_manager)

    @app.route('/api/teacher/youtube/auth-url', methods=['GET'])
    @require_jwt
    def get_youtube_auth_url():
        """Get YouTube OAuth authorization URL for a teacher."""
        try:
            teacher_id = request.user_id
            auth_url, state = oauth_manager.get_authorization_url(teacher_id)
            
            if not auth_url:
                return jsonify({"error": "YouTube OAuth not configured"}), 500
            
            logger.info(f"Auth URL generated for teacher {teacher_id}")
            return jsonify({
                "success": True,
                "auth_url": auth_url,
                "state": state
            }), 200
        
        except Exception as e:
            logger.error(f"Get auth URL error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/teacher/youtube/oauth-callback', methods=['GET'])
    def youtube_oauth_callback():
        """OAuth callback from Google - exchanges code for access token."""
        try:
            from flask import redirect
            
            code = request.args.get('code')
            state = request.args.get('state')
            teacher_id = request.args.get('teacher_id')
            
            if not code or not state or not teacher_id:
                return jsonify({"error": "Missing OAuth parameters"}), 400
            
            success = oauth_manager.handle_oauth_callback(teacher_id, code, state)
            
            if success:
                logger.info(f"YouTube OAuth completed for teacher {teacher_id}")
                return redirect('/dashboard?youtube=connected')
            else:
                return jsonify({"error": "OAuth failed"}), 500
        
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/teacher/youtube/sync-analytics', methods=['POST'])
    @require_jwt
    def sync_youtube_analytics():
        """Fetch video metrics from YouTube and save to database."""
        try:
            teacher_id = request.user_id
            data = request.get_json()
            
            video_id = data.get('video_id')
            if not video_id:
                return jsonify({"error": "Missing video_id"}), 400
            
            # Fetch metrics from YouTube
            metrics = api_fetcher.fetch_video_metrics(teacher_id, video_id)
            
            if not metrics:
                return jsonify({"error": "Could not fetch YouTube metrics"}), 500
            
            # Get teacher info
            teacher = get_current_user(teacher_id)
            channel_subs = teacher.get('channel_subs', 0) if teacher else 0
            
            # Save to database
            success = yt_store.save(
                video_id=video_id,
                views=metrics['views'],
                channel_subscribers=channel_subs,
                likes=metrics['likes'],
                comments=metrics['comments'],
                shares=metrics.get('shares', 0)
            )
            
            if not success:
                return jsonify({"error": "Failed to save metrics"}), 500
            
            logger.info(f"Analytics synced for video {video_id}: {metrics['views']} views")
            
            return jsonify({
                "success": True,
                "metrics": metrics
            }), 200
        
        except Exception as e:
            logger.error(f"Sync analytics error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/teacher/youtube/sync-all-videos', methods=['POST'])
    @require_jwt
    def sync_all_youtube_videos():
        """Fetch metrics for ALL uploaded videos in teacher's channel."""
        try:
            teacher_id = request.user_id
            
            # Get teacher's channel ID
            teacher = get_current_user(teacher_id)
            channel_id = teacher.get('youtube_channel_id') if teacher else None
            
            if not channel_id:
                return jsonify({"error": "Teacher has no YouTube channel connected"}), 400
            
            # Fetch all videos
            videos = api_fetcher.fetch_channel_videos(teacher_id, channel_id, max_results=50)
            
            if not videos:
                return jsonify({"error": "Could not fetch channel videos"}), 500
            
            # Get channel subscriber count
            channel_subs = api_fetcher.fetch_channel_subscribers(teacher_id, channel_id)
            
            # Save each video's metrics
            synced = 0
            for video in videos:
                success = yt_store.save(
                    video_id=video['video_id'],
                    views=video.get('views', 0),
                    channel_subscribers=channel_subs or 0,
                    likes=video.get('likes', 0),
                    comments=video.get('comments', 0),
                    shares=0
                )
                if success:
                    synced += 1
            
            logger.info(f"Synced {synced} videos for teacher {teacher_id}")
            
            return jsonify({
                "success": True,
                "synced_count": synced,
                "total_count": len(videos),
                "videos": videos
            }), 200
        
        except Exception as e:
            logger.error(f"Sync all videos error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/teacher/youtube/disconnect', methods=['POST'])
    @require_jwt
    def disconnect_youtube():
        """Revoke teacher's YouTube OAuth credentials."""
        try:
            teacher_id = request.user_id
            success = oauth_manager.revoke_credentials(teacher_id)
            
            if success:
                logger.info(f"YouTube account disconnected for teacher {teacher_id}")
                return jsonify({
                    "success": True,
                    "message": "YouTube account disconnected"
                }), 200
            else:
                return jsonify({"error": "Failed to disconnect"}), 500
        
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/teacher/youtube/status', methods=['GET'])
    @require_jwt
    def youtube_status():
        """Check if teacher's YouTube account is connected."""
        try:
            teacher_id = request.user_id
            teacher = get_current_user(teacher_id)
            channel_id = teacher.get('youtube_channel_id') if teacher else None
            
            if not channel_id:
                return jsonify({
                    "connected": False,
                    "message": "No YouTube channel connected"
                }), 200
            
            # Check if credentials exist
            credentials = oauth_manager.get_credentials(teacher_id)
            connected = credentials is not None
            
            return jsonify({
                "connected": connected,
                "channel_id": channel_id,
                "channel_name": teacher.get('youtube_channel_name') if teacher else None,
                "subscribers": teacher.get('channel_subs', 0) if teacher else 0,
                "last_sync": teacher.get('youtube_last_sync') if teacher else None
            }), 200
        
        except Exception as e:
            logger.error(f"YouTube status error: {e}")
            return jsonify({"error": str(e)}), 500




    # ════════════════════════════════════════════════════════════════════
    # LONG-FORM VIDEOS (1hr / 3hr with streaming)
    # ════════════════════════════════════════════════════════════════════
    
    # Import long-form generator if not provided
    if not long_form_gen:
        from features.long_form_generator import LongFormVideoGenerator
        
        if not s3_client:
            import boto3
            s3_client = boto3.client('s3', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        if not bucket:
            bucket = os.getenv('S3_BUCKET')
        
        long_form_gen = LongFormVideoGenerator(
            provider=llm_provider,
            data_loader=data_loader,
            s3_client=s3_client,
            bucket=bucket,
            validator=validator,
            dedup=dedup
        )

    @app.route('/api/generate-long-form', methods=['POST'])
    @require_jwt
    @require_active_subscription
    def generate_long_form():
        """Generate 1hr or 3hr long-form educational video with streaming output."""
        from flask import Response, stream_with_context
        import json
        
        try:
            teacher_id = request.user_id
            data = request.get_json()
            
            subject = data.get('subject')
            topic = data.get('topic')
            subtopic = data.get('subtopic')
            duration_minutes = data.get('duration_minutes', 60)
            
            if not all([subject, topic, subtopic]):
                return jsonify({"error": "Missing required fields: subject, topic, subtopic"}), 400
            
            if duration_minutes not in [60, 180]:
                return jsonify({"error": "duration_minutes must be 60 or 180"}), 400
            
            logger.info(f"Long-form generation: {subject}/{topic}/{subtopic} ({duration_minutes}min)")
            
            # Collect events for streaming
            events = []
            
            def stream_callback(event_type, data_item):
                """Collect events for streaming response."""
                events.append({
                    'event': event_type,
                    'data': data_item if isinstance(data_item, dict) else {'message': str(data_item)}
                })
            
            # Generate with streaming
            result = long_form_gen.generate(
                subject=subject,
                topic=topic,
                subtopic=subtopic,
                duration_minutes=duration_minutes,
                stream_callback=stream_callback,
            )
            
            if not result['success']:
                return jsonify({"error": result['error']}), 500
            
            # Save to database
            script_id = str(uuid.uuid4())
            metadata_json = json.dumps({
                'duration_minutes': duration_minutes,
                'word_count': result['final_word_count'],
                'outline': result['outline'],
                'validation': result['validation'],
                'is_duplicate': result['is_duplicate'],
            })
            
            conn = script_store.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO generated_scripts (
                    id, teacher_id, subject, topic, subtopic,
                    script, quality_metrics, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                script_id, teacher_id, subject, topic, subtopic,
                result['full_script'], metadata_json, 'draft'
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            result['script_id'] = script_id
            logger.info(f"Long-form script saved: {script_id}")
            
            # Stream response as SSE
            def generate_sse():
                for event in events:
                    yield f"event: {event['event']}\n"
                    yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                
                # Final complete event
                yield "event: complete\n"
                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
            
            return Response(
                stream_with_context(generate_sse()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                    'Content-Type': 'text/event-stream',
                }
            )
        
        except Exception as e:
            logger.error(f"Long-form generation error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route('/api/long-form/<script_id>', methods=['GET'])
    @require_jwt
    def get_long_form_script(script_id):
        """Retrieve a generated long-form script."""
        try:
            teacher_id = request.user_id
            
            conn = script_store.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT 
                    id, teacher_id, subject, topic, subtopic,
                    script, quality_metrics, created_at
                FROM generated_scripts
                WHERE id = %s AND teacher_id = %s
            """, (script_id, teacher_id))
            
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if not row:
                return jsonify({"error": "Long-form script not found"}), 404
            
            script_id, teacher_id, subject, topic, subtopic, script_content, metadata_json, created_at = row

            if isinstance(metadata_json, dict):
                metadata = metadata_json
            elif metadata_json:
                metadata = json.loads(metadata_json)
            else:
                metadata = {}
            
            return jsonify({
                "success": True,
                "script_id": str(script_id),
                "subject": subject,
                "topic": topic,
                "subtopic": subtopic,
                "duration_minutes": metadata.get('duration_minutes'),
                "word_count": metadata.get('word_count'),
                "outline": metadata.get('outline'),
                "full_script": script_content,
                "validation": metadata.get('validation'),
                "is_duplicate": metadata.get('is_duplicate'),
                "generated_at": created_at.isoformat() if created_at else None
            }), 200
        
        except Exception as e:
            logger.error(f"Get long-form script error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/long-form/export/<script_id>', methods=['GET'])
    @require_jwt
    def export_long_form_docx(script_id):
        """Export long-form script as DOCX."""
        try:
            from flask import send_file
            import io
            
            teacher_id = request.user_id
            include_outline = request.args.get('include_outline', 'false').lower() == 'true'
            
            conn = script_store.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT 
                    id, subject, topic, subtopic,
                    script, quality_metrics
                FROM generated_scripts
                WHERE id = %s AND teacher_id = %s
            """, (script_id, teacher_id))
            
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if not row:
                return jsonify({"error": "Long-form script not found"}), 404
            
            script_id, subject, topic, subtopic, script_content, metadata_json = row
            if isinstance(metadata_json, dict):
                metadata = metadata_json
            elif metadata_json:
                metadata = json.loads(metadata_json)
            else:
                metadata = {}
            
            # Export as DOCX
            docx_bytes = docx_exporter.export_long_form(
                subject=subject,
                topic=f"{topic} - {subtopic}",
                script_content=script_content,
                outline=metadata.get('outline') if include_outline else None,
                metadata=metadata
            )
            
            return send_file(
                io.BytesIO(docx_bytes),
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                as_attachment=True,
                download_name=f"{subject}_{topic}_{subtopic}_longform.docx"
            )
        
        except Exception as e:
            logger.error(f"Export long-form error: {e}")
            return jsonify({"error": str(e)}), 500




    # ════════════════════════════════════════════════════════════════════
    # ESSAY GENERATOR (Hidden Premium Feature)
    # ════════════════════════════════════════════════════════════════════
    
    from features.essay_generator import EssayGenerator
    from functools import wraps
    
    essay_gen = EssayGenerator(
        provider=llm_provider,
        validator=validator,
        dedup=dedup
    )

    def require_essay_author(f):
        """Decorator: Only accessible to users with is_essay_author=true."""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user_id = request.user_id
                conn = script_store.db.get_connection()
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT is_essay_author
                    FROM users
                    WHERE id = %s
                """, (user_id,))
                
                row = cur.fetchone()
                cur.close()
                conn.close()
                
                if not row or not row[0]:
                    logger.warning(f"Essay access denied for user {user_id}")
                    return jsonify({"error": "Access denied. Essay feature not enabled."}), 403
                
                return f(*args, **kwargs)
            
            except Exception as e:
                logger.error(f"Essay author check error: {e}")
                return jsonify({"error": "Authorization error"}), 500
        
        return decorated_function

    @app.route('/api/essay/ingest-chunk', methods=['POST'])
    @require_jwt
    @require_essay_author
    def ingest_essay_chunk():
        """
        Upload one chunk of source material to S3.
        Body: { session_id, chunk_index, chunk_text, total_chunks }
        """
        try:
            data = request.get_json(force=True) or {}
            session_id = data.get('session_id')
            chunk_index = data.get('chunk_index')
            chunk_text = data.get('chunk_text', '')
            total_chunks = data.get('total_chunks', 1)

            if not session_id or chunk_index is None:
                return jsonify({'error': 'Missing session_id or chunk_index'}), 400

            key = f"essay-sources/{session_id}/chunk_{chunk_index:04d}.txt"
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=chunk_text.encode('utf-8'),
                ContentType='text/plain',
            )

            logger.info(f"Essay chunk {chunk_index + 1}/{total_chunks} stored: {key}")
            return jsonify({'success': True, 'chunk_index': chunk_index, 'total_chunks': total_chunks}), 200

        except Exception as e:
            logger.error(f"Ingest chunk error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/essay/generate', methods=['POST'])
    @require_jwt
    @require_essay_author
    def generate_essay():
        """
        Generate a professional essay from source material.

        Headers: Authorization: Bearer <token>
        Request JSON: {title, source_material, essay_type?, tone?, target_audience?}
        Response 201: Full essay result dict with essay_id
        """
        from flask import Response, stream_with_context
        import json as _json

        try:
            data = request.get_json(force=True) or {}
            title = data.get('title')
            source_material = data.get('source_material')
            session_id = data.get('session_id')

            # Load source from S3 chunks if session_id provided
            if not source_material and session_id:
                try:
                    prefix = f"essay-sources/{session_id}/"
                    s3_resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
                    chunk_keys = sorted(
                        [obj['Key'] for obj in s3_resp.get('Contents', [])],
                        key=lambda k: k
                    )
                    parts = []
                    for key in chunk_keys:
                        obj = s3_client.get_object(Bucket=bucket, Key=key)
                        parts.append(obj['Body'].read().decode('utf-8'))
                    source_material = '\n\n'.join(parts)
                    logger.info(f"Loaded {len(chunk_keys)} S3 chunks for session {session_id}: {len(source_material.split())} words")
                except Exception as e:
                    logger.error(f"S3 chunk load error: {e}")
                    return jsonify({'error': f'Failed to load source chunks: {e}'}), 500

            if not title or not source_material:
                return jsonify({'error': 'Missing title or source_material (or session_id)'}), 400

            essay_type = data.get('essay_type', 'medium')
            tone = data.get('tone', 'academic')
            target_audience = data.get('target_audience', 'educated general reader')

            logger.info(f"Essay generation: '{title}' ({essay_type}, {tone})")

            events = []

            def stream_callback(event_type, data_item):
                events.append({
                    'event': event_type,
                    'data': data_item if isinstance(data_item, dict) else {'message': str(data_item)}
                })

            result = essay_gen.generate(
                title=title,
                source_material=source_material,
                essay_type=essay_type,
                tone=tone,
                target_audience=target_audience,
                stream_callback=stream_callback,
            )

            if not result.get('success'):
                return jsonify({'error': result.get('error', 'Essay generation failed')}), 500

            # Save to essays table
            essay_id = str(uuid.uuid4())
            user_id = request.user_id

            conn = script_store.db.get_connection()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO essays (id, user_id, title, content, metadata, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        essay_id,
                        user_id,
                        title,
                        result['full_essay'],
                        _json.dumps({
                            'essay_type': essay_type,
                            'tone': tone,
                            'target_audience': target_audience,
                            'word_count': result['final_word_count'],
                            'source_hash': result.get('source_hash'),
                            'outline': result.get('outline'),
                            'validation': result.get('validation'),
                            'is_duplicate': result.get('is_duplicate'),
                        }),
                        'draft'
                    ))
                    conn.commit()
                    cur.close()
                except Exception as db_err:
                    logger.error(f"Essay DB save error: {db_err}")
                finally:
                    conn.close()

            result['essay_id'] = essay_id
            logger.info(f"Essay saved: {essay_id} ({result['final_word_count']} words)")

            return jsonify(result), 201

        except Exception as e:
            logger.error(f"Essay generation error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/essay/<essay_id>', methods=['GET'])
    @require_jwt
    @require_essay_author
    def get_essay(essay_id):
        """
        Retrieve a generated essay by ID.

        Headers: Authorization: Bearer <token>
        Response 200: {essay_id, title, content, metadata, created_at}
        """
        try:
            user_id = request.user_id
            conn = script_store.db.get_connection()
            if not conn:
                return jsonify({'error': 'Database unavailable'}), 500

            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, content, metadata, status, created_at
                FROM essays
                WHERE id = %s AND user_id = %s
            """, (essay_id, user_id))

            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                return jsonify({'error': 'Essay not found'}), 404

            eid, title, content, metadata_json, status, created_at = row
            import json as _json
            metadata = metadata_json if isinstance(metadata_json, dict) else (_json.loads(metadata_json) if metadata_json else {})

            return jsonify({
                'success': True,
                'essay_id': str(eid),
                'title': title,
                'content': content,
                'essay_type': metadata.get('essay_type'),
                'tone': metadata.get('tone'),
                'target_audience': metadata.get('target_audience'),
                'word_count': metadata.get('word_count'),
                'outline': metadata.get('outline'),
                'status': status,
                'created_at': created_at.isoformat() if created_at else None,
            }), 200

        except Exception as e:
            logger.error(f"Get essay error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/essay/<essay_id>/export', methods=['GET'])
    @require_jwt
    @require_essay_author
    def export_essay(essay_id):
        """
        Export essay as DOCX.

        Headers: Authorization: Bearer <token>
        Query: ?format=docx (default) or ?format=md
        Response: File download
        """
        try:
            from flask import send_file
            import io
            import json as _json

            user_id = request.user_id
            export_format = request.args.get('format', 'docx')

            conn = script_store.db.get_connection()
            if not conn:
                return jsonify({'error': 'Database unavailable'}), 500

            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, content, metadata
                FROM essays
                WHERE id = %s AND user_id = %s
            """, (essay_id, user_id))

            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                return jsonify({'error': 'Essay not found'}), 404

            eid, title, content, metadata_json = row
            metadata = metadata_json if isinstance(metadata_json, dict) else (_json.loads(metadata_json) if metadata_json else {})

            if export_format == 'md':
                return send_file(
                    io.BytesIO(content.encode('utf-8')),
                    mimetype='text/markdown',
                    as_attachment=True,
                    download_name=f"{title[:50].replace(' ', '_')}.md"
                )

            # DOCX export
            docx_bytes = docx_exporter.export_essay(
                title=title,
                content=content,
                metadata=metadata,
            )

            if not docx_bytes:
                return jsonify({'error': 'DOCX generation failed'}), 500

            return send_file(
                io.BytesIO(docx_bytes),
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                as_attachment=True,
                download_name=f"{title[:50].replace(' ', '_')}.docx"
            )

        except Exception as e:
            logger.error(f"Export essay error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/essays', methods=['GET'])
    @require_jwt
    @require_essay_author
    def list_essays():
        """
        List all essays for the current user.

        Headers: Authorization: Bearer <token>
        Response 200: {essays: [...], total: int}
        """
        try:
            import json as _json
            user_id = request.user_id

            conn = script_store.db.get_connection()
            if not conn:
                return jsonify({'error': 'Database unavailable'}), 500

            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, metadata, status, created_at
                FROM essays
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))

            rows = cur.fetchall()
            cur.close()
            conn.close()

            essays = []
            for row in rows:
                eid, title, metadata_json, status, created_at = row
                metadata = metadata_json if isinstance(metadata_json, dict) else (_json.loads(metadata_json) if metadata_json else {})
                essays.append({
                    'essay_id': str(eid),
                    'title': title,
                    'essay_type': metadata.get('essay_type'),
                    'tone': metadata.get('tone'),
                    'word_count': metadata.get('word_count'),
                    'status': status,
                    'created_at': created_at.isoformat() if created_at else None,
                })

            return jsonify({'essays': essays, 'total': len(essays)}), 200

        except Exception as e:
            logger.error(f"List essays error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/essay_generator.html', methods=['GET'])
    def serve_essay_generator():
        try:
            frontend_path = os.getenv('FRONTEND_PATH', './static')
            with open(f'{frontend_path}/essay_generator.html', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error loading essay generator: {e}", 500

    @app.route("/", methods=["GET"])
    def serve_landing():
        try:
            frontend_path = os.getenv('FRONTEND_PATH', './static')
            with open(f"{frontend_path}/landing.html", "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}", 500

    @app.route("/dashboard", methods=["GET"])
    def serve_dashboard():
        try:
            frontend_path = os.getenv('FRONTEND_PATH', './static')
            with open(f"{frontend_path}/dashboard.html", "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}", 500
# ════════════════════════════════════════════════════════════════════
    # PODCAST OUTLINE GENERATOR
    # ════════════════════════════════════════════════════════════════════

    @app.route('/api/podcast/generate', methods=['POST'])
    @require_jwt
    @require_active_subscription
    def generate_podcast_outline():
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request body required'}), 400

            speaker_profile = data.get('speaker_profile')
            guest_profile = data.get('guest_profile')
            episode_context = data.get('episode_context')

            if not speaker_profile or not guest_profile or not episode_context:
                return jsonify({'error': 'speaker_profile, guest_profile, and episode_context required'}), 400

            from features.podcast_generator import PodcastOutlineGenerator
            podcast_gen = PodcastOutlineGenerator(llm_provider)
            result = podcast_gen.generate(speaker_profile, guest_profile, episode_context)

            if not result.get('success'):
                return jsonify({'error': result.get('error', 'Generation failed')}), 500

            return jsonify(result)

        except Exception as e:
            logger.error(f"Podcast generation error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    logger.info("All routes registered")
